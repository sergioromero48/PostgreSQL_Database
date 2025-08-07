#!/usr/bin/env python3
"""
Simple health check script to test database connectivity
and serial port availability before running the main app.
"""
import os
import sys

def check_database():
    """Test database connection"""
    try:
        from database import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def check_serial_port():
    """Test serial port availability"""
    serial_port = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    try:
        import serial
        ser = serial.Serial(serial_port, 115200, timeout=1)
        ser.close()
        print(f"✅ Serial port {serial_port} is available")
        return True
    except Exception as e:
        print(f"⚠️  Serial port {serial_port} not available: {e}")
        print("   (App will continue without serial data)")
        return False

def check_table_exists():
    """Check if the required table exists"""
    try:
        from database import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'weatherdatafromsite1'
            );
        """)
        exists = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        if exists:
            print("✅ Table 'weatherDataFromSite1' exists")
        else:
            print("❌ Table 'weatherDataFromSite1' does not exist")
        return exists
    except Exception as e:
        print(f"❌ Failed to check table existence: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Running health checks...")
    
    db_ok = check_database()
    serial_ok = check_serial_port()
    table_ok = check_table_exists()
    
    print(f"\n📊 Results:")
    print(f"  Database: {'✅' if db_ok else '❌'}")
    print(f"  Serial:   {'✅' if serial_ok else '⚠️'}")
    print(f"  Table:    {'✅' if table_ok else '❌'}")
    
    if db_ok and table_ok:
        print("\n🚀 Ready to run Streamlit app!")
        sys.exit(0)
    else:
        print("\n🛑 Please fix the issues above before running the app")
        sys.exit(1)
