from flask import Flask, render_template, request
import joblib
import pandas as pd

app = Flask(__name__)

MODEL_PATH = "decision_tree_model.pkl"
model = joblib.load(MODEL_PATH)

MODEL_FEATURES = list(getattr(model, "feature_names_in_", []))

if not MODEL_FEATURES:
    training_df = pd.read_csv("Training.csv")
    MODEL_FEATURES = [col for col in training_df.columns if col != "prognosis"]


def prettify_symptom(symptom):
    return " ".join(symptom.replace("_", " ").split()).title()


@app.route("/")
def home_page():
    return render_template('home.html')