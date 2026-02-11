from flask import Flask, render_template

app = Flask(__init__)

@app.route('/')
def home_page():
    return render_template('home_page.html')