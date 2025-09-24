import sqlite3
from datetime import datetime

conn = sqlite3.connect("C:\\Users\\Sivuyile\\Documents\\market_alert\\dashboard.db")
cursor = conn.cursor()

# Add a sample client
cursor.execute("""
INSERT INTO clients (name, email, tier, created_at)
VALUES (?, ?, ?, ?)
""", ("SniperTest", "sniper@example.com", "Basic", datetime.now()))
conn.commit()

# Check client ID
cursor.execute("SELECT client_id, name, tier FROM clients")
print(cursor.fetchall())

conn.close()
