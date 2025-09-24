from flask import Flask, render_template, request, redirect, url_for, session, flash
import yfinance as yf
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ---- USER DATA & TIERS ----
users = {
    "basic@example.com": {"password": "basicpass", "tier": "Basic"},
    "pro@example.com": {"password": "propass", "tier": "Pro"},
    "premium@example.com": {"password": "premiumpass", "tier": "Premium"}
}

# ---- ALERT STORAGE ----
alerts_data = []

# ---- EMAIL SETTINGS ----
EMAIL_USERNAME = "youremail@gmail.com"
EMAIL_PASSWORD = "yourpassword"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ---- HELPER FUNCTIONS ----
def send_alert_email(to_email, subject, message):
    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USERNAME
        msg['To'] = to_email

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email failed:", e)

def fetch_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="7d")  # last 7 days to ensure 5 closes
        if data.empty:
            return None
        return data
    except:
        return None

# ---- ROUTES ----
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email in users and users[email]['password'] == password:
            session['user'] = email
            session['tier'] = users[email]['tier']
            return redirect(url_for('index'))
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    # Filter alerts based on tier limits
    tier_limits = {"Basic": 3, "Pro": 5, "Premium": 1000}
    limit = tier_limits.get(session['tier'], 3)
    alerts = alerts_data[:limit]
    
    return render_template('dashboard.html', alerts=alerts, tier=session['tier'])

@app.route('/add_alert', methods=['POST'])
def add_alert():
    if 'user' not in session:
        return redirect(url_for('login'))

    symbol = request.form['symbol'].upper()
    stock_data = fetch_stock_data(symbol)
    if not stock_data:
        flash(f"No data found for {symbol}", "warning")
        return redirect(url_for('index'))

    latest_close = stock_data['Close'][-1]

    # Last 5 days for chart
    last_5_days = stock_data['Close'][-5:]
    dates = list(last_5_days.index.strftime('%Y-%m-%d'))
    prices = list(last_5_days.values)

    alert = {
        "symbol": symbol,
        "price": latest_close,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": dates,
        "prices": prices
    }
    alerts_data.insert(0, alert)

    # Send email alert
    send_alert_email(session['user'], f"Market Alert for {symbol}", f"{symbol} latest price: {latest_close}")
    flash(f"Alert for {symbol} added and email sent!", "success")
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
