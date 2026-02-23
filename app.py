from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
import pandas as pd
import numpy as np
import openai
import os

app = Flask(__name__)

# ================= CONFIG =================

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ALPHA_KEY = os.environ.get("ALPHA_KEY")
OPENAI_KEY = os.environ.get("OPENAI_KEY")

# ================= DATABASE MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(50))
    quantity = db.Column(db.Integer)
    user_id = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= AUTH ROUTES =================

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(
            username=request.form["username"],
            password=request.form["password"]
        ).first()

        if user:
            login_user(user)
            return redirect("/dashboard")

    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        new_user = User(
            username=request.form["username"],
            password=request.form["password"]
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect("/login")

    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ================= NIFTY ROUTE =================

@app.route("/nifty")
@login_required
def nifty():
    symbol = "NIFTYBEES.BSE"
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
    data = requests.get(url).json()
    return jsonify(data)

# ================= STOCK DATA =================

@app.route("/stock/<symbol>")
@login_required
def stock(symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_KEY}"
    data = requests.get(url).json()
    return jsonify(data)

# ================= TECHNICAL INDICATORS =================

@app.route("/technical/<symbol>")
@login_required
def technical(symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_KEY}"
    data = requests.get(url).json()

    if "Time Series (Daily)" not in data:
        return jsonify({"error": "Invalid symbol or API limit reached"})

    df = pd.DataFrame(data["Time Series (Daily)"]).T
    df["close"] = df["4. close"].astype(float)

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    macd = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()

    return jsonify({
        "RSI": round(rsi.iloc[-1],2),
        "MACD": round(macd.iloc[-1],2)
    })

# ================= AI ANALYSIS =================

@app.route("/ai_suggestion/<symbol>")
@login_required
def ai_suggestion(symbol):
    openai.api_key = OPENAI_KEY

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"user",
                 "content":f"Give short investment suggestion for Indian stock {symbol}"}
            ]
        )

        return jsonify({"analysis": response.choices[0].message.content})

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= PORTFOLIO =================

@app.route("/add_portfolio", methods=["POST"])
@login_required
def add_portfolio():
    p = Portfolio(
        symbol=request.form["symbol"],
        quantity=request.form["quantity"],
        user_id=current_user.id
    )
    db.session.add(p)
    db.session.commit()
    return redirect("/dashboard")

@app.route("/portfolio")
@login_required
def portfolio():
    user_data = Portfolio.query.filter_by(user_id=current_user.id).all()
    return jsonify([
        {"symbol": p.symbol, "qty": p.quantity}
        for p in user_data
    ])

# ================= START SERVER =================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)