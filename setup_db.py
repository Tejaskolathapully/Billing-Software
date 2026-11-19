import os
import psycopg2

PW = os.environ.get("PGPASSWORD", "postgres")

# 1. Create the KTMall database if it doesn't exist
conn = psycopg2.connect(host="localhost", user="postgres", password=PW, dbname="postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = 'KTMall'")
if not cur.fetchone():
    cur.execute('CREATE DATABASE "KTMall"')
    print("Database KTMall created")
else:
    print("Database KTMall already exists")
conn.close()

# 2. Create the products table and add sample rows
conn = psycopg2.connect(host="localhost", user="postgres", password=PW, dbname="KTMall")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        barcode_ean13 VARCHAR(13) PRIMARY KEY,
        product_name  VARCHAR(255) NOT NULL,
        category      VARCHAR(100),
        mrp_inr       NUMERIC(10,2) NOT NULL
    )
""")
cur.execute("""
    INSERT INTO products (barcode_ean13, product_name, category, mrp_inr) VALUES
    ('8901234567890', 'Sample Biscuits', 'Snacks', 20.00),
    ('8909876543210', 'Sample Soap', 'Personal Care', 45.00)
    ON CONFLICT DO NOTHING
""")
conn.commit()
conn.close()
print("products table ready")