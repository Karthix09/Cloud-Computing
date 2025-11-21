import os, sqlite3, requests, threading, time, re
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
import pandas as pd
import folium
from sqlalchemy import create_engine, Table, Column, String, Float, MetaData, DateTime



# Import auth module
from database import init_users_db, init_bus_db, get_db_connection, get_bus_db_connection, IS_PRODUCTION
from auth import auth_bp, login_required, current_user

#Chatbot module
from chatbot import chatbot_bp 

# Initialize users database
init_users_db()

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================
API_KEY = os.getenv("API_KEY")
TRAFFIC_API_KEY = os.getenv("TRAFFIC_API_KEY") or API_KEY
BASE_URL = os.getenv("BASE_URL", "https://datamall2.mytransport.sg/ltaodataservice")
TRAFFIC_API_URL = os.getenv("TRAFFIC_API_URL", "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents")

BUS_HEADERS = {"AccountKey": API_KEY, "accept": "application/json"}
TRAFFIC_HEADERS = {"AccountKey": TRAFFIC_API_KEY, "accept": "application/json"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUS_DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

# ==================== FLASK APP ====================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-to-strong-secret")
app.register_blueprint(auth_bp)

# ==================== CHATBOT blueprint ====================
app.register_blueprint(chatbot_bp)

# ==================== LOGIN REQUIRED ====================
# @app.before_request
# def require_login():
#     open_paths = ("/login", "/register", "/logout", "/static/", "/favicon.ico")
#     if request.path.startswith(open_paths):
#         return
#     if not session.get("user_id"):
#         return redirect(url_for("auth.login"))

# ==================== BUS MODULE ====================

# Bus database setup


# Load bus stops
def load_bus_stops():
    conn = get_bus_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM bus_stops")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    print("📥 Loading bus stops ...")
    skip = 0
    while True:
        r = requests.get(f"{BASE_URL}/BusStops?$skip={skip}", headers=BUS_HEADERS, timeout=20)
        data = r.json().get("value", [])
        if not data:
            break
        for s in data:
            c.execute("INSERT OR REPLACE INTO bus_stops VALUES (?,?,?,?,?)",
                      (s["BusStopCode"], s["Description"], s["RoadName"],
                       s["Latitude"], s["Longitude"]))
        conn.commit()
        if len(data) < 500:
            break
        skip += 500
    conn.close()
    print("✅ Bus stops cached.")

# Load bus routes
def load_bus_routes():
    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bus_routes (
        ServiceNo TEXT,
        Direction INTEGER,
        StopSequence INTEGER,
        BusStopCode TEXT,
        Distance REAL
    )""")
    conn.commit()

    print("📥 Loading bus routes ...")
    skip = 0
    while True:
        r = requests.get(f"{BASE_URL}/BusRoutes?$skip={skip}", headers=BUS_HEADERS, timeout=20)
        data = r.json().get("value", [])
        if not data:
            break
        for route in data:
            c.execute("""
                INSERT OR REPLACE INTO bus_routes VALUES (?,?,?,?,?)
            """, (
                route["ServiceNo"], route["Direction"],
                route["StopSequence"], route["BusStopCode"],
                route.get("Distance", 0.0)
            ))
        conn.commit()
        if len(data) < 500:
            break
        skip += 500
    conn.close()
    print("✅ Bus routes cached.")


# Background bus data collector
def get_all_stops():
    conn = get_bus_db_connection()  # NEW
    c = conn.cursor()
    c.execute("SELECT code FROM bus_stops")
    stops = [x[0] for x in c.fetchall()]
    conn.close()
    return stops

def collect_bus_arrivals():
    conn = get_bus_db_connection()  # NEW
    c = conn.cursor()
    stops = get_all_stops()
    now = datetime.now()

    for code in stops:
        try:
            r = requests.get(f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
                             headers=BUS_HEADERS, timeout=10)
            data = r.json().get("Services", [])
            for s in data:
                service = s["ServiceNo"]
                btype = s["NextBus"].get("Type", "Unknown")
                for key in ["NextBus", "NextBus2", "NextBus3"]:
                    t = s[key].get("EstimatedArrival")
                    if not t:
                        continue
                    eta = datetime.fromisoformat(t.replace("+08:00", ""))
                    diff = (eta - now).total_seconds() / 60
                    if diff >= 0:
                        c.execute("""SELECT eta_min FROM bus_arrivals
                                     WHERE stop_code=? AND service=?
                                     ORDER BY timestamp DESC LIMIT 1""",
                                  (code, service))
                        last = c.fetchone()
                        if not last or abs(last[0] - diff) > 0.3:
                            c.execute("""
                                INSERT INTO bus_arrivals (stop_code, service, eta_min, bus_type, timestamp)
                                VALUES (?,?,?,?,?)
                            """, (code, service, round(diff, 1), btype, now.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            time.sleep(0.4)
        except Exception as e:
            print(f"⚠️ Error fetching stop {code}: {e}")
    conn.close()
    print(f"✅ Bus collector cycle done at {datetime.now().strftime('%H:%M:%S')}")

def background_bus_collector():
    print("🧠 Bus background collector started (every 1 min).")
    while True:
        try:
            collect_bus_arrivals()
        except Exception as e:
            print("Bus collector failed:", e)
        time.sleep(60)

# Bus API endpoints
@app.route("/bus_stops")
def bus_stops():
    q = request.args.get("query", "").strip().lower()
    conn = get_bus_db_connection()  # NEW
    c = conn.cursor()
    if q:
        like = f"%{q}%"
        c.execute("""SELECT code,description,road,lat,lon FROM bus_stops
                     WHERE LOWER(description) LIKE ? OR LOWER(road) LIKE ? OR code LIKE ?""",
                  (like, like, like))
    else:
        c.execute("SELECT code,description,road,lat,lon FROM bus_stops")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"code": r[0], "desc": r[1], "road": r[2], "lat": r[3], "lon": r[4]} for r in rows])

@app.route("/bus_routes")
def get_bus_routes():
    service = request.args.get("service")
    direction = request.args.get("direction", 1)
    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()
    c.execute("SELECT ServiceNo, Direction, StopSequence, BusStopCode FROM bus_routes WHERE ServiceNo = ? AND Direction = ? ORDER BY StopSequence", (service, direction))
    rows = c.fetchall()
    conn.close()
    return jsonify([
        {"ServiceNo": r[0], "Direction": r[1], "StopSequence": r[2], "BusStopCode": r[3]}
        for r in rows
    ])

@app.route("/api/route", methods=["POST"])
def get_route():
    data = request.get_json()
    origin = data.get("origin")
    destination = data.get("destination")
    if not origin or not destination:
        return jsonify({"error": "Missing origin or destination"}), 400

    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()

    # Step 1: Direct routes (same service & direction)
    c.execute("""
        SELECT a.ServiceNo, a.Direction, a.StopSequence as seq1, b.StopSequence as seq2
        FROM bus_routes a
        JOIN bus_routes b
        ON a.ServiceNo = b.ServiceNo AND a.Direction = b.Direction
        WHERE a.BusStopCode = ? AND b.BusStopCode = ? AND a.StopSequence < b.StopSequence
    """, (origin, destination))
    direct_routes = c.fetchall()

    results = []
    for svc, direction, seq1, seq2 in direct_routes:
        stops = seq2 - seq1
        est_time = round(stops * 1.5, 1)
        results.append({
            "service": svc,
            "direction": direction,
            "stops": stops,
            "estimated_time_min": est_time
        })

    # Step 2: Transfer routes (two buses)
    if not results:
        # Find all buses from origin
        c.execute("SELECT DISTINCT ServiceNo, Direction FROM bus_routes WHERE BusStopCode = ?", (origin,))
        origin_services = c.fetchall()

        # Find all buses that go to destination
        c.execute("SELECT DISTINCT ServiceNo, Direction FROM bus_routes WHERE BusStopCode = ?", (destination,))
        dest_services = c.fetchall()

        transfer_routes = []
        for svc1, dir1 in origin_services:
            # Get all stops this bus passes
            c.execute("SELECT BusStopCode, StopSequence FROM bus_routes WHERE ServiceNo=? AND Direction=?", (svc1, dir1))
            svc1_stops = c.fetchall()

            for svc2, dir2 in dest_services:
                c.execute("SELECT BusStopCode, StopSequence FROM bus_routes WHERE ServiceNo=? AND Direction=?", (svc2, dir2))
                svc2_stops = c.fetchall()

                # Find common transfer stops
                common_stops = set([s[0] for s in svc1_stops]) & set([s[0] for s in svc2_stops])
                for transfer_stop in common_stops:
                    # Compute total estimated time
                    seq_o = next((s[1] for s in svc1_stops if s[0] == origin), None)
                    seq_t1 = next((s[1] for s in svc1_stops if s[0] == transfer_stop), None)
                    seq_t2 = next((s[1] for s in svc2_stops if s[0] == transfer_stop), None)
                    seq_d = next((s[1] for s in svc2_stops if s[0] == destination), None)

                    if seq_o is not None and seq_t1 is not None and seq_t2 is not None and seq_d is not None and seq_o < seq_t1 and seq_t2 < seq_d:
                        total_stops = (seq_t1 - seq_o) + (seq_d - seq_t2)
                        est_time = round(total_stops * 1.5 + 3, 1)  # +3 mins for transfer wait
                        transfer_routes.append({
                            "transfer": True,
                            "legs": [
                                {"service": svc1, "from": origin, "to": transfer_stop, "stops": seq_t1 - seq_o},
                                {"service": svc2, "from": transfer_stop, "to": destination, "stops": seq_d - seq_t2}
                            ],
                            "estimated_time_min": est_time
                        })

        # keep only top 3 fastest
        transfer_routes = sorted(transfer_routes, key=lambda x: x["estimated_time_min"])[:3]
        results.extend(transfer_routes)

    conn.close()

    if not results:
        return jsonify({"message": "No routes found"}), 404

    # keep only top 3 routes
    results = sorted(results, key=lambda x: x["estimated_time_min"])[:3]
    return jsonify({"origin": origin, "destination": destination, "routes": results})


@app.route("/bus_arrivals/<code>")
def bus_arrivals(code):
    try:
        r = requests.get(f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
                         headers=BUS_HEADERS, timeout=10)
        data = r.json()
        now = datetime.now()
        results = []
        for s in data.get("Services", []):
            waits = []
            for key in ["NextBus", "NextBus2", "NextBus3"]:
                t = s[key].get("EstimatedArrival")
                if t:
                    diff = (datetime.fromisoformat(t.replace("+08:00", "")) - now).total_seconds() / 60
                    if diff >= 0:
                        waits.append(round(diff, 1))
            results.append({"service": s["ServiceNo"], "type": s["NextBus"].get("Type"), "eta": waits})

        # Log
        conn = get_bus_db_connection()  # NEW
        c = conn.cursor()
        for s in results:
            for eta in s["eta"]:
                c.execute("INSERT INTO bus_arrivals (stop_code, service, eta_min, bus_type) VALUES (?,?,?,?)",
                          (code, s["service"], eta, s["type"]))
        conn.commit()
        conn.close()
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/bus/history/<stop_code>")
def bus_history(stop_code):
    conn = get_bus_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%H', timestamp) as hour, service, AVG(eta_min)
        FROM bus_arrivals
        WHERE stop_code = ? AND timestamp >= datetime('now', '-1 day')
        GROUP BY hour, service
        ORDER BY hour ASC
    """, (stop_code,))
    rows = c.fetchall()
    conn.close()

    data = {}
    for hour, svc, eta in rows:
        data.setdefault(svc, []).append({"x": int(hour), "y": round(eta, 2)})
    return render_template("bus_history.html", stop_code=stop_code, data=data)

@app.route("/bus/history/all")
def bus_history_all():
    conn = get_bus_db_connection()  # NEW
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%H', timestamp) as hour, AVG(eta_min)
        FROM bus_arrivals
        WHERE timestamp >= datetime('now', '-1 day')
        GROUP BY hour
        ORDER BY hour ASC
    """)
    rows = c.fetchall()
    conn.close()
    data = [{"x": int(hour), "y": round(avg, 2)} for hour, avg in rows]
    return render_template("bus_history_all.html", data=data)

@app.route("/bus")
def bus_dashboard():
    return render_template("bus_main.html")



# API to get users favorite locations and show on the smart bus dashboard

@app.route("/api/user_locations")
@login_required
def get_user_locations():
    """API endpoint to get current user's saved locations"""
    user = current_user()
    if not user:
        return jsonify([])
    # Use get_db_connection from database.py
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL uses %s
            cursor.execute("""
                SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = %s
                ORDER BY is_favourite DESC, id DESC
            """, (user["id"],))
        else:
            # SQLite uses ?
            cursor.execute("""
                SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = ?
                ORDER BY is_favourite DESC, id DESC
            """, (user["id"],))
        
        locations = []
        for row in cursor.fetchall():
            locations.append({
                "id": row["id"],
                "label": row["label"],
                "lat": row["latitude"],
                "lng": row["longitude"],
                "address": row["address"] if row["address"] else "",
                "postal_code": row["postal_code"] if row["postal_code"] else "",
                "is_favourite": bool(row["is_favourite"])
            })
        
        cursor.close()
        conn.close()
        return jsonify(locations)
    except Exception as e:
        print(f"Error fetching user locations: {e}")
        conn.close()
        return jsonify([])




# ==================== BUS FAVORITES API ====================

# Get user's favorite bus stops
@app.route("/api/bus_favorites", methods=["GET"])
@login_required
def get_bus_favorites():
    """Get current user's favorite bus stops"""
    user = current_user()
    if not user:
        return jsonify([])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            cursor.execute("""
                SELECT bus_stop_code, bus_stop_name
                FROM bus_favorites
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user["id"],))
        else:
            cursor.execute("""
                SELECT bus_stop_code, bus_stop_name
                FROM bus_favorites
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user["id"],))
        
        favorites = []
        for row in cursor.fetchall():
            favorites.append({
                "code": row["bus_stop_code"],
                "desc": row["bus_stop_name"]
            })
        
        cursor.close()
        conn.close()
        return jsonify(favorites)
    except Exception as e:
        print(f"Error fetching bus favorites: {e}")
        conn.close()
        return jsonify([])

#Add to bus stops to favorites

@app.route("/api/bus_favorites/add", methods=["POST"])
@login_required
def add_bus_favorite():
    """Add a bus stop to user's favorites"""
    user = current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    code = data.get("code")
    desc = data.get("desc")
    
    if not code or not desc:
        return jsonify({"error": "Missing bus stop info"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            cursor.execute("""
                INSERT INTO bus_favorites (user_id, bus_stop_code, bus_stop_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, bus_stop_code) DO NOTHING
            """, (user["id"], code, desc))
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO bus_favorites (user_id, bus_stop_code, bus_stop_name)
                VALUES (?, ?, ?)
            """, (user["id"], code, desc))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Added to favorites"})
    except Exception as e:
        print(f"Error adding bus favorite: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500

# Delete bus stop from favorites

@app.route("/api/bus_favorites/remove", methods=["POST"])
@login_required
def remove_bus_favorite():
    """Remove a bus stop from user's favorites"""
    user = current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    code = data.get("code")
    
    if not code:
        return jsonify({"error": "Missing bus stop code"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            cursor.execute("""
                DELETE FROM bus_favorites
                WHERE user_id = %s AND bus_stop_code = %s
            """, (user["id"], code))
        else:
            cursor.execute("""
                DELETE FROM bus_favorites
                WHERE user_id = ? AND bus_stop_code = ?
            """, (user["id"], code))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Removed from favorites"})
    except Exception as e:
        print(f"Error removing bus favorite: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500


# ==================== TRAFFIC MODULE ====================

# Global state
traffic_last_update = ""

# SQLite setup for traffic
traffic_engine = create_engine("sqlite:///database/TrafficIncidents.db", future=True)
traffic_metadata = MetaData()
incidents_table = Table(
    "incidents", traffic_metadata,
    Column("Id", String, primary_key=True),
    Column("Type", String),
    Column("Latitude", Float),
    Column("Longitude", Float),
    Column("Message", String),
    Column("FetchedAt", DateTime)
)
traffic_metadata.create_all(traffic_engine)

def extract_road(msg: str) -> str:
    """Extract clean, likely road name."""
    if pd.isna(msg) or not msg:
        return ""
    exp_match = re.search(r"\b(PIE|CTE|AYE|ECP|SLE|TPE|KPE|MCE|BKE)\b", msg, flags=re.IGNORECASE)
    if exp_match:
        return exp_match.group(1).upper()
    road_match = re.search(
        r"([A-Z][a-z]+(?:\s(?:Road|Rd|Avenue|Ave|Street|St|Boulevard|Drive|Dr|Lane|Expressway|Exit|Entrance)))",
        msg, flags=re.IGNORECASE)
    if road_match:
        return road_match.group(1).strip().title()
    m = re.search(r"(?:on|at|along|near)\s+([A-Z][^,.\-]*)", msg, flags=re.IGNORECASE)
    return m.group(1).strip().title() if m else ""

def fetch_and_store_traffic_loop(poll_seconds: int = 60):
    """Fetch latest traffic incidents every 60 seconds."""
    global traffic_last_update
    while True:
        try:
            now = datetime.now()
            r = requests.get(TRAFFIC_API_URL, headers=TRAFFIC_HEADERS, timeout=20)
            r.raise_for_status()
            payload = r.json()
            incidents = payload.get("value", [])
            df = pd.DataFrame(incidents)

            if df.empty:
                print(f"ℹ️ No active traffic incidents at {now}")
                time.sleep(poll_seconds)
                continue

            df["FetchedAt"] = now

            if "IncidentID" not in df.columns:
                df["IncidentID"] = df.apply(
                    lambda r: f"{r.get('Type', 'Unknown')}_{r.get('Latitude', '')}_{r.get('Longitude', '')}",
                    axis=1)

            # Remove duplicates
            unique_records = []
            seen_ids = set()
            for _, row in df.iterrows():
                record_id = str(row["IncidentID"])
                if record_id not in seen_ids:
                    seen_ids.add(record_id)
                    unique_records.append({
                        "Id": record_id,
                        "Type": row.get("Type"),
                        "Latitude": row.get("Latitude"),
                        "Longitude": row.get("Longitude"),
                        "Message": row.get("Message"),
                        "FetchedAt": now
                    })

            with traffic_engine.begin() as conn:
                conn.execute(incidents_table.delete())
                if unique_records:
                    conn.execute(incidents_table.insert(), unique_records)

            traffic_last_update = now.strftime("%d %b %Y, %I:%M %p")
            print(f"✅ Updated {len(unique_records)} active traffic incidents at {traffic_last_update}")

        except Exception as e:
            print("❌ Traffic fetch error:", e)

        time.sleep(poll_seconds)

def build_traffic_map_from_df(df: pd.DataFrame) -> str:
    """Generate a folium map with all traffic incidents."""
    sg_bounds = [[1.1304753, 103.6920359], [1.4504753, 104.0120359]]
    sg_map = folium.Map(location=[1.3521, 103.8198], zoom_start=12, control_scale=True)

    if not df.empty:
        for _, row in df.iterrows():
            lat, lon = row.get("Latitude"), row.get("Longitude")
            if pd.notna(lat) and pd.notna(lon):
                msg = row.get("Message") or "No description"
                type_info = row.get("Type") or "Incident"
                match = re.search(r"\((\d{1,2}/\d{1,2})\)(\d{2}:\d{2})", msg)
                reported_time = f"({match.group(1)}) {match.group(2)}" if match else None
                clean_msg = re.sub(r"\(\d{1,2}/\d{1,2}\)\d{2}:\d{2}", "", msg).strip()

                popup_html = f"""
                <div style='font-size:14px; width:260px; line-height:1.4;'>
                    <b>{type_info}</b><br>{clean_msg}
                    {f"<br>🕒 Reported at: {reported_time}" if reported_time else ""}
                </div>
                """
                folium.Marker(
                    [lat, lon],
                    popup=folium.Popup(popup_html, max_width=300, min_width=250),
                    icon=folium.Icon(color="red", icon="info-sign"),
                ).add_to(sg_map)

    sg_map.fit_bounds(sg_bounds)
    return sg_map._repr_html_()

@app.route("/traffic", methods=["GET", "POST"])
@app.route("/", methods=["GET", "POST"])
def traffic_dashboard():
    search_query = request.form.get("search", "").strip() if request.method == "POST" else ""
    selected_type = request.form.get("type", "").strip() if request.method == "POST" else ""
    selected_road = request.form.get("road", "").strip() if request.method == "POST" else ""
    clear_filter = request.form.get("clear") if request.method == "POST" else None

    with traffic_engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM incidents", conn)

    if not df.empty:
        df["RoadCategory"] = df["Message"].apply(extract_road)
    else:
        df["RoadCategory"] = ""

    road_options = sorted([r for r in df["RoadCategory"].dropna().unique() if r])
    type_options = sorted([t for t in df["Type"].dropna().unique() if t])

    if clear_filter:
        search_query = selected_type = selected_road = ""

    filtered = df.copy()
    if search_query:
        mask = filtered["Message"].str.contains(search_query, case=False, na=False) | \
               filtered["RoadCategory"].str.contains(search_query, case=False, na=False)
        filtered = filtered[mask]
    if selected_type:
        filtered = filtered[filtered["Type"] == selected_type]
    if selected_road:
        filtered = filtered[filtered["RoadCategory"] == selected_road]

    total_incidents = len(filtered)
    most_road = filtered["RoadCategory"].value_counts().idxmax() if not filtered.empty and not filtered[
        "RoadCategory"].dropna().empty else "N/A"
    most_type = filtered["Type"].value_counts().idxmax() if not filtered.empty and not filtered[
        "Type"].dropna().empty else "N/A"
    type_counts = filtered["Type"].value_counts().to_dict() if not filtered.empty else {}
    no_results = filtered.empty

    filtered_html = build_traffic_map_from_df(filtered)

    return render_template(
        "traffic_main.html",
        filtered_html=filtered_html,
        last_update=traffic_last_update,
        total_incidents=total_incidents,
        most_road=most_road,
        most_type=most_type,
        type_options=type_options,
        road_options=road_options,
        search_query=search_query,
        type_query=selected_type,
        road_query=selected_road,
        type_counts=type_counts,
        no_results=no_results
    )

@app.route("/traffic_pie_chart")
def traffic_pie_chart():
    """Interactive pie chart showing traffic incidents by type."""
    import plotly.express as px
    import plotly.io as pio

    with traffic_engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM incidents", conn)

    if df.empty:
        return "<h3>No data available for pie chart yet.</h3>"

    def extract_area(msg):
        if not msg:
            return ""
        m = re.search(r"(?:on|at|along|near|before|after)\s+([^,().-]+)", msg, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    df["Area"] = df["Message"].apply(extract_area).fillna("Unknown")

    type_groups = df.groupby("Type")
    type_list, count_list, hover_texts = [], [], []

    for incident_type, group in type_groups:
        count = len(group)
        areas = sorted(set(group["Area"].dropna()) - {""})
        area_lines = "<br>".join(f"• {a}" for a in areas[:10])
        hover_text = (
            f"<b>{incident_type}</b><br>"
            f"Incidents: {count}<br>"
            f"<b>Areas involved:</b><br>{area_lines}"
        )
        type_list.append(incident_type)
        count_list.append(count)
        hover_texts.append(hover_text)

    fig = px.pie(
        names=type_list,
        values=count_list,
        title="Traffic Incidents by Type (Hover for Details)",
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    fig.update_traces(
        hoverinfo="text",
        hovertemplate="%{customdata}",
        textinfo="percent",
        customdata=hover_texts
    )
    fig.update_layout(width=800, height=450, showlegend=True)

    chart_html = pio.to_html(fig, full_html=False)

    return render_template("traffic_pie_chart.html", chart_html=chart_html, last_update=traffic_last_update)


    

    # ==================== BUS ROUTES MODULE ====================
#   service = request.args.get("service")
#     direction = request.args.get("direction", 1)
#     conn = sqlite3.connect(BUS_DB_FILE)
#     c = conn.cursor()
#     c.execute("SELECT ServiceNo, Direction, StopSequence, BusStopCode FROM bus_routes WHERE ServiceNo = ? AND Direction = ? ORDER BY StopSequence", (service, direction))
#     rows = c.fetchall()
#     conn.close()
#     return jsonify([
#         {"ServiceNo": r[0], "Direction": r[1], "StopSequence": r[2], "BusStopCode": r[3]}
#         for r in rows
#     ])

# Bus Routes API endpoints from local database 
# @app.route("/api/bus_route/<service_no>/<bus_stop_code>")
# def get_bus_route(service_no, bus_stop_code):
#     try:
#         # ✅ Query local database instead of API
#         conn = sqlite3.connect(BUS_DB_FILE)
#         c = conn.cursor()
        
#         c.execute("""
#             SELECT ServiceNo, Direction, StopSequence, BusStopCode, Distance 
#             FROM bus_routes 
#             WHERE ServiceNo = ? 
#             ORDER BY Direction, StopSequence
#         """, (service_no,))
        
#         route_rows = c.fetchall()
#         conn.close()
        
#         if not route_rows:
#             return jsonify({"error": "Route not found"}), 404
        
#         # Convert to dict format (same as API response)
#         routes = []
#         for row in route_rows:
#             routes.append({
#                 "ServiceNo": row[0],
#                 "Direction": row[1],
#                 "StopSequence": row[2],
#                 "BusStopCode": row[3],
#                 "Distance": row[4]
#             })
        
#         # Normalize stop code
#         bus_stop_code = str(bus_stop_code).strip()

#         # Find the current bus stop
#         current_stop_info = None
#         for route in routes:
#             if str(route.get("BusStopCode", "")).strip() == bus_stop_code:
#                 current_stop_info = route
#                 break
        
#         if not current_stop_info:
#             return jsonify({"error": f"Bus stop {bus_stop_code} not found on route"}), 404
        
#         # Get current direction and sequence
#         current_direction = current_stop_info.get("Direction")
#         current_sequence = current_stop_info.get("StopSequence")
        
#         # Filter routes from current stop onwards
#         filtered_routes = [
#             route for route in routes
#             if route.get("Direction") == current_direction 
#             and route.get("StopSequence") >= current_sequence
#         ]

#         print(f"\n=== Bus Route Filtering Info ===")
#         print(f"Service: {service_no}, Current Stop: {bus_stop_code}")
#         print(f"Direction: {current_direction}, Current Sequence: {current_sequence}")
#         print(f"Total stops for this service: {len(routes)}")
#         print(f"Stops after filtering: {len(filtered_routes)}")
#         print(filtered_routes)

#         route_data = []
#         not_found_stops = []
#         conn = get_bus_db_connection()
#         c = conn.cursor()

#            # Sort by sequence
#         route_data.sort(key=lambda x: x["sequence"])
        
#         if not route_data:
#             return jsonify({"error": "No valid route data found"}), 404
        
#         # Return data to frontend for map rendering
#         return jsonify({
#             "service_no": service_no,
#             "direction": current_direction,
#             "current_stop": bus_stop_code,
#             "remaining_stops": route_data,
#             "stops_remaining": len(route_data)
#         })
        
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


# Retrieving bus route information using API pagination 

@app.route("/api/bus_route/<service_no>/<bus_stop_code>")
def get_bus_route(service_no, bus_stop_code):
    """
    Fetch bus route for a specific service number from LTA DataMall API.
    Returns route stops with coordinates in sequence.
    """
    try:
        # Normalize service number (strip whitespace, handle leading zeros)
        service_no = str(service_no).strip()
        
        # LTA DataMall API endpoint for bus routes
        # Fetching all routes for all bus services with pagination
        all_routes = []
        skip = 0
        
        while True:
            r = requests.get(
                f"{BASE_URL}/BusRoutes?$skip={skip}",
                headers=BUS_HEADERS,
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            
            page_routes = data.get("value", [])
            if not page_routes:
                break
            
            # Normalize and filter routes by service number
            for route in page_routes:
                route_service_no = str(route.get("ServiceNo", "")).strip()
                if route_service_no == service_no:
                    all_routes.append(route)
            
            # If we got less than 500 records, we've reached the last page
            if len(page_routes) < 500:
                break
            
            skip += 500
        
        print(f"Found {len(all_routes)} routes for service {service_no}")
        
        if not all_routes:
            return jsonify({"error": "Route not found"}), 404
            
        # Normalize stop code to string (remove any whitespace, ensure consistent format)
        bus_stop_code = str(bus_stop_code).strip()

        # Find the direction of the current bus stop 
        current_stop_info = None
        for route in all_routes:
            if str(route.get("BusStopCode", "")).strip() == bus_stop_code:
                current_stop_info = route
                break

        # If current stop is not found
        if not current_stop_info:
            return jsonify({"error": f"Bus stop {bus_stop_code} not found on route"}), 404
        
        # Get the current bus direction and the bus stop sequence no.
        current_direction = current_stop_info.get("Direction")
        current_sequence = current_stop_info.get("StopSequence")
            
        # The sequence of bus-stops from current stop must be greater or equal to current stop and same direction 
        # 1. Stops with sequence >= current Stop && direction == current stop direction 
        # 2. Arrange sequence in ascending order 
        filtered_routes = [
            route for route in all_routes
            if route.get("Direction") == current_direction 
            and route.get("StopSequence") >= current_sequence
        ]

        # Log filtering info
        print(f"\n=== Bus Route Filtering Info ===")
        print(f"Service: {service_no}, Current Stop: {bus_stop_code}")
        print(f"Direction: {current_direction}, Current Sequence: {current_sequence}")
        print(f"Total stops in full route: {len(all_routes)}")
        print(f"Stops after filtering: {len(filtered_routes)}")
        print(filtered_routes)

        route_data = []
        not_found_stops = []
        conn = get_bus_db_connection()
        c = conn.cursor()

        for route in filtered_routes:
            stop_sequence = route.get("StopSequence", 0)
            route_bus_stop_code = str(route.get("BusStopCode", "")).strip()

            if not route_bus_stop_code:
                continue

            # Get coordinates from database
            c.execute(
                "SELECT lat, lon, description, road, code FROM bus_stops WHERE code = ?",
                (route_bus_stop_code,)
            )
            stop_info = c.fetchone()

            # # Try with padding if not found
            # if not stop_info and len(route_bus_stop_code) < 5:
            #     padded_code = route_bus_stop_code.zfill(5)
            #     c.execute(
            #         "SELECT lat, lon, description, road, code FROM bus_stops WHERE code = ?",
            #         (padded_code,)
            #     )
            #     stop_info = c.fetchone()
            
            # # Try without leading zeros if not found
            # if not stop_info and route_bus_stop_code.startswith('0'):
            #     unpadded_code = route_bus_stop_code.lstrip('0') or '0'
            #     c.execute(
            #         "SELECT lat, lon, description, road, code FROM bus_stops WHERE code = ?",
            #         (unpadded_code,)
            #     )
            #     stop_info = c.fetchone()

            # Log if stop not found in database
            if not stop_info:
                not_found_stops.append({
                    "stop_code": route_bus_stop_code,
                    "sequence": stop_sequence
                })
                continue

            # Add stop data to route_data if found
            if stop_info[0] is not None and stop_info[1] is not None:
                try:
                    lat, lon = float(stop_info[0]), float(stop_info[1])
                    actual_stop_code = str(stop_info[4]) if len(stop_info) > 4 else route_bus_stop_code
                    route_data.append({
                        "sequence": stop_sequence,
                        "stop_code": actual_stop_code,
                        "lat": lat,
                        "lon": lon,
                        "description": stop_info[2] or "",
                        "road": stop_info[3] or "",
                        "distance": route.get("Distance", 0)
                    })
                except (ValueError, TypeError, IndexError):
                    not_found_stops.append({
                        "stop_code": route_bus_stop_code,
                        "sequence": stop_sequence
                    })
        
        conn.close()

        # Log stops not found in database
        if not_found_stops:
            print(f"\n⚠️  Stops NOT FOUND in database ({len(not_found_stops)}):")
            for stop in not_found_stops:
                print(f"  - Stop Code: {stop['stop_code']}, Sequence: {stop['sequence']}")
        else:
            print(f"✓ All {len(filtered_routes)} filtered stops found in database")
        
        print(f"Final route data: {len(route_data)} stops")
        print("=" * 40 + "\n")
        
        # Sort by sequence
        route_data.sort(key=lambda x: x["sequence"])
        
        if not route_data:
            return jsonify({"error": "No valid route data found"}), 404
        
        # Return data to frontend for map rendering
        return jsonify({
            "service_no": service_no,
            "direction": current_direction,
            "current_stop": bus_stop_code,
            "remaining_stops": route_data,
            "stops_remaining": len(route_data)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ==================== MAIN ====================
if __name__ == "__main__":
    print("🚀 Initializing unified transport analytics system...")
    
    try:
        # Initialize bus module
        init_bus_db()
        load_bus_stops()
        load_bus_routes()
        
        threading.Thread(target=load_bus_stops, daemon=True).start()
        
        # Start background threads
        threading.Thread(target=background_bus_collector, daemon=True).start()
        threading.Thread(target=fetch_and_store_traffic_loop, daemon=True).start()
        
        print("🌐 Running unified app at http://localhost:5000")
        print("📍 Traffic Dashboard: http://localhost:5000/traffic")
        print("🚌 Bus Dashboard: http://localhost:5000/bus")
        print("💡 If the page doesn't load, check that port 5000 is available")
        
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e) or "port" in str(e).lower():
            print(f"❌ Error: Port 5000 is already in use!")
            print("   Please stop the other application using port 5000, or change the port in app.py")
            print(f"   Details: {e}")
        else:
            print(f"❌ Error starting server: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()