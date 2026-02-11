from flask import Flask, render_template, request, url_for, redirect, flash, session
import joblib
import pandas as pd
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = '57bbfe3952f5d6871ff495ec'
MODEL_PATH = "decision_tree_model.pkl"
model = joblib.load(MODEL_PATH)

def init_db():
    conn = None
    try:
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()
init_db()

def user_exists(username):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None

@app.route("/")
def home_page():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]

        # Connect to database
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        # Check if user exists
        cur.execute("SELECT * FROM users WHERE username = ? AND password = ?", (name, password))
        user = cur.fetchone()
        conn.close()

        if user:
            # User exists, redirect to home page
            session['user'] = name  # Optional: store user in session
            flash("Login successful!", "success")
            return redirect(url_for("home_page"))
        else:
            # User not found, stay on login page with flash message
            flash("Invalid username or password", "danger")
            return render_template("login.html")

    # GET request, just render login page
    return render_template("login.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        username = request.form["name"]
        email = request.form['email']
        password1 = request.form["password1"]
        password2 = request.form["password2"]

        if user_exists(username):
            flash('User already exists!!', category='danger')
            return render_template("signup.html")

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", (username, password1, email))
        conn.commit()
        conn.close()
        flash('Logged in successfully.', 'success')
        return redirect(url_for("home_page"))
    
    return render_template("signup.html")

@app.route('/analyzer')
def analyzer_page():
    return render_template('analyzer.html')

@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/doctors')
def doctor_page():
    return render_template('doctors.html')

if __name__ == "__main__":
    app.run(debug=True)
