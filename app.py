# File: app.py
from pathlib import Path

from flask import Flask
from models import db

app = Flask(__name__)
database_path = Path(__file__).resolve().parent / "coinpulse.sqlite3"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)