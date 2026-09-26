from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class RawData(db.Model):
    __tablename__ = "raw_data"

    id = db.Column(db.Integer, primary_key=True)
    coin_name = db.Column(db.String(100), nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AnalyzedData(db.Model):
    __tablename__ = "analyzed_data"

    id = db.Column(db.Integer, primary_key=True)
    coin_name = db.Column(db.String(100), nullable=False)
    moving_average_price = db.Column(db.Float, nullable=False)
    trend = db.Column(db.String(8), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint("trend IN ('bullish', 'bearish')", name="valid_trend"),
    )