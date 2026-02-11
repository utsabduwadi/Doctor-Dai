from flask import Flask, render_template, request
import joblib
import pandas as pd
import re
import zipfile
import xml.etree.ElementTree as ET

app = Flask(__name__)

MODEL_PATH = "decision_tree_model.pkl"
model = joblib.load(MODEL_PATH)

MODEL_FEATURES = list(getattr(model, "feature_names_in_", []))

if not MODEL_FEATURES:
    training_df = pd.read_csv("Training.csv")
    MODEL_FEATURES = [col for col in training_df.columns if col != "prognosis"]


def prettify_symptom(symptom):
    return " ".join(symptom.replace("_", " ").split()).title()


def _slugify_name(name):
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", str(name)).strip().lower()
    return ".".join(cleaned.split()) if cleaned else "doctor"


def _build_avatar(name):
    words = [w for w in re.sub(r"[^a-zA-Z ]", "", str(name)).split() if w]
    if not words:
        return "DR"
    initials = (words[0][0] + (words[1][0] if len(words) > 1 else "R")).upper()
    return initials


def _load_sheet1_rows_without_openpyxl(file_path):
    ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ns_rel_doc = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    ns_rel_pkg = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

    with zipfile.ZipFile(file_path) as workbook_zip:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", ns_main):
                text = "".join((t.text or "") for t in si.findall(".//a:t", ns_main))
                shared_strings.append(text)

        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        workbook_rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_target_map = {
            rel.attrib.get("Id"): "xl/" + rel.attrib.get("Target", "")
            for rel in workbook_rels_root.findall("r:Relationship", ns_rel_pkg)
        }

        target_sheet = None
        for sheet in workbook_root.findall("a:sheets/a:sheet", ns_main):
            if sheet.attrib.get("name") == "Sheet1":
                rel_id = sheet.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target_sheet = rel_target_map.get(rel_id)
                break

        if not target_sheet:
            return []

        sheet_root = ET.fromstring(workbook_zip.read(target_sheet))
        rows = []
        for row in sheet_root.findall(".//a:sheetData/a:row", ns_main):
            row_values = []
            for cell in row.findall("a:c", ns_main):
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", ns_main)
                if value_node is None:
                    row_values.append("")
                    continue
                raw_value = value_node.text or ""
                if cell_type == "s" and raw_value.isdigit():
                    idx = int(raw_value)
                    row_values.append(shared_strings[idx] if idx < len(shared_strings) else "")
                else:
                    row_values.append(raw_value)
            rows.append(row_values)

        if len(rows) < 2:
            return []

        headers = [str(h).strip() for h in rows[0]]
        parsed = []
        for raw_row in rows[1:]:
            padded_row = raw_row + [""] * (len(headers) - len(raw_row))
            parsed.append({headers[i]: padded_row[i] for i in range(len(headers))})
        return parsed


def load_doctors_from_excel():
    try:
        df = pd.read_excel("doctor.xlsx", sheet_name="Sheet1")
        df.columns = [str(col).strip() for col in df.columns]
    except Exception:
        try:
            parsed_rows = _load_sheet1_rows_without_openpyxl("doctor.xlsx")
            df = pd.DataFrame(parsed_rows)
            if not df.empty:
                df.columns = [str(col).strip() for col in df.columns]
            else:
                raise ValueError("Unable to parse doctor.xlsx")
        except Exception:
            return [
                {
                    "name": "Dr. Sarah Johnson",
                    "specialty": "Cardiologist",
                    "experience": "15 years experience",
                    "focus": "Board Certified",
                    "email": "sarah.johnson@hospital.com",
                    "phone": "(555) 123-4567",
                    "location": "New York",
                    "availability": ["today", "week"],
                    "avatar": "SJ",
                },
                {
                    "name": "Dr. Michael Chen",
                    "specialty": "Neurologist",
                    "experience": "12 years experience",
                    "focus": "Specialist in Migraines",
                    "email": "michael.chen@hospital.com",
                    "phone": "(555) 234-5678",
                    "location": "Boston",
                    "availability": ["week", "month"],
                    "avatar": "MC",
                },
                {
                    "name": "Dr. Emily Rodriguez",
                    "specialty": "Endocrinologist",
                    "experience": "18 years experience",
                    "focus": "Diabetes Specialist",
                    "email": "emily.rodriguez@hospital.com",
                    "phone": "(555) 345-6789",
                    "location": "Chicago",
                    "availability": ["today", "month"],
                    "avatar": "ER",
                },
            ]

    required_cols = {"Name_of_Doctor", "Department", "Name_of_Hospital", "Location"}
    if not required_cols.issubset(set(df.columns)):
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

        username = _slugify_name(name)
        doctors.append(
            {
                "name": name,
                "specialty": specialty,
                "experience": f"{8 + (idx % 17)} years experience",
                "focus": hospital if hospital else "Hospital Consultant",
                "email": f"{username}@hospital.com",
                "phone": f"(555) {100 + (idx % 900)}-{1000 + (idx % 9000):04d}",
                "location": location if location else "Unknown",
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
    return render_template('home.html')


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/analyzer', methods=['GET', 'POST'])
@app.route('/analyze', methods=['GET', 'POST'])
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
        if not selected_symptoms:
            selected_symptoms = [
                request.form.get(f"symptom_{idx}", "").strip()
                for idx in range(1, 6)
            ]
            selected_symptoms = [symptom for symptom in selected_symptoms if symptom]

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
        for symptom in MODEL_FEATURES
    ]

    return render_template(
        'analyzer.html',
        symptom_options=symptom_options,
        selected_symptoms=selected_symptoms,
        prediction=prediction,
        top_predictions=top_predictions,
        next_steps=next_steps,
    )

@app.route('/doctors')
def doctor_page():
    doctors = DOCTORS_DATA

    selected_specialty = request.args.get("specialty", "").strip()
    selected_location = request.args.get("location", "").strip()
    selected_availability = request.args.get("availability", "").strip().lower()

    filtered_doctors = []
    for doctor in doctors:
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
            filtered_doctors.append(doctor)

    specialty_options = sorted({doctor["specialty"] for doctor in doctors if doctor.get("specialty")})

    return render_template(
        'doctors.html',
        doctors=filtered_doctors,
        specialty_options=specialty_options,
        selected_specialty=selected_specialty,
        selected_location=selected_location,
        selected_availability=selected_availability,
    )



@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

if __name__ == "__main__":
    app.run(debug=True)
