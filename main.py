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
import hashlib
from Data_Bases.databs import init_db, init_dbp, user_exists
init_dbp()
init_db()

app = Flask(__name__)
app.config['SECRET_KEY'] = '57bbfe3952f5d6871ff495ec'
MODEL_PATH = "models_req/disease_diagnosis_model.pkl"
TRAINING_DATA_PATH = "models_req/Training.csv"


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
        df = pd.read_excel("Dataset/doctor.xlsx", sheet_name="Sheet1")
    except Exception:
        try:
            df = pd.DataFrame(_load_sheet1_rows_without_openpyxl("Dataset/doctor.xlsx"))
        except Exception:
            df = pd.DataFrame()

    if df.empty:
        return []

    df.columns = [str(c).strip() for c in df.columns]
    required = {"Name_of_Doctor", "Department", "Name_of_Hospital", "Location"}
    if not required.issubset(df.columns):
        return []

    df = df.dropna(subset=["Name_of_Doctor", "Department"]).copy()
    phone_col = None
    for candidate in ["Phone no.", "Phone", "Phone_No", "Contact", "Contact_No", "Mobile", "Mobile no."]:
        if candidate in df.columns:
            phone_col = candidate
            break
    doctors = []
    for idx, row in df.iterrows():
        name = str(row.get("Name_of_Doctor", "")).strip()
        specialty = str(row.get("Department", "")).strip()
        hospital = str(row.get("Name_of_Hospital", "")).strip()
        location = str(row.get("Location", "")).strip()
        if not name or not specialty:
            continue
        slug = _slugify_name(name)
        raw_phone = row.get(phone_col, "") if phone_col else ""
        phone = str(raw_phone).strip() if pd.notna(raw_phone) else ""
        if phone.lower() in {"nan", "none"}:
            phone = ""

        doctors.append(
            {
                "name": name,
                "specialty": specialty,
                "experience": f"{8 + (idx % 17)} years experience",
                "focus": hospital or "Hospital Consultant",
                "email": f"{slug}@hospital.com",
                "phone": phone or "Phone not available",
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


def _normalize_key(value):
    return " ".join(str(value).replace("_", " ").strip().lower().split())


def load_disease_doctor_assignments():
    file_path = "Dataset/Disease_With_Doctor_Assignment.xlsx"
    ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ns_rel_pkg = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

    def _column_index(cell_ref):
        letters = "".join(ch for ch in str(cell_ref) if ch.isalpha())
        index = 0
        for ch in letters:
            index = index * 26 + (ord(ch.upper()) - 64)
        return max(index - 1, 0)

    def _cell_text(cell, shared_strings):
        cell_type = cell.attrib.get("t")
        if cell_type == "s":
            value_node = cell.find("a:v", ns_main)
            raw = "" if value_node is None else (value_node.text or "")
            if raw.isdigit():
                idx = int(raw)
                return shared_strings[idx] if idx < len(shared_strings) else ""
            return ""
        if cell_type == "inlineStr":
            return "".join((t.text or "") for t in cell.findall(".//a:t", ns_main))
        value_node = cell.find("a:v", ns_main)
        return "" if value_node is None else (value_node.text or "")

    try:
        with zipfile.ZipFile(file_path) as workbook_zip:
            shared_strings = []
            if "xl/sharedStrings.xml" in workbook_zip.namelist():
                shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
                for si in shared_root.findall("a:si", ns_main):
                    shared_strings.append("".join((t.text or "") for t in si.findall(".//a:t", ns_main)))

            workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
            rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
            rel_map = {}
            for rel in rels_root.findall("r:Relationship", ns_rel_pkg):
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target", "")
                if target.startswith("/"):
                    target = target.lstrip("/")
                elif not target.startswith("xl/"):
                    target = f"xl/{target}"
                rel_map[rid] = target

            first_sheet = workbook_root.find("a:sheets/a:sheet", ns_main)
            if first_sheet is None:
                return {}
            rid = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target_sheet = rel_map.get(rid)
            if not target_sheet:
                return {}

            sheet_root = ET.fromstring(workbook_zip.read(target_sheet))
            rows = []
            for row in sheet_root.findall(".//a:sheetData/a:row", ns_main):
                cells = row.findall("a:c", ns_main)
                if not cells:
                    continue
                max_idx = max(_column_index(cell.attrib.get("r", "A1")) for cell in cells)
                values = [""] * (max_idx + 1)
                for cell in cells:
                    values[_column_index(cell.attrib.get("r", "A1"))] = _cell_text(cell, shared_strings).strip()
                rows.append(values)
    except Exception:
        return {}

    disease_map = {}
    for values in rows:
        non_empty = [(i, v) for i, v in enumerate(values) if v]
        if not non_empty:
            continue

        doctors_idx = None
        doctors_text = ""
        for idx, text in non_empty:
            if "|" in text:
                doctors_idx = idx
                doctors_text = text
                break
        if doctors_idx is None:
            continue

        disease_text = ""
        for idx, text in reversed(non_empty):
            if idx < doctors_idx and text.lower() != "assigned_doctors":
                disease_text = text
                break
        if not disease_text:
            continue

        disease_key = _normalize_key(disease_text)
        doctor_names = [name.strip() for name in doctors_text.split("|") if name.strip()]
        if not doctor_names:
            continue

        bucket = disease_map.setdefault(disease_key, [])
        seen = {_normalize_key(name) for name in bucket}
        for name in doctor_names:
            name_key = _normalize_key(name)
            if name_key not in seen:
                bucket.append(name)
                seen.add(name_key)
    return disease_map


DISEASE_DOCTOR_MAP = load_disease_doctor_assignments()


def recommend_doctors_for_diseases(disease_names, limit=2):
    if not disease_names or not DOCTORS_DATA:
        return []

    def _hospital_key(doc):
        return _normalize_key(doc.get("focus", "") or "unknown")

    doctor_index = {}
    for doc in DOCTORS_DATA:
        doctor_index.setdefault(_normalize_key(doc.get("name", "")), []).append(doc)

    matched_docs = []
    for disease in disease_names:
        key = _normalize_key(disease)
        for assigned_name in DISEASE_DOCTOR_MAP.get(key, []):
            for doc in doctor_index.get(_normalize_key(assigned_name), []):
                matched_docs.append(doc)

    recommendations = []
    used_hospitals = set()
    used_names = set()

    def _try_add(doc):
        if len(recommendations) >= limit:
            return
        hospital_key = _hospital_key(doc)
        name_key = _normalize_key(doc.get("name", ""))
        if not name_key or hospital_key in used_hospitals or name_key in used_names:
            return

        recommendations.append(
            {
                "name": doc.get("name", "Specialist"),
                "department": doc.get("specialty", "General Medicine"),
                "hospital": doc.get("focus", "Hospital"),
                "email": doc.get("email", ""),
                "phone": doc.get("phone", ""),
            }
        )
        used_hospitals.add(hospital_key)
        used_names.add(name_key)

    for doc in matched_docs:
        _try_add(doc)
        if len(recommendations) >= limit:
            break

    return recommendations

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
    user_name = session.get("user")
    if not user_name:
        flash("Please login first!", "danger")
        return redirect("/login")

    prediction = None
    selected_symptoms = []
    top_predictions = []
    recommended_doctors = []

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

        ranked_diseases = [item["disease"] for item in top_predictions] if top_predictions else ([prediction] if prediction else [])
        recommended_doctors = recommend_doctors_for_diseases(ranked_diseases, limit=2)

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
        recommended_doctors=recommended_doctors,
    )
@app.route('/personal_info', methods=['GET', 'POST'])
def personal_info_page():
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
            INSERT INTO health_entries (user_name, height, weight, Age, Gender, Systolic, Diastolic, Heart_rate, blood_sugar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_name, height, weight, age, gender, systolic, diastolic, heart_rate, blood_sugar))

        conn.commit()
        conn.close()

        return redirect('/personal_info')

    user_name = session.get("user")
    if not user_name:
        flash("Please login first!", "danger")
        return redirect("/login")

    conn = sqlite3.connect("personal_database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM health_entries WHERE user_name = ? ORDER BY id DESC", (user_name,))
    entries = cur.fetchall()

    conn.close()
    chart_rows = list(reversed(entries))

    def _to_number(value):
        try:
            if value is None or str(value).strip() == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    chart_data = {
        "labels": [str(i + 1) for i in range(len(chart_rows))],
        "metrics": {
            "blood_pressure": {
                "label": "Blood Pressure",
                "unit": "mmHg",
                "series": [
                    {"name": "Systolic", "values": [_to_number(row["Systolic"]) for row in chart_rows]},
                    {"name": "Diastolic", "values": [_to_number(row["Diastolic"]) for row in chart_rows]},
                ],
            },
            "weight": {
                "label": "Weight",
                "unit": "kg",
                "series": [
                    {"name": "Weight", "values": [_to_number(row["weight"]) for row in chart_rows]},
                ],
            },
            "heart_rate": {
                "label": "Heart Rate",
                "unit": "bpm",
                "series": [
                    {"name": "Heart Rate", "values": [_to_number(row["Heart_rate"]) for row in chart_rows]},
                ],
            },
            "blood_sugar": {
                "label": "Blood Sugar",
                "unit": "mg/dL",
                "series": [
                    {"name": "Blood Sugar", "values": [_to_number(row["blood_sugar"]) for row in chart_rows]},
                ],
            },
        },
    }

    return render_template('personal_info.html', entries=entries, chart_data=chart_data)



@app.route('/doctors')
def doctor_page():
    user_name = session.get("user")
    if not user_name:
        flash("Please login first!", "danger")
        return redirect("/login")

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
