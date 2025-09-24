# Market_Alert_Dashboard.py
"""
Market_Alert_Dashboard — Flask app
Features:
- Tiered access: Basic / Pro / Premium (enforced)
- User sign-up / login by email (no password for MVP — magic-link style)
- Watchlist limited by tier
- Live price checks via yfinance
- Discount detection (compares current price to recent high)
- Dashboard UI: Bootstrap + Chart.js
- Alerts: in-dashboard + email (SMTP configured by ENV)
- SQLite storage (users, watchlists, alerts)
- Ready for Render: uses PORT env var and supports gunicorn
"""

import os
import sqlite3
import json
from datetime import datetime, date
from functools import wraps

import yfinance as yf
import pandas as pd
from flask import (
    Flask, render_template, request, redirect, url_for, session, jsonify, flash
)
import smtplib
from email.mime.text import MIMEText

# ---- CONFIG ----
APP_SECRET = os.getenv("APP_SECRET") or "change_this_secret_in_prod"
DB_PATH = os.getenv("DB_PATH", "market_alert.db")

TIERS = {
    "Basic": {"slots": 3, "daily_alerts": 3},
    "Pro": {"slots": 5, "daily_alerts": 5},
    "Premium": {"slots": 9999, "daily_alerts": 9999}
}

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")  # set in Render env
SMTP_PASS = os.getenv("SMTP_PASS")  # set in Render env
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

# Discount threshold to trigger alert (percent)
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", 5.0))

# ---- FLASK APP ----
app = Flask(__name__)
app.secret_key = APP_SECRET

# ---- DB helpers ----
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        tier TEXT,
        created_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS watchlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        symbol TEXT,
        added_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        symbol TEXT,
        price REAL,
        discount REAL,
        timestamp TEXT
    );
    """)
    conn.commit()
    conn.close()

init_db()

# ---- utilities ----
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "email" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def send_email(to_email, subject, html_body):
    if not (SMTP_USER and SMTP_PASS and FROM_EMAIL):
        app.logger.warning("SMTP not configured; skipping email send.")
        return False
    try:
        msg = MIMEText(html_body, "html")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        app.logger.exception("Email send failed: %s", e)
        return False

def lookup_price_and_history(symbol, period="1mo"):
    t = yf.Ticker(symbol)
    try:
        hist = t.history(period=period)
        if hist.empty:
            return None
        # most recent close price
        current = t.info.get("regularMarketPrice") or hist["Close"].iloc[-1]
        closes = hist["Close"].tolist()
        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        return {"symbol": symbol.upper(), "price": float(current), "closes": closes, "dates": dates}
    except Exception as e:
        app.logger.exception("yfinance fetch failed for %s: %s", symbol, e)
        return None

def detect_discount(symbol):
    rec = lookup_price_and_history(symbol, period="1mo")
    if not rec:
        return None
    current = rec["price"]
    high_30 = max(rec["closes"]) if rec["closes"] else current
    discount = 0.0
    if high_30 and current:
        discount = round((high_30 - current) / high_30 * 100, 2)
    return {"symbol": rec["symbol"], "price": current, "30d_high": high_30, "discount_percent": discount, "closes": rec["closes"], "dates": rec["dates"]}

def user_remaining_alerts(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT tier FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row:
        return 0
    tier = row["tier"]
    daily_limit = TIERS[tier]["daily_alerts"]
    today = date.today().isoformat()
    cur.execute("SELECT COUNT(*) as c FROM alerts WHERE user_email=? AND date(timestamp)=?", (email, today))
    used = cur.fetchone()["c"]
    conn.close()
    return max(0, daily_limit - used)

# ---- ROUTES ----

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        tier = request.form.get("tier")
        if not email or tier not in TIERS:
            flash("Enter valid email and tier.", "danger")
            return redirect(url_for("index"))
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (email, tier, created_at) VALUES (?, ?, ?)", (email, tier, datetime.utcnow().isoformat()))
        cur.execute("UPDATE users SET tier=? WHERE email=?", (tier, email))
        conn.commit()
        conn.close()
        session["email"] = email
        session["tier"] = tier
        return redirect(url_for("dashboard"))
    return render_template("index.html", tiers=TIERS)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    email = session["email"]
    tier = session.get("tier")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlists WHERE user_email=?", (email,))
    rows = cur.fetchall()
    watchlist = [r["symbol"] for r in rows]
    remaining_alerts = user_remaining_alerts(email)
    conn.close()
    return render_template("dashboard.html", tier=tier, watchlist=watchlist, remaining_alerts=remaining_alerts)

@app.route("/api/add_watchlist", methods=["POST"])
@login_required
def add_watchlist():
    email = session["email"]
    symbol = request.json.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "No symbol"}), 400
    # enforce slots
    tier = session.get("tier")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM watchlists WHERE user_email=?", (email,))
    count = cur.fetchone()["c"]
    if count >= TIERS[tier]["slots"]:
        conn.close()
        return jsonify({"error": "Watchlist limit reached for your tier"}), 403
    # insert
    cur.execute("INSERT INTO watchlists (user_email, symbol, added_at) VALUES (?, ?, ?)", (email, symbol, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "symbol": symbol})

@app.route("/api/remove_watchlist", methods=["POST"])
@login_required
def remove_watchlist():
    email = session["email"]
    symbol = request.json.get("symbol", "").strip().upper()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlists WHERE user_email=? AND symbol=?", (email, symbol))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/check_symbol", methods=["POST"])
@login_required
def check_symbol():
    symbol = request.json.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "No symbol"}), 400
    res = detect_discount(symbol)
    if not res:
        return jsonify({"error": "Symbol not found or no data"}), 404

    # If discount above threshold, create alert (if user has quota)
    if res["discount_percent"] >= ALERT_THRESHOLD:
        email = session["email"]
        remaining = user_remaining_alerts(email)
        if remaining > 0:
            # store alert
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO alerts (user_email, symbol, price, discount, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (email, res["symbol"], res["price"], res["discount_percent"], datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            # send email
            html_body = render_template("email_alert.html", symbol=res["symbol"],
                                       price=res["price"], high=res["30d_high"],
                                       discount=res["discount_percent"], symbol_link=f"https://finance.yahoo.com/quote/{symbol}")
            send_ok = send_email(email, f"Market Alert: {symbol} discounted by {res['discount_percent']}%", html_body)
            res["alert_sent"] = send_ok
        else:
            res["alert_sent"] = False
            res["alert_message"] = "Daily alert limit reached for your tier."
    return jsonify(res)

@app.route("/api/get_watchlist_data")
@login_required
def get_watchlist_data():
    email = session["email"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlists WHERE user_email=?", (email,))
    rows = cur.fetchall()
    symbols = [r["symbol"] for r in rows]
    results = []
    for s in symbols:
        rec = detect_discount(s)
        if rec:
            results.append(rec)
    return jsonify({"watchlist": results})

@app.route("/api/alerts_history")
@login_required
def alerts_history():
    email = session["email"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, price, discount, timestamp FROM alerts WHERE user_email=? ORDER BY timestamp DESC LIMIT 100", (email,))
    rows = cur.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({"alerts": data})

# Simple admin route to view users (MVP)
@app.route("/admin/users")
def admin_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT email, tier, created_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return render_template("admin_users.html", users=rows)

# ---- run ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
