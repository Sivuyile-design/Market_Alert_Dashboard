# Market_Alert_Dashboard.py
from flask import Flask, jsonify
import yfinance as yf
import pandas as pd

app = Flask(__name__)

@app.route("/")
def home():
    return "Market Alert Dashboard is running!"

@app.route("/stock/<ticker>")
def get_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")  # last 5 days
        df = pd.DataFrame(hist)
        # convert to dict for JSON
        return jsonify(df.tail(5).to_dict())
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
