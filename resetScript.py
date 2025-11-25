
# Clean up DB
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUS_DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

conn = sqlite3.connect(BUS_DB_FILE)
c = conn.cursor()

# Check how many rows before deletion
c.execute("SELECT COUNT(*) FROM bus_routes")
before = c.fetchone()[0]
print(f"📊 Rows before: {before:,}")

# Delete all rows
print("🗑️  Deleting all bus routes...")
c.execute("DELETE FROM bus_routes")
conn.commit()

#Verify deletion
c.execute("SELECT COUNT(*) FROM bus_routes")
after = c.fetchone()[0]
print(f"📊 Rows after: {after:,}")

if after == 0:
    print("✅ All bus routes deleted successfully!")
else:
    print(f"⚠️  Warning: {after} rows still remain")

conn.close()