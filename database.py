import os
import sqlite3

# Check if running on AWS or production
IS_PRODUCTION = os.getenv('AWS_EXECUTION_ENV') or os.getenv('FLASK_ENV') == 'production'

if IS_PRODUCTION:
    import psycopg2
    from psycopg2.extras import RealDictCursor


def get_db_connection():
    """
    Get database connection for USER DATA based on environment.
    - Production (AWS): PostgreSQL via RDS
    - Development (Local): SQLite
    """
    if IS_PRODUCTION:
        # PostgreSQL connection for production
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'transport_db'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD'),
            cursor_factory=RealDictCursor
        )
        print("✅ Connected to PostgreSQL (Production)")
    else:
        # SQLite connection for local development
        conn = sqlite3.connect("database/users.db")
        conn.row_factory = sqlite3.Row
        print("✅ Connected to SQLite (Development)")
    
    return conn


def get_bus_db_connection():
    """
    Get database connection for BUS DATA.
    - Production: PostgreSQL RDS (use existing bus_stops and bus_arrivals tables)
    - Development: SQLite local cache
    """
    if IS_PRODUCTION:
        # Use PostgreSQL for bus data in production
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'transport_db'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD'),
            cursor_factory=RealDictCursor
        )
        print("✅ Connected to PostgreSQL for bus data (Production)")
        return conn
    else:
        # SQLite for local development
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        BUS_DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(BUS_DB_FILE), exist_ok=True)
        
        conn = sqlite3.connect(BUS_DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn


def init_users_db():
    """
    Initialize USER database tables.
    Works with both SQLite (local) and PostgreSQL (production).
    """
    conn = get_db_connection()
    
    if IS_PRODUCTION:
        # PostgreSQL syntax
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(50),
                password_hash VARCHAR(255) NOT NULL,
                date_of_birth DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Locations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                label VARCHAR(255),
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                is_primary BOOLEAN DEFAULT FALSE,
                address TEXT,
                postal_code VARCHAR(20),
                is_favourite BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # Bus favorites table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bus_favorites (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                bus_stop_code VARCHAR(10) NOT NULL,
                bus_stop_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, bus_stop_code)
            )
        ''')
        
        conn.commit()
        cursor.close()
        print("✅ PostgreSQL user tables initialized")
        
    else:
        # SQLite syntax
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            phone TEXT,
            password_hash TEXT,
            date_of_birth TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            label TEXT,
            latitude REAL,
            longitude REAL,
            is_primary BOOLEAN DEFAULT 0,
            address TEXT,
            postal_code TEXT,
            is_favourite BOOLEAN DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS bus_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bus_stop_code TEXT,
            bus_stop_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, bus_stop_code),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        
        conn.commit()
        print("✅ SQLite user tables initialized")
    
    conn.close()


def init_bus_db():
    """
    Initialize BUS database tables.
    In production, this uses your EXISTING PostgreSQL tables.
    In development, creates local SQLite tables.
    """
    conn = get_bus_db_connection()
    cursor = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL - Create missing tables only
        # bus_stops and bus_arrivals already exist in your RDS
        
        # Create bus_routes table (needed for route planning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bus_routes (
                ServiceNo VARCHAR(10),
                Direction INTEGER,
                StopSequence INTEGER,
                BusStopCode VARCHAR(10),
                Distance DECIMAL(10, 2)
            )
        """)
        
        # Create index for bus_routes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bus_routes_service 
            ON bus_routes(ServiceNo, Direction, StopSequence)
        """)
        
        # Create traffic incidents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                Id VARCHAR(255) PRIMARY KEY,
                Type VARCHAR(100),
                Latitude DOUBLE PRECISION,
                Longitude DOUBLE PRECISION,
                Message TEXT,
                FetchedAt TIMESTAMP
            )
        """)
        
        conn.commit()
        print("✅ PostgreSQL bus tables initialized (using existing bus_stops and bus_arrivals)")
        
    else:
        # SQLite for local development
        cursor.execute("""CREATE TABLE IF NOT EXISTS bus_stops(
            code TEXT PRIMARY KEY, 
            description TEXT, 
            road TEXT, 
            lat REAL, 
            lon REAL
        )""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS bus_arrivals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stop_code TEXT,
            service TEXT,
            eta_min REAL,
            bus_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS bus_routes(
            ServiceNo TEXT,
            Direction INTEGER,
            StopSequence INTEGER,
            BusStopCode TEXT,
            Distance REAL
        )""")
        
        conn.commit()
        print("✅ SQLite bus tables initialized")
    
    conn.close()


# Initialize both databases when module is imported
if __name__ == "__main__":
    print("🚀 Initializing databases...")
    print(f"Environment: {'Production (AWS)' if IS_PRODUCTION else 'Development (Local)'}")
    init_users_db()
    init_bus_db()
    print("✅ All databases initialized successfully!")