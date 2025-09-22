# ========================================
# Market Alert Dashboard - Client-Specific with Currency
# ========================================

from flask import Flask, render_template_string
import sqlite3
from datetime import datetime
import yfinance as yf

app = Flask(__name__)

# ------------------------
# 1. Database Setup
# ------------------------
conn = sqlite3.connect("dashboard.db", check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    tier TEXT,
    created_at DATETIME
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS scraped_data (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    item_name TEXT,
    price REAL,
    currency TEXT,
    url TEXT,
    timestamp DATETIME
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS client_urls (
    client_id INTEGER,
    category TEXT,
    item_name TEXT,
    url TEXT,
    PRIMARY KEY (client_id, category, item_name),
    FOREIGN KEY(client_id) REFERENCES clients(client_id)
)
""")

conn.commit()

# ------------------------
# 2. Tier Settings
# ------------------------
tier_limits = {
    "Basic": 5,
    "Pro": 15,
    "Premium": None  # Unlimited
}

# ------------------------
# 3. Scraper Functions
# ------------------------
def scrape_stock_yf(symbol, currency="USD"):
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d")
    
    if not data.empty:
        price = round(data['Close'].iloc[0], 2)
    else:
        price = "N/A"
    
    return {
        "category": "Stocks",
        "item_name": symbol,
        "price": price,
        "currency": currency,
        "url": f"https://finance.yahoo.com/quote/{symbol}/",
        "timestamp": datetime.now()
    }

def scrape_car(model, url, currency="USD"):
    return {
        "category": "Cars",
        "item_name": model,
        "price": "N/A",
        "currency": currency,
        "url": url,
        "timestamp": datetime.now()
    }

def scrape_clothes(item, url, currency="USD"):
    return {
        "category": "Clothes",
        "item_name": item,
        "price": "N/A",
        "currency": currency,
        "url": url,
        "timestamp": datetime.now()
    }

def store_data(data):
    cursor.execute("""
    INSERT INTO scraped_data (category, item_name, price, currency, url, timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (data["category"], data["item_name"], data["price"], data.get("currency","USD"), data["url"], data["timestamp"]))
    conn.commit()

# ------------------------
# 4. Add Clients & Assign URLs
# ------------------------
def add_client(name, email, tier):
    if tier not in tier_limits:
        print("Invalid tier")
        return
    cursor.execute("""
    INSERT INTO clients (name, email, tier, created_at)
    VALUES (?, ?, ?, ?)
    """, (name, email, tier, datetime.now()))
    conn.commit()
    print(f"Client {name} added with tier {tier}.")

def assign_item_to_client(client_id, category, item_name, url):
    cursor.execute("""
    INSERT OR REPLACE INTO client_urls (client_id, category, item_name, url)
    VALUES (?, ?, ?, ?)
    """, (client_id, category, item_name, url))
    conn.commit()
    print(f"Assigned {item_name} ({category}) to client {client_id}")

# ------------------------
# 5. Fetch Dashboard per Client
# ------------------------
def fetch_dashboard_for_client(client_id):
    cursor.execute("SELECT tier, name FROM clients WHERE client_id=?", (client_id,))
    client = cursor.fetchone()
    if not client:
        return None, None
    tier, name = client
    limit = tier_limits[tier]
    
    if limit:
        cursor.execute("SELECT * FROM scraped_data ORDER BY timestamp DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT * FROM scraped_data ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    
    return tier, rows

# ------------------------
# 6. Flask Web Dashboard
# ------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Market Alert Dashboard</title>
<style>
body { font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }
h2 { color: #333; }
table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background: #333; color: white; }
tr:nth-child(even) { background: #eee; }
</style>
</head>
<body>
<h2>Dashboard ({{ tier }} - {{ name }})</h2>
<table>
<tr><th>Category</th><th>Item</th><th>Price</th><th>URL</th><th>Timestamp</th></tr>
{% for row in rows %}
<tr>
<td>{{ row[1] }}</td>
<td>{{ row[2] }}</td>
<td>{{ row[3] }} {{ row[4] }}</td>
<td><a href="{{ row[5] }}" target="_blank">Link</a></td>
<td>{{ row[6] }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""

@app.route("/dashboard/<int:client_id>")
def client_dashboard(client_id):
    tier, rows = fetch_dashboard_for_client(client_id)
    if not tier:
        return "Client not found"
    
    cursor.execute("SELECT name FROM clients WHERE client_id=?", (client_id,))
    name = cursor.fetchone()[0]
    return render_template_string(HTML_TEMPLATE, tier=tier, rows=rows, name=name)

# ------------------------
# 7. Run Scrapers & Store Example Data
# ------------------------
if __name__ == "__main__":
    # Example stocks
    stocks = ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
    for stock in stocks:
        store_data(scrape_stock_yf(stock))
    
    # Example cars
    cars = [
        {"model": "BMW X5", "url": "https://example.com/bmw-x5"},
        {"model": "Audi Q7", "url": "https://example.com/audi-q7"}
    ]
    for car in cars:
        store_data(scrape_car(car["model"], car["url"]))
    
    # Example clothes
    clothes = [
        {"item": "Nike Air Max", "url": "https://example.com/nike-air-max"},
        {"item": "Adidas Hoodie", "url": "https://example.com/adidas-hoodie"}
    ]
    for cloth in clothes:
        store_data(scrape_clothes(cloth["item"], cloth["url"]))
    
    # Run Flask server
    app.run(debug=True)
