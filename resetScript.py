# import sqlite3
# import os

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# BUS_DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

# print("🧹 Starting database cleanup...")
# print("=" * 60)

# conn = sqlite3.connect(BUS_DB_FILE)
# c = conn.cursor()

# # Count before
# c.execute("SELECT COUNT(*) FROM bus_routes")
# before_count = c.fetchone()[0]
# print(f"📊 Rows before cleanup: {before_count:,}")

# # # Create a temporary table with unique data
# print("\n⏳ Creating cleaned data table...")
# c.execute("""
#     CREATE TABLE IF NOT EXISTS bus_routes_clean (
#         ServiceNo TEXT,
#         Direction INTEGER,
#         StopSequence INTEGER,
#         BusStopCode TEXT,
#         Distance REAL,
#         PRIMARY KEY (ServiceNo, Direction, StopSequence, BusStopCode)
#     )
# """)

# # Copy unique data to clean table
# print("⏳ Removing duplicates...")
# c.execute("""
#     INSERT OR IGNORE INTO bus_routes_clean
#     SELECT DISTINCT ServiceNo, Direction, StopSequence, BusStopCode, Distance
#     FROM bus_routes
# """)

# # Count cleaned data
# c.execute("SELECT COUNT(*) FROM bus_routes_clean")
# after_count = c.fetchone()[0]
# print(f"✅ Unique rows: {after_count:,}")

# # Backup old table (just in case)
# print("\n💾 Backing up old table as 'bus_routes_backup'...")
# c.execute("DROP TABLE IF EXISTS bus_routes_backup")
# c.execute("ALTER TABLE bus_routes RENAME TO bus_routes_backup")

# # Rename clean table to original
# print("♻️  Replacing old table with cleaned data...")
# c.execute("ALTER TABLE bus_routes_clean RENAME TO bus_routes")

# conn.commit()

# # Verify
# c.execute("SELECT COUNT(*) FROM bus_routes")
# final_count = c.fetchone()[0]

# print("\n" + "=" * 60)
# print("✨ CLEANUP COMPLETE!")
# print("=" * 60)
# print(f"📊 Before: {before_count:,} rows")
# print(f"📊 After:  {final_count:,} rows")
# print(f"🗑️  Removed: {before_count - final_count:,} duplicate rows")
# print(f"💾 Backup saved as 'bus_routes_backup' table")

# # Show sample data to verify
# print("\n📋 Sample data (first 5 routes of Bus 10):")
# c.execute("""
#     SELECT ServiceNo, Direction, StopSequence, BusStopCode, Distance
#     FROM bus_routes
#     WHERE ServiceNo = '10'
#     ORDER BY Direction, StopSequence
#     LIMIT 5
# """)
# for row in c.fetchall():
#     print(f"  Bus {row[0]}, Dir {row[1]}, Seq {row[2]}, Stop {row[3]}, Dist {row[4]}km")

# conn.close()
# print("\n✅ Database cleanup successful!")


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
# print("🗑️  Deleting all bus routes...")
# c.execute("DELETE FROM bus_routes")
# conn.commit()

# Verify deletion
# c.execute("SELECT COUNT(*) FROM bus_routes")
# after = c.fetchone()[0]
# print(f"📊 Rows after: {after:,}")

# if after == 0:
#     print("✅ All bus routes deleted successfully!")
# else:
#     print(f"⚠️  Warning: {after} rows still remain")

conn.close()