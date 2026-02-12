from flask import Flask, render_template, request, url_for, redirect, flash, session
import joblib
import pandas as pd
import sqlite3
import re
import zipfile
import xml.etree.ElementTree as ET
from sklearn.ensemble import RandomForestClassifier
import hashlib
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = '57bbfe3952f5d6871ff495ec'
MODEL_PATH = r"C:\python\Doctor-Dai\disease_diagnosis_model.pkl"
TRAINING_DATA_PATH = "Training.csv"

import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_salt, stored_hash, provided_password):
    salt = bytes.fromhex(stored_salt)
    check_hash = hashlib.sha256(salt + provided_password.encode()).hexdigest()
    return check_hash == stored_hash

    
def init_prediction_engine():
    try:
        training_df = pd.read_csv(TRAINING_DATA_PATH)
        all_symptoms = [col for col in training_df.columns if col != "prognosis"]
        x_train = training_df[all_symptoms]
        y_train = training_df["prognosis"].astype(str)

        trained_model = RandomForestClassifier(
            n_estimators=350,
            random_state=42,
            n_jobs=-1,
        )
        trained_model.fit(x_train, y_train)
        return trained_model, all_symptoms, all_symptoms
    except Exception:
        fallback_model = joblib.load(MODEL_PATH)
        model_features = list(getattr(fallback_model, "feature_names_in_", []))
        if not model_features:
            raise RuntimeError("No valid features found for prediction model.")
        return fallback_model, model_features, model_features


model, MODEL_FEATURES, ALL_SYMPTOMS = init_prediction_engine()

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

def init_dbp():
    with sqlite3.connect("personal_database.db") as conn:
        command = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT UNIQUE NOT NULL,
            height REAL,
            weight REAL,
            Age INTEGER,
            Gender TEXT NOT NULL,
            Systolic INTEGER,
            Diastolic INTEGER,
            Heart_rate INTEGER,
            blood_sugar INTEGER
        )
        """
        conn.execute(command)

init_dbp()
def user_exists(username):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None


def prettify_symptom(symptom):
    return " ".join(symptom.replace("_", " ").split()).title()


def _slugify_name(name):
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", str(name)).strip().lower()
    return ".".join(cleaned.split()) if cleaned else "doctor"


def _build_avatar(name):
    words = [w for w in re.sub(r"[^a-zA-Z ]", "", str(name)).split() if w]
    if not words:
        return "DR"
    return (words[0][0] + (words[1][0] if len(words) > 1 else "R")).upper()


def _load_sheet1_rows_without_openpyxl(file_path):
    ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ns_rel_pkg = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

    with zipfile.ZipFile(file_path) as workbook_zip:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", ns_main):
                text = "".join((t.text or "") for t in si.findall(".//a:t", ns_main))
                shared_strings.append(text)

        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib.get("Id"): "xl/" + rel.attrib.get("Target", "")
            for rel in rels_root.findall("r:Relationship", ns_rel_pkg)
        }

        target_sheet = None
        for sheet in workbook_root.findall("a:sheets/a:sheet", ns_main):
            if sheet.attrib.get("name") == "Sheet1":
                rid = sheet.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target_sheet = rel_map.get(rid)
                break
        if not target_sheet:
            return []

        sheet_root = ET.fromstring(workbook_zip.read(target_sheet))
        rows = []
        for row in sheet_root.findall(".//a:sheetData/a:row", ns_main):
            vals = []
            for cell in row.findall("a:c", ns_main):
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", ns_main)
                if value_node is None:
                    vals.append("")
                    continue
                raw = value_node.text or ""
                if cell_type == "s" and raw.isdigit():
                    idx = int(raw)
                    vals.append(shared_strings[idx] if idx < len(shared_strings) else "")
                else:
                    vals.append(raw)
            rows.append(vals)

        if len(rows) < 2:
            return []

        headers = [str(h).strip() for h in rows[0]]
        parsed = []
        for raw_row in rows[1:]:
            raw_row += [""] * (len(headers) - len(raw_row))
            parsed.append({headers[i]: raw_row[i] for i in range(len(headers))})
        return parsed


def load_doctors_from_excel():
    try:
        df = pd.read_excel("doctor.xlsx", sheet_name="Sheet1")
    except Exception:
        try:
            df = pd.DataFrame(_load_sheet1_rows_without_openpyxl("doctor.xlsx"))
        except Exception:
            df = pd.DataFrame()

    if df.empty:
        return []

    df.columns = [str(c).strip() for c in df.columns]
    required = {"Name_of_Doctor", "Department", "Name_of_Hospital", "Location"}
    if not required.issubset(df.columns):
        return []

    df = df.dropna(subset=["Name_of_Doctor", "Department"]).copy()
    doctors = []
    for idx, row in df.iterrows():
        name = str(row.get("Name_of_Doctor", "")).strip()
        specialty = str(row.get("Department", "")).strip()
        hospital = str(row.get("Name_of_Hospital", "")).strip()
        location = str(row.get("Location", "")).strip()
        if not name or not specialty:
            continue
        slug = _slugify_name(name)
        doctors.append(
            {
                "name": name,
                "specialty": specialty,
                "experience": f"{8 + (idx % 17)} years experience",
                "focus": hospital or "Hospital Consultant",
                "email": f"{slug}@hospital.com",
                "phone": f"(555) {100 + (idx % 900)}-{1000 + (idx % 9000):04d}",
                "location": location or "Unknown",
                "availability": (
                    ["today", "week"]
                    if idx % 3 == 0
                    else (["week", "month"] if idx % 3 == 1 else ["today", "month"])
                ),
                "avatar": _build_avatar(name),
            }
        )
    return doctors


DOCTORS_DATA = load_doctors_from_excel()

@app.route("/")
def home_page():
    return render_template("home.html")
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        # Fetch user by username only
        cur.execute("SELECT id, username, password FROM users WHERE username = ?", (name,))
        user = cur.fetchone()
        conn.close()

        if user:
            userid, username, stored_hash = user
            # Check hashed password
            if stored_hash == hash_password(password):
                session['user'] = username
                session['user_id'] = userid
                flash("Login successful!", "success")
                return redirect(url_for("home_page"))
            else:
                flash("Incorrect password. Try again.", "danger")
                return render_template('login.html')
        else:
            flash("Invalid username", "danger")
            return render_template("login.html")

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
        if len(password1) < 6:
            flash("Password must be greater than or equal to length 6.", 'danger')
            return render_template('signup.html')
        if password1 != password2:
            flash("Password don't match. Try again!", 'danger')
            return render_template('signup.html')
        session['user'] = username
        
        hashed_password = hash_password(password1)
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
            (username, hashed_password, email)
        )

        conn.commit()

        # Get the last inserted user id
        user_id = cur.lastrowid

        conn.close()

        # Store in session
        session["user_id"] = user_id
        session["user"] = username

        flash('Signup Successfully.', 'success')
        return redirect(url_for("home_page"))

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()   
    flash("You have been logged out.", "info")
    return redirect("/")

@app.route('/analyzer', methods=['GET', 'POST'])
def analyzer_page():
    prediction = None
    selected_symptoms = []
    top_predictions = []
    next_steps = [
        "Rest and stay hydrated.",
        "Monitor symptoms for 24-48 hours.",
        "Consult a qualified doctor if symptoms worsen.",
    ]

    if request.method == "POST":
        selected_symptoms = request.form.getlist("symptoms")
        selected_symptoms = [s for s in selected_symptoms if s]
        selected_symptoms = list(dict.fromkeys(selected_symptoms))

        symptom_vector = {
            feature: int(feature in selected_symptoms)
            for feature in MODEL_FEATURES
        }
        input_df = pd.DataFrame([symptom_vector], columns=MODEL_FEATURES)
        prediction = str(model.predict(input_df)[0])

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(input_df)[0]
            classes = list(model.classes_)
            ranked = sorted(
                zip(classes, probabilities),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            top_predictions = [
                {"disease": str(disease), "probability": round(float(prob) * 100, 1)}
                for disease, prob in ranked
            ]
        elif prediction:
            top_predictions = [{"disease": prediction, "probability": 100.0}]

    symptom_options = [
        {"value": symptom, "label": prettify_symptom(symptom)}
        for symptom in ALL_SYMPTOMS
    ]

    return render_template(
        'analyzer.html',
        symptom_options=symptom_options,
        selected_symptoms=selected_symptoms,
        prediction=prediction,
        top_predictions=top_predictions,
        next_steps=next_steps,
    )
@app.route('/history', methods=['GET', 'POST'])
def history_page():
    # ----------------------
    # POST: Save new entry
    # ----------------------
    if request.method == "POST":
        user_name = session.get("user")
        if not user_name:
            flash("Please login first!", "danger")
            return redirect("/login")

        height = request.form.get("height")
        weight = request.form.get("weight")
        age = request.form.get("age")
        gender = request.form.get("gender")
        systolic = request.form.get("systolic")
        diastolic = request.form.get("diastolic")
        heart_rate = request.form.get("heart_rate")
        blood_sugar = request.form.get("blood_sugar")

        conn = sqlite3.connect("personal_database.db", timeout=10)
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO users (user_name, height, weight, Age, Gender, Systolic, Diastolic, Heart_rate, blood_sugar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_name, height, weight, age, gender, systolic, diastolic, heart_rate, blood_sugar))

        conn.commit()
        conn.close()

        return redirect('/history')

    user_name = session.get("user")
    if not user_name:
        flash("Please login first!", "danger")
        return redirect("/login")

    conn = sqlite3.connect("personal_database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE user_name = ? ORDER BY id DESC", (user_name,))
    entries = cur.fetchall()

    conn.close()

    return render_template('history.html', entries=entries)



@app.route('/doctors')
def doctor_page():
    selected_specialty = request.args.get("specialty", "").strip()
    selected_location = request.args.get("location", "").strip()
    selected_availability = request.args.get("availability", "").strip().lower()

    filtered = []
    for doctor in DOCTORS_DATA:
        specialty_ok = (
            not selected_specialty
            or selected_specialty.lower() in doctor["specialty"].lower()
        )
        location_ok = (
            not selected_location
            or selected_location.lower() in doctor["location"].lower()
        )
        availability_ok = (
            not selected_availability
            or selected_availability in doctor["availability"]
        )
        if specialty_ok and location_ok and availability_ok:
            filtered.append(doctor)

    specialty_options = sorted({d["specialty"] for d in DOCTORS_DATA if d.get("specialty")})
    return render_template(
        'doctors.html',
        doctors=filtered,
        specialty_options=specialty_options,
        selected_specialty=selected_specialty,
        selected_location=selected_location,
        selected_availability=selected_availability,
    )

if __name__ == "__main__":
    app.run(debug=True)
