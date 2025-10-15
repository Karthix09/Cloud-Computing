import os, sqlite3, requests, threading, time
from datetime import datetime
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

# Shows bus Dashboard plus the history 

# ---------------- CONFIG ----------------
load_dotenv()
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://datamall2.mytransport.sg/ltaodataservice")
HEADERS = {"AccountKey": API_KEY, "accept": "application/json"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")


app = Flask(__name__)

# ---------------- DB SETUP ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
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

# ---------------- LOAD BUS STOPS ----------------
def load_bus_stops():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM bus_stops")
    if c.fetchone()[0] > 0:
        conn.close(); return
    print("📥 Loading bus stops ...")
    skip = 0
    while True:
        r = requests.get(f"{BASE_URL}/BusStops?$skip={skip}", headers=HEADERS, timeout=20)
        data = r.json().get("value", [])
        if not data: break
        for s in data:
            c.execute("INSERT OR REPLACE INTO bus_stops VALUES (?,?,?,?,?)",
                      (s["BusStopCode"], s["Description"], s["RoadName"],
                       s["Latitude"], s["Longitude"]))
        conn.commit()
        if len(data) < 500: break
        skip += 500
    conn.close()
    print("✅ Bus stops cached.")

# ---------------- BACKGROUND DATA COLLECTOR ----------------
def get_all_stops():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT code FROM bus_stops")
    stops = [x[0] for x in c.fetchall()]
    conn.close()
    return stops

def collect_arrivals():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    stops = get_all_stops()
    now = datetime.now()

    for code in stops:
        try:
            r = requests.get(f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
                             headers=HEADERS, timeout=10)
            data = r.json().get("Services", [])
            for s in data:
                service = s["ServiceNo"]
                btype = s["NextBus"].get("Type", "Unknown")
                for key in ["NextBus", "NextBus2", "NextBus3"]:
                    t = s[key].get("EstimatedArrival")
                    if not t: continue
                    eta = datetime.fromisoformat(t.replace("+08:00",""))
                    diff = (eta - now).total_seconds() / 60
                    if diff >= 0:
                        # Insert only if changed
                        c.execute("""SELECT eta_min FROM bus_arrivals
                                     WHERE stop_code=? AND service=?
                                     ORDER BY timestamp DESC LIMIT 1""",
                                  (code, service))
                        last = c.fetchone()
                        if not last or abs(last[0] - diff) > 0.3:
                            c.execute("""
                                INSERT INTO bus_arrivals (stop_code, service, eta_min, bus_type, timestamp)
                                VALUES (?,?,?,?,?)
                            """, (code, service, round(diff,1), btype, now.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            time.sleep(0.4)
        except Exception as e:
            print(f"⚠️ Error fetching stop {code}: {e}")
    conn.close()
    print(f"✅ Collector cycle done at {datetime.now().strftime('%H:%M:%S')}")

def background_collector():
    print("🧠 Background collector started (every 1 min).")
    while True:
        try:
            collect_arrivals()
        except Exception as e:
            print("Collector failed:", e)
        time.sleep(60)

# ---------------- API ENDPOINTS ----------------
@app.route("/bus_stops")
def bus_stops():
    q = request.args.get("query", "").strip().lower()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if q:
        like = f"%{q}%"
        c.execute("""SELECT code,description,road,lat,lon FROM bus_stops
                     WHERE LOWER(description) LIKE ? OR LOWER(road) LIKE ? OR code LIKE ?""",
                  (like, like, like))
    else:
        c.execute("SELECT code,description,road,lat,lon FROM bus_stops")
    rows = c.fetchall(); conn.close()
    return jsonify([{"code":r[0],"desc":r[1],"road":r[2],"lat":r[3],"lon":r[4]} for r in rows])

@app.route("/bus_arrivals/<code>")
def bus_arrivals(code):
    try:
        r = requests.get(f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
                         headers=HEADERS, timeout=10)
        data = r.json()
        now = datetime.now()
        results = []
        for s in data.get("Services", []):
            waits = []
            for key in ["NextBus","NextBus2","NextBus3"]:
                t = s[key].get("EstimatedArrival")
                if t:
                    diff = (datetime.fromisoformat(t.replace("+08:00","")) - now).total_seconds()/60
                    if diff >= 0: waits.append(round(diff,1))
            results.append({"service":s["ServiceNo"],"type":s["NextBus"].get("Type"),"eta":waits})

        # Log
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for s in results:
            for eta in s["eta"]:
                c.execute("INSERT INTO bus_arrivals (stop_code, service, eta_min, bus_type) VALUES (?,?,?,?)",
                          (code, s["service"], eta, s["type"]))
        conn.commit(); conn.close()
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/history/<stop_code>")
def history(stop_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%H', timestamp) as hour, service, AVG(eta_min)
        FROM bus_arrivals
        WHERE stop_code = ? AND timestamp >= datetime('now', '-1 day')
        GROUP BY hour, service
        ORDER BY hour ASC
    """, (stop_code,))
    rows = c.fetchall(); conn.close()

    data = {}
    for hour, svc, eta in rows:
        data.setdefault(svc, []).append({"x": int(hour), "y": round(eta,2)})
    return render_template("bus_history.html", stop_code=stop_code, data=data)

@app.route("/history/all")
def history_all():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%H', timestamp) as hour, AVG(eta_min)
        FROM bus_arrivals
        WHERE timestamp >= datetime('now', '-1 day')
        GROUP BY hour
        ORDER BY hour ASC
    """)
    rows = c.fetchall(); conn.close()
    data = [{"x": int(hour), "y": round(avg, 2)} for hour, avg in rows]
    return render_template("bus_history_all.html", data=data)

# ---------------- FRONTEND ----------------
@app.route("/")
def bus():
    return render_template("bus_main.html")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("🚀 Initializing system...")
    init_db(); load_bus_stops()
    threading.Thread(target=background_collector, daemon=True).start()
    print("🌐 Running at http://localhost:5000")
    app.run(host="localhost", port=5000, debug=False, use_reloader=False)
