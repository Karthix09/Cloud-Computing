#!/usr/bin/env python3
"""
Initialize Database Tables
Run this script ONCE before starting your application
"""

import os
import sys

# Set environment to development for local testing
os.environ['FLASK_ENV'] = 'development'

print("=" * 50)
print("🚀 Database Initialization Script")
print("=" * 50)

try:
    from database import init_users_db, init_bus_db, get_db_connection, IS_PRODUCTION
    
    print(f"\n📍 Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
    
    # Initialize users database
    print("\n1️⃣  Creating users tables...")
    try:
        init_users_db()
        print("   ✅ Users tables created successfully")
    except Exception as e:
        print(f"   ❌ Error creating users tables: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Initialize bus database
    print("\n2️⃣  Creating bus tables...")
    try:
        init_bus_db()
        print("   ✅ Bus tables created successfully")
    except Exception as e:
        print(f"   ❌ Error creating bus tables: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Verify tables were created
    print("\n3️⃣  Verifying tables...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
        else:
            # SQLite
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """)
        
        tables = cursor.fetchall()
        print("   📋 Tables found:")
        for table in tables:
            print(f"      - {table[0] if IS_PRODUCTION else table['name']}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"   ⚠️  Could not verify tables: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Database initialization complete!")
    print("=" * 50)
    print("\nYou can now run your Flask application:")
    print("  python3 app.py")
    print("\n")
    
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("\nMake sure you're in the correct directory and have installed dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)