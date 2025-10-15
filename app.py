import os, sqlite3, requests, threading, time, re
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
import pandas as pd
import folium
from sqlalchemy import create_engine, Table, Column, String, Float, MetaData, DateTime

# Import auth module
from database import init_users_db
from auth import auth_bp, login_required, current_user, USERS_DB


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

# ==================== LOGIN REQUIRED ====================
@app.before_request
def require_login():
    open_paths = ("/login", "/register", "/logout", "/static/", "/favicon.ico")
    if request.path.startswith(open_paths):
        return
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

# ==================== BUS MODULE ====================

# Bus database setup
def init_bus_db():
    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bus_stops(
        code TEXT PRIMARY KEY, description TEXT, road TEXT, lat REAL, lon REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bus_routes(
        service TEXT, stop_code TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bus_arrivals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stop_code TEXT,
        service TEXT,
        eta_min REAL,
        bus_type TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

# Load bus stops
def load_bus_stops():
    conn = sqlite3.connect(BUS_DB_FILE)
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

# Background bus data collector
def get_all_stops():
    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()
    c.execute("SELECT code FROM bus_stops")
    stops = [x[0] for x in c.fetchall()]
    conn.close()
    return stops

def collect_bus_arrivals():
    conn = sqlite3.connect(BUS_DB_FILE)
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
    conn = sqlite3.connect(BUS_DB_FILE)
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
        conn = sqlite3.connect(BUS_DB_FILE)
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
    conn = sqlite3.connect(BUS_DB_FILE)
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
    conn = sqlite3.connect(BUS_DB_FILE)
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
    
    # Use the same database and connection method as auth.py
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    USERS_DB = os.path.join(BASE_DIR, "users.db")
    
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
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
        
        return jsonify(locations)
    except Exception as e:
        print(f"Error fetching user locations: {e}")
        return jsonify([])
    finally:
        conn.close()




# ==================== BUS FAVORITES API ====================

# Get user's favorite bus stops

@app.route("/api/bus_favorites", methods=["GET"])
@login_required
def get_bus_favorites():
    """Get current user's favorite bus stops"""
    user = current_user()
    if not user:
        return jsonify([])
    
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
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
        
        return jsonify(favorites)
    except Exception as e:
        print(f"Error fetching bus favorites: {e}")
        return jsonify([])
    finally:
        conn.close()

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
    
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO bus_favorites (user_id, bus_stop_code, bus_stop_name)
            VALUES (?, ?, ?)
        """, (user["id"], code, desc))
        conn.commit()
        return jsonify({"success": True, "message": "Added to favorites"})
    except Exception as e:
        print(f"Error adding bus favorite: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

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
    
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM bus_favorites
            WHERE user_id = ? AND bus_stop_code = ?
        """, (user["id"], code))
        conn.commit()
        return jsonify({"success": True, "message": "Removed from favorites"})
    except Exception as e:
        print(f"Error removing bus favorite: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()



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

@app.route("/traffic")
@app.route("/")
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
        textinfo="percent+label",
        customdata=hover_texts
    )
    fig.update_layout(width=800, height=450, showlegend=True)

    chart_html = pio.to_html(fig, full_html=False)

    return render_template("traffic_pie_chart.html", chart_html=chart_html, last_update=traffic_last_update)

# ==================== MAIN ====================
if __name__ == "__main__":
    print("🚀 Initializing unified transport analytics system...")
    
    # Initialize bus module
    init_bus_db()
    load_bus_stops()
    
    # Start background threads
    threading.Thread(target=background_bus_collector, daemon=True).start()
    threading.Thread(target=fetch_and_store_traffic_loop, daemon=True).start()
    
    print("🌐 Running unified app at http://localhost:5000")
    print("📍 Traffic Dashboard: http://localhost:5000/traffic")
    print("🚌 Bus Dashboard: http://localhost:5000/bus")
    
    app.run(host="localhost", port=5000, debug=False, use_reloader=False)