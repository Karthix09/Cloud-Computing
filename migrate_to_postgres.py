"""
Migration script to move data from SQLite to PostgreSQL
Run this ONCE when setting up production database
"""
import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def migrate_users():
    """Migrate users from SQLite to PostgreSQL"""
    print("Migrating users table...")
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect('users.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    pg_cursor = pg_conn.cursor()
    
    try:
        # Get all users from SQLite
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()
        
        if not users:
            print("No users to migrate.")
            return
        
        # Prepare data for PostgreSQL
        user_data = []
        for user in users:
            user_data.append((
                user['username'],
                user['email'],
                user['phone'],
                user['password_hash'],
                user['date_of_birth'],
                user['created_at']
            ))
        
        # Insert into PostgreSQL
        insert_query = """
            INSERT INTO users (username, email, phone, password_hash, date_of_birth, created_at)
            VALUES %s
            ON CONFLICT (username) DO NOTHING
        """
        execute_values(pg_cursor, insert_query, user_data)
        pg_conn.commit()
        
        print(f"✅ Migrated {len(users)} users")
        
    except Exception as e:
        print(f"❌ Error migrating users: {e}")
        pg_conn.rollback()
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


def migrate_locations():
    """Migrate user locations from SQLite to PostgreSQL"""
    print("Migrating locations table...")
    
    sqlite_conn = sqlite3.connect('users.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    pg_cursor = pg_conn.cursor()
    
    try:
        # Get all locations
        sqlite_cursor.execute("SELECT * FROM locations")
        locations = sqlite_cursor.fetchall()
        
        if not locations:
            print("No locations to migrate.")
            return
        
        # Prepare data
        location_data = []
        for loc in locations:
            location_data.append((
                loc['user_id'],
                loc['label'],
                loc['latitude'],
                loc['longitude'],
                loc['is_primary'],
                loc.get('address'),
                loc.get('postal_code'),
                loc.get('is_favourite', 0)
            ))
        
        # Insert into PostgreSQL
        insert_query = """
            INSERT INTO locations 
            (user_id, label, latitude, longitude, is_primary, address, postal_code, is_favourite)
            VALUES %s
        """
        execute_values(pg_cursor, insert_query, location_data)
        pg_conn.commit()
        
        print(f"✅ Migrated {len(locations)} locations")
        
    except Exception as e:
        print(f"❌ Error migrating locations: {e}")
        pg_conn.rollback()
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


def migrate_bus_favorites():
    """Migrate bus favorites from SQLite to PostgreSQL"""
    print("Migrating bus favorites table...")
    
    sqlite_conn = sqlite3.connect('users.db')
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    pg_cursor = pg_conn.cursor()
    
    try:
        # Check if table exists in SQLite
        sqlite_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bus_favorites'"
        )
        if not sqlite_cursor.fetchone():
            print("No bus_favorites table found in SQLite.")
            return
        
        # Get all bus favorites
        sqlite_cursor.execute("SELECT * FROM bus_favorites")
        favorites = sqlite_cursor.fetchall()
        
        if not favorites:
            print("No bus favorites to migrate.")
            return
        
        # Prepare data
        favorite_data = []
        for fav in favorites:
            favorite_data.append((
                fav['user_id'],
                fav['bus_stop_code'],
                fav['bus_stop_name'],
                fav['created_at']
            ))
        
        # Insert into PostgreSQL
        insert_query = """
            INSERT INTO bus_favorites (user_id, bus_stop_code, bus_stop_name, created_at)
            VALUES %s
            ON CONFLICT (user_id, bus_stop_code) DO NOTHING
        """
        execute_values(pg_cursor, insert_query, favorite_data)
        pg_conn.commit()
        
        print(f"✅ Migrated {len(favorites)} bus favorites")
        
    except Exception as e:
        print(f"❌ Error migrating bus favorites: {e}")
        pg_conn.rollback()
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


def verify_migration():
    """Verify that migration was successful"""
    print("\n" + "="*50)
    print("VERIFICATION")
    print("="*50)
    
    pg_conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    pg_cursor = pg_conn.cursor()
    
    # Count records
    pg_cursor.execute("SELECT COUNT(*) FROM users")
    user_count = pg_cursor.fetchone()[0]
    
    pg_cursor.execute("SELECT COUNT(*) FROM locations")
    location_count = pg_cursor.fetchone()[0]
    
    pg_cursor.execute("SELECT COUNT(*) FROM bus_favorites")
    favorite_count = pg_cursor.fetchone()[0]
    
    print(f"PostgreSQL Database Status:")
    print(f"  - Users: {user_count}")
    print(f"  - Locations: {location_count}")
    print(f"  - Bus Favorites: {favorite_count}")
    
    pg_cursor.close()
    pg_conn.close()


if __name__ == "__main__":
    print("="*50)
    print("SQLite to PostgreSQL Migration")
    print("="*50)
    print(f"Target Database: {os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}")
    print("="*50)
    
    response = input("\n⚠️  This will migrate data to PostgreSQL. Continue? (yes/no): ")
    
    if response.lower() == 'yes':
        migrate_users()
        migrate_locations()
        migrate_bus_favorites()
        verify_migration()
        print("\n✅ Migration complete!")
    else:
        print("Migration cancelled.")