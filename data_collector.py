"""
data_collector.py
-----------------
Collects live bus arrival data across Singapore from LTA DataMall every few minutes
and stores it in the shared 'bus_data.db' used by app.py.

Make sure to:
Have a valid .env file with API_KEY and BASE_URL
Run this script alongside your Flask app (in another terminal)
"""

import os
import requests
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv

# ---------------- CONFIG ----------------
load_dotenv()

API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://datamall2.mytransport.sg/ltaodataservice")
HEADERS = {"AccountKey": API_KEY, "accept": "application/json"}

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bus_data.db")

# ---------------- HELPERS ----------------
def get_all_stops():
    """Fetch all bus stop codes from the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT code FROM bus_stops")
    stops = [x[0] for x in c.fetchall()]
    conn.close()
    return stops

def collect_arrivals():
    """Fetch arrival times from LTA API for all stops and store them."""
    stops = get_all_stops()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()

    for code in stops:
        try:
            r = requests.get(
                f"{BASE_URL}/v3/BusArrival?BusStopCode={code}",
                headers=HEADERS,
                timeout=10
            )
            data = r.json().get("Services", [])
            if not data:
                continue

            for s in data:
                service = s["ServiceNo"]
                btype = s["NextBus"].get("Type", "Unknown")

                for key in ["NextBus", "NextBus2", "NextBus3"]:
                    t = s[key].get("EstimatedArrival")
                    if not t:
                        continue
                    try:
                        eta = datetime.fromisoformat(t.replace("+08:00", ""))
                        diff = (eta - now).total_seconds() / 60
                        if diff >= 0:
                            c.execute("""
                                INSERT INTO bus_arrivals (stop_code, service, eta_min, bus_type, timestamp)
                                VALUES (?, ?, ?, ?, ?)
                            """, (code, service, round(diff, 1), btype, now.strftime("%Y-%m-%d %H:%M:%S")))
                    except Exception as inner_e:
                        print(f"⚠️ Parsing error for stop {code}: {inner_e}")

            conn.commit()
            time.sleep(0.5)  # avoid API rate limits

        except Exception as e:
            print(f"❌ Error fetching stop {code}: {e}")

    conn.close()
    print(f"✅ Completed data collection cycle at {datetime.now().strftime('%H:%M:%S')}")

# ---------------- MAIN LOOP ----------------
if __name__ == "__main__":
    print("🚀 Starting LTA Data Collector")
    print("🌐 Collecting from:", BASE_URL)
    print("💾 Using database:", DB_FILE)

    while True:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚌 Collecting nationwide bus arrival data...")
        collect_arrivals()
        print("⏳ Cycle complete, sleeping 5 minutes...\n")
        time.sleep(300)  # Wait 5 minutes before next cycle
