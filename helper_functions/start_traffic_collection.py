#used to start collection of traffic data in ec2
#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv()

import time
import sys
from datetime import datetime, timedelta
import sqlite3

print("🚦 Starting Traffic Incidents Collector with Auto-Cleanup")
print("=" * 60)

def cleanup_old_data():
    """Delete traffic incidents older than 7 days"""
    try:
        db_path = "database/TrafficIncidents.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Delete incidents older than 7 days
        seven_days_ago = datetime.now() - timedelta(days=7)
        
        cursor.execute("DELETE FROM incidents WHERE FetchedAt < ?", (seven_days_ago,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if deleted > 0:
            print(f"🧹 Cleaned up {deleted} old traffic incidents (>7 days old)")
        
        return deleted
    except Exception as e:
        print(f"⚠️  Cleanup error: {e}")
        return 0

def collect_traffic_data():
    """Fetch and store traffic incidents from LTA API"""
    import requests
    import os
    
    API_KEY = os.getenv("TRAFFIC_API_KEY") or os.getenv("API_KEY")
    TRAFFIC_URL = "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents"
    
    try:
        # Fetch from API
        r = requests.get(TRAFFIC_URL, headers={"AccountKey": API_KEY}, timeout=20)
        r.raise_for_status()
        
        data = r.json()
        incidents = data.get("value", [])
        
        if not incidents:
            print(f"ℹ️  No active traffic incidents at {datetime.now().strftime('%H:%M:%S')}")
            return 0
        
        # Store in SQLite
        db_path = "database/TrafficIncidents.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                Id TEXT PRIMARY KEY,
                Type TEXT,
                Latitude REAL,
                Longitude REAL,
                Message TEXT,
                FetchedAt TIMESTAMP
            )
        """)
        
        # Clear current incidents (they're real-time, not historical)
        cursor.execute("DELETE FROM incidents WHERE FetchedAt >= datetime('now', '-5 minutes')")
        
        # Insert new incidents
        now = datetime.now()
        inserted = 0
        
        for inc in incidents:
            incident_id = inc.get('IncidentID') or f"{inc.get('Type')}_{inc.get('Latitude')}_{inc.get('Longitude')}"
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO incidents (Id, Type, Latitude, Longitude, Message, FetchedAt)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    incident_id,
                    inc.get('Type'),
                    inc.get('Latitude'),
                    inc.get('Longitude'),
                    inc.get('Message'),
                    now
                ))
                inserted += 1
            except Exception as e:
                print(f"⚠️  Error inserting incident: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Updated {inserted} traffic incidents at {now.strftime('%H:%M:%S')}")
        return inserted
        
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

# Main collection loop
cycle_count = 0
cleanup_interval = 12  # Cleanup every 12 hours (12 * 60min cycles)

try:
    print("Starting continuous collection...")
    print("- Updates: Every 2 minutes")
    print("- Cleanup: Every 12 hours (keeps last 7 days)")
    print("- Press Ctrl+C to stop\n")
    
    while True:
        cycle_count += 1
        
        # Collect traffic data
        collect_traffic_data()
        
        # Cleanup old data every 12 hours (720 cycles at 1min each = 12 hours)
        if cycle_count % (cleanup_interval * 60) == 0:
            cleanup_old_data()
            cycle_count = 0  # Reset counter
        
        # Wait 2 minutes before next collection
        time.sleep(120)
        
except KeyboardInterrupt:
    print("\n🛑 Traffic collector stopped by user")
    sys.exit(0)
except Exception as e:
    print(f"❌ Fatal error: {e}")
    sys.exit(1)