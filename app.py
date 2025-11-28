import os, sqlite3, requests, threading, time, re
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, current_app
from dotenv import load_dotenv
import pandas as pd
import folium
from sqlalchemy import create_engine, Table, Column, String, Float, MetaData, DateTime
from charts import charts_bp

# Import auth module
from database import init_users_db, init_bus_db, get_db_connection, get_bus_db_connection, IS_PRODUCTION
from auth import auth_bp, login_required, current_user

#Chatbot module
from chatbot import chatbot_bp 

# Initialize users database
init_users_db()

# Load environment variables
load_dotenv()

from datetime import timedelta

# ==================== CONFIGURATION ====================
API_KEY = os.getenv("API_KEY")
TRAFFIC_API_KEY = os.getenv("TRAFFIC_API_KEY") or API_KEY
BASE_URL = os.getenv("BASE_URL", "https://datamall2.mytransport.sg/ltaodataservice")
TRAFFIC_API_URL = os.getenv("TRAFFIC_API_URL", "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents")

BUS_HEADERS = {"AccountKey": API_KEY, "accept": "application/json"}
TRAFFIC_HEADERS = {"AccountKey": TRAFFIC_API_KEY, "accept": "application/json"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUS_DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

# ==================== FLASK APP ===========================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise ValueError("SECRET_KEY must be set!")

app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.register_blueprint(auth_bp)
# ==================== CHATBOT blueprint ====================
app.register_blueprint(chatbot_bp)

# ==================== Charts blueprint ====================
app.register_blueprint(charts_bp)

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

# Load bus stops
def load_bus_stops():
    conn = get_bus_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM bus_stops")
    if c.fetchone()[0] > 0:
        conn.close()
        return # Exit if data exists 

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

# 

# "service_no": service_no,
#             "direction": current_direction,
#             "current_stop": bus_stop_code,
#             "remaining_stops": route_data,
#             "stops_remaining": len(route_data)
# Load bus routes


# Loading bus routes on start-up 
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

     # If data already exist in the table then skip 
    c.execute("SELECT COUNT(*) FROM bus_routes")
    if c.fetchone()[0] > 0:
        conn.close()
        print("✅ Bus routes already cached.")
        return #exit if data exist

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

# Build bus_routes_by_service cache from SQLite
def build_bus_routes_cache():
    print("🔧 Building bus_routes_by_service cache (deduplicated)...")

    conn = sqlite3.connect(BUS_DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT ServiceNo, Direction, StopSequence, BusStopCode
        FROM bus_routes
        ORDER BY ServiceNo, Direction, StopSequence
    """)

    rows = c.fetchall()
    conn.close()

    cache = {}

    # We deduplicate using (svc, direction, stop_seq) keys
    temp = {}

    for svc, direction, seq, stop in rows:
        key = (svc, direction, seq)
        if key not in temp:
            temp[key] = stop  # keep first occurrence only

    # Now group by (svc, direction)
    for (svc, direction, seq), stop in temp.items():
        svc_key = (svc, direction)
        if svc_key not in cache:
            cache[svc_key] = []
        cache[svc_key].append((stop, seq))

    # Sort each service/direction properly
    for svc_key in cache:
        cache[svc_key] = sorted(cache[svc_key], key=lambda x: x[1])

    print(f"✅ bus_routes_by_service built: {len(cache)} services loaded")
    return cache

# Global cache storage
bus_routes_by_service = {}

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


#with fixed timezone issues
@app.route("/bus_arrivals/<code>")
@login_required
def bus_arrivals(code):
    try:
        # Call LTA API
        r = requests.get(
            f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
            headers=BUS_HEADERS,
            timeout=10
        )
        r.raise_for_status()
        
        data = r.json()
        
        # Use Singapore timezone for proper comparison
        from datetime import timezone, timedelta
        sg_tz = timezone(timedelta(hours=8))
        now = datetime.now(sg_tz)  # ← Singapore time, not UTC!
        
        results = []
        
        for s in data.get("Services", []):
            waits = []
            for key in ["NextBus", "NextBus2", "NextBus3"]:
                eta_str = s[key].get("EstimatedArrival")
                if eta_str:
                    try:
                        # Parse with timezone info intact
                        eta_time = datetime.fromisoformat(eta_str)
                        
                        # Calculate difference in minutes
                        diff = (eta_time - now).total_seconds() / 60
                        
                        if diff >= 0:
                            waits.append(round(diff, 1))
                    except Exception as e:
                        print(f"Error parsing time: {e}")
                        continue
            
            results.append({
                "service": s["ServiceNo"],
                "type": s["NextBus"].get("Type", "Unknown"),
                "eta": waits
            })
        
        return jsonify(results)
        
    except Exception as e:
        print(f"Bus arrivals error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bus-arrivals/<bus_stop_code>")
@login_required
def get_bus_arrivals_api(bus_stop_code):
    """API endpoint for bus arrivals"""
    try:
        # Get arrivals from LTA API
        import requests
        from datetime import datetime, timezone, timedelta
        
        LTA_API_KEY = os.environ.get('LTA_API_KEY')
        
        headers = {
            'AccountKey': LTA_API_KEY,
            'accept': 'application/json'
        }
        
        response = requests.get(
            'https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival',
            headers=headers,
            params={'BusStopCode': bus_stop_code},
            timeout=10
        )
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'LTA API returned status {response.status_code}'
            }), 500
        
        data = response.json()
        services = data.get('Services', [])
        
        # Format response
        formatted_services = []
        sg_tz = timezone(timedelta(hours=8))
        now = datetime.now(sg_tz)
        
        for service in services:
            buses = []
            for bus_key in ['NextBus', 'NextBus2', 'NextBus3']:
                bus = service.get(bus_key, {})
                if bus and bus.get('EstimatedArrival'):
                    eta_str = bus.get('EstimatedArrival')
                    eta_time = datetime.fromisoformat(eta_str)
                    diff_minutes = int((eta_time - now).total_seconds() / 60)
                    
                    if diff_minutes >= 0:
                        buses.append({
                            'eta': eta_str,
                            'minutes': diff_minutes,
                            'load': bus.get('Load', 'N/A'),
                            'type': bus.get('Type', 'SD'),
                            'feature': bus.get('Feature', '')
                        })
            
            if buses:
                formatted_services.append({
                    'service_no': service.get('ServiceNo'),
                    'operator': service.get('Operator'),
                    'buses': buses
                })
        
        return jsonify({
            'success': True,
            'bus_stop_code': bus_stop_code,
            'services': formatted_services,
            'timestamp': datetime.now(sg_tz).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting bus arrivals: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
def get_user_locations():
    """Get user's saved locations from PostgreSQL"""
    
    # TEMPORARY: Hardcode user_id = 7 for now
    user_id = 7
    
    print(f"[DEBUG] Getting locations for user_id: {user_id}")
    
    # Connect to PostgreSQL
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get locations for this user
        if IS_PRODUCTION:
            cursor.execute("""
                SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = %s
                ORDER BY is_favourite DESC, id DESC
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = ?
                ORDER BY is_favourite DESC, id DESC
            """, (user_id,))
        
        rows = cursor.fetchall()
        print(f"[DEBUG] Found {len(rows)} locations")
        
        # CRITICAL: Check if rows are dicts or tuples
        if rows and isinstance(rows[0], dict):
            # Using RealDictCursor - access by key
            locations = []
            for row in rows:
                locations.append({
                    "id": row['id'],
                    "label": row['label'],
                    "latitude": float(row['latitude']) if row['latitude'] else None,
                    "longitude": float(row['longitude']) if row['longitude'] else None,
                    "address": row['address'],
                    "postal_code": row['postal_code'],
                    "is_favourite": bool(row['is_favourite'])
                })
        else:
            # Using regular cursor - access by index
            locations = []
            for row in rows:
                locations.append({
                    "id": row[0],
                    "label": row[1],
                    "latitude": float(row[2]) if row[2] else None,
                    "longitude": float(row[3]) if row[3] else None,
                    "address": row[4],
                    "postal_code": row[5],
                    "is_favourite": bool(row[6])
                })
        
        cursor.close()
        conn.close()
        
        print(f"[DEBUG] Returning {len(locations)} locations")
        for loc in locations:
            print(f"[DEBUG] Location: {loc['label']} at ({loc['latitude']}, {loc['longitude']})")
        
        return jsonify(locations)
        
    except Exception as e:
        print(f"[ERROR] Exception in get_user_locations: {e}")
        import traceback
        traceback.print_exc()
        try:
            cursor.close()
            conn.close()
        except:
            pass
        return jsonify([])

@app.route("/api/nearby_bus_stops")
def get_nearby_bus_stops():
    """Get bus stops near a given location"""
    
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))
        radius_km = float(request.args.get("radius", 0.5))
    except (TypeError, ValueError) as e:
        print(f"[ERROR] Invalid parameters: {e}")
        return jsonify({"success": False, "error": "Invalid parameters"}), 400
    
    print(f"[DEBUG] Searching for bus stops near ({latitude}, {longitude}) within {radius_km}km")
    
    try:
        # Connect to SQLite bus database
        bus_db_path = os.path.join(BASE_DIR, "database", "bus_data.db")
        
        if not os.path.exists(bus_db_path):
            print(f"[ERROR] Bus database not found at {bus_db_path}")
            return jsonify({"success": False, "error": "Bus database not found"}), 500
        
        bus_conn = sqlite3.connect(bus_db_path)
        bus_cursor = bus_conn.cursor()
        
        # FIXED: Use correct table and column names
        bus_cursor.execute("""
            SELECT code, description, lat, lon, road
            FROM bus_stops
            WHERE lat IS NOT NULL AND lon IS NOT NULL
        """)
        
        all_stops = bus_cursor.fetchall()
        bus_conn.close()
        
        print(f"[DEBUG] Total bus stops in database: {len(all_stops)}")
        
        # Calculate distances using Haversine formula
        from math import radians, sin, cos, sqrt, atan2
        
        nearby_stops = []
        R = 6371.0  # Earth radius in km
        
        for stop in all_stops:
            stop_code, description, stop_lat, stop_lon, road_name = stop
            
            try:
                stop_lat = float(stop_lat)
                stop_lon = float(stop_lon)
            except:
                continue
            
            # Singapore bounds check
            if not (1.0 <= stop_lat <= 1.5 and 103.5 <= stop_lon <= 104.1):
                continue
            
            # Haversine distance calculation
            lat1 = radians(latitude)
            lon1 = radians(longitude)
            lat2 = radians(stop_lat)
            lon2 = radians(stop_lon)
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            if distance <= radius_km:
                nearby_stops.append({
                    "BusStopCode": stop_code,
                    "Description": description,
                    "Latitude": stop_lat,
                    "Longitude": stop_lon,
                    "RoadName": road_name or "N/A",
                    "Distance": round(distance, 3)
                })
        
        # Sort by distance and limit to 20
        nearby_stops.sort(key=lambda x: x["Distance"])
        nearby_stops = nearby_stops[:20]
        
        print(f"[DEBUG] Found {len(nearby_stops)} bus stops within {radius_km}km")
        
        return jsonify({
            "success": True,
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "count": len(nearby_stops),
            "stops": nearby_stops
        })
        
    except Exception as e:
        print(f"[ERROR] Exception in get_nearby_bus_stops: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

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
traffic_last_update = ""

# Traffic database - PostgreSQL in production, SQLite in development
TRAFFIC_DB_FILE = os.path.join(BASE_DIR, "database/TrafficIncidents.db")
traffic_engine = create_engine(f"sqlite:///{TRAFFIC_DB_FILE}", future=True)

if IS_PRODUCTION:
    print("✅ Using SQLite for traffic data (Production - Local Cache)")
else:
    print("✅ Using SQLite for traffic data (Development)")

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

    # Handle empty dataframe
    if df.empty:
        # No traffic data - show empty map
        sg_map = folium.Map(location=[1.3521, 103.8198], zoom_start=12)
        empty_html = sg_map._repr_html_()
        
        return render_template(
            "traffic_main.html",
            filtered_html=empty_html,
            last_update="No data available yet",
            total_incidents=0,
            most_road="N/A",
            most_type="N/A",
            type_options=[],
            road_options=[],
            search_query="",
            type_query="",
            road_query="",
            type_counts={},
            no_results=True
        )

    # Process data only if not empty
    df["RoadCategory"] = df["Message"].apply(extract_road)

    # Safely get options
    road_options = sorted([r for r in df["RoadCategory"].dropna().unique() if r]) if "RoadCategory" in df.columns else []
    type_options = sorted([t for t in df["Type"].dropna().unique() if t]) if "Type" in df.columns else []

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
    most_road = filtered["RoadCategory"].value_counts().idxmax() if not filtered.empty and not filtered["RoadCategory"].dropna().empty else "N/A"
    most_type = filtered["Type"].value_counts().idxmax() if not filtered.empty and not filtered["Type"].dropna().empty else "N/A"
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

# Retrieving bus route information from LOCAL DATABASE
@app.route("/api/bus_route/<service_no>/<bus_stop_code>")
def get_bus_route(service_no, bus_stop_code):
    """
    Fetch bus route for a specific service number from LOCAL DATABASE.
    Returns route stops with coordinates in sequence.
    """
    try:
        # Normalize service number (strip whitespace, handle leading zeros)
        service_no = str(service_no).strip()
        
        # FETCH FROM LOCAL DATABASE instead of API
        conn = get_bus_db_connection()
        c = conn.cursor()
        
        # Query all routes for this service number
        c.execute("""
            SELECT ServiceNo, Direction, StopSequence, BusStopCode, Distance
            FROM bus_routes
            WHERE ServiceNo = ?
            ORDER BY Direction, StopSequence
        """, (service_no,))
        
        route_rows = c.fetchall()
        
        
        # Convert database rows to dict format (same as API response)
        all_routes = []
        for row in route_rows:
            all_routes.append({
                "ServiceNo": row[0],
                "Direction": row[1],
                "StopSequence": row[2],
                "BusStopCode": row[3],
                "Distance": row[4]
            })
        
        print(f"Found {len(all_routes)} routes for service {service_no}")
        print(all_routes)
        
        if not all_routes:
            conn.close()
            return jsonify({"error": "Route not found"}), 404
            
        # Normalize stop code to string (remove any whitespace, ensure consistent format)
        bus_stop_code = str(bus_stop_code).strip()                    

        # Find ALL occurrences of current stop (handles interchanges)
        matching_stops = []
        for route in all_routes:
            # Add all the matching bus stop codes to matching_stops array;
            if str(route.get("BusStopCode", "")).strip() == bus_stop_code:
                matching_stops.append(route)
        # If current stop is not found in list 
        if not matching_stops:
            conn.close()
            return jsonify({"error": f"Bus stop {bus_stop_code} not found on route"}), 404
        
        print(f"✅ Found {len(matching_stops)} direction(s) for stop {bus_stop_code}")

        # if multiple directions exist then pick the one with more stops ahead 
        current_stop_info = None

        if len(matching_stops) == 1:
            # Only one direction exist
            current_stop_info = matching_stops[0]
            print(f"Single direction found: Direction {current_stop_info['Direction']}")
        else:
            # First, try to find sequence = 1, then its 
            for stop in matching_stops:
                if stop['StopSequence'] == 1:
                    current_stop_info = stop
                    break
            
            print(f"🔀 Multiple directions found at interchange:")
            for stop in matching_stops:
                print(f"   Direction {stop['Direction']}: Sequence {stop['StopSequence']}")
            print(f"✅ Selected Direction {current_stop_info['Direction']} (Sequence {current_stop_info['StopSequence']})")

        # Get the current bus direction and the bus stop sequence no.
        current_direction = current_stop_info.get("Direction")
        current_sequence = current_stop_info.get("StopSequence")
            

        #CHANGED: Get ALL stops for this direction
        full_route = [
            route for route in all_routes
            if route.get("Direction") == current_direction
        ]

        #Changed: Also get remaining routes 
        remaining_routes = [
            route for route in all_routes
            if route.get("Direction") == current_direction 
            and route.get("StopSequence") > current_sequence
        ]

        # Log filtering info
        print(f"\n=== Bus Route Filtering Info ===")
        print(f"Service: {service_no}, Current Stop: {bus_stop_code}")
        print(f"Direction: {current_direction}, Current Sequence: {current_sequence}")
        print(f"Full route (same direction): {len(full_route)}")
        print(f"Stops remaining from current bus-stop: {len(remaining_routes)}")

        route_data = []
        not_found_stops = []

        # Process FULL route instead of filtered
        for route in full_route:
            stop_sequence = route.get("StopSequence", 0)
            route_bus_stop_code = str(route.get("BusStopCode", "")).strip()

            if not route_bus_stop_code:
                continue

            # Get coordinates from database (using same connection)
            c.execute(
                "SELECT lat, lon, description, road, code FROM bus_stops WHERE code = ?",
                (route_bus_stop_code,)
            )
            stop_info = c.fetchone()

            # Log if stop not found in database
            if not stop_info:
                not_found_stops.append({
                    "stop_code": route_bus_stop_code,
                    "sequence": stop_sequence
                })
                continue

            # Add stop data to route_data if found and map to lat and long from 
            if stop_info[0] is not None and stop_info[1] is not None:
                try:
                    lat, lon = float(stop_info[0]), float(stop_info[1])
                    actual_stop_code = str(stop_info[4]) if len(stop_info) > 4 else route_bus_stop_code

                    # Mark if this is the current stop
                    is_current = (route_bus_stop_code == bus_stop_code)

                    route_data.append({
                        "sequence": stop_sequence,
                        "stop_code": actual_stop_code,
                        "lat": lat,
                        "lon": lon,
                        "description": stop_info[2] or "",
                        "road": stop_info[3] or "",
                        "distance": route.get("Distance", 0),
                        "is_current": is_current
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
            print(f"✓ All {len(full_route)} filtered stops found in database")
        
        print(f"Final route data: {len(route_data)} stops")
        print("=" * 40 + "\n")
        
        # Sort by sequence
        route_data.sort(key=lambda x: x["sequence"])
        
        if not route_data:
            return jsonify({"error": "No valid route data found"}), 404
        
        # Return data to frontend for map rendering (SAME FORMAT)
        return jsonify({
            "service_no": service_no,
            "direction": current_direction,
            "current_stop": bus_stop_code,
            "full_route": route_data,
            "stops_remaining": len(remaining_routes)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/settings")
@login_required
def settings():
    user = get_current_user()
    locations = get_user_locations(user["id"])
    google_maps_api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    return render_template(
        "settings.html",
        user=user,
        locations=locations,
        google_maps_api_key=google_maps_api_key,
    )

# ==================== MAIN ====================
if __name__ == "__main__":
    print("🚀 Initializing unified transport analytics system...")
    
    # Running code sychronously 
    try:
        # Initialize bus module
        init_bus_db()
        load_bus_stops()
        load_bus_routes()
        
        bus_routes_by_service = build_bus_routes_cache()
        # ROUTE_GRAPH = build_route_graph_from_cache(bus_routes_by_service)

        
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
