import os, sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
conn = sqlite3.connect(os.path.join(BASE_DIR, "database/bus_data.db"))
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS bus_routes;")
c.execute("""
CREATE TABLE bus_routes (
    ServiceNo TEXT,
    Direction INTEGER,
    StopSequence INTEGER,
    BusStopCode TEXT,
    Distance REAL
);
""")

conn.commit()
conn.close()
print("bus_routes table reset successfully.")
