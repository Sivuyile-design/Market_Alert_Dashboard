from flask import Flask, render_template, request, redirect, session, url_for
from functools import wraps

app = Flask(__name__)
app.secret_key = "YourSuperSecretKeyHere"  # keep secret

# Simple test users
USERS = {
    "friend@test.com": {"password": "Test1234!", "tier": "Pro"},
    "admin@test.com": {"password": "AdminPass!", "tier": "Premium"}
}

# Decorator to protect routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = USERS.get(email)
        if user and user["password"] == password:
            session["user_email"] = email
            session["tier"] = user["tier"]
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password"
    return render_template("login.html", error=error)

@app.route("/dashboard")
@login_required
def dashboard():
    tiers = session.get("tier")
    return render_template("dashboard.html", tiers=tiers)

@app.route("/alerts")
@login_required
def alerts():
    return render_template("email_alert.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
