import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "fl_audit_db")

print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

try:
    conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    print("✅ Successfully connected to Aiven MySQL!")

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        email VARCHAR(150) NOT NULL,
        role VARCHAR(50) DEFAULT 'HOSPITAL',
        status VARCHAR(50) DEFAULT 'PENDING',
        otp VARCHAR(10) NULL,
        otp_expiry DATETIME NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Audit Ledger Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_ledger (
        block_index INT PRIMARY KEY,
        timestamp DOUBLE NOT NULL,
        client_id VARCHAR(100) NOT NULL,
        update_hash VARCHAR(255) NOT NULL,
        status VARCHAR(50) NOT NULL,
        previous_hash VARCHAR(255) NOT NULL,
        current_hash VARCHAR(255) NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Insert Admin Account (akshay / naina07)
    admin_sql = """
    INSERT INTO users (username, password, email, role, status)
    VALUES (
        'akshay',
        'scrypt:32768:8:1$ZZVjhDp1irLUwHiC$fbe6c5e0ce4bfa82ea670a6cbac5bd179922a6e29a4bd3ae9c657a9ed02ff88b40aef29e0ecc4212f67fad16d5e7efb0caaecd62e978bf5184ef9d5f61061ff3',
        'akshaysuresh968@gmail.com',
        'ADMIN',
        'APPROVED'
    )
    ON DUPLICATE KEY UPDATE 
        password = VALUES(password),
        email = VALUES(email),
        role = 'ADMIN',
        status = 'APPROVED';
    """
    cursor.execute(admin_sql)
    conn.commit()

    # Verify tables
    cursor.execute("SHOW TABLES;")
    tables = cursor.fetchall()
    print("📋 Tables created in database:", tables)

    cursor.close()
    conn.close()
    print("🎉 Database successfully initialized!")

except Exception as e:
    print(f"❌ Database initialization error: {e}")
