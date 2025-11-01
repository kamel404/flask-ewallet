import os

from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

db = SQLAlchemy()

def create_app(env="development"):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or "sqlite:///dev.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")
    db.init_app(app)

    # register blueprints
    from .routes.auth import bp as auth_bp
    from .routes.transfer import bp as transfer_bp
    from .routes.webhook import bp as webhook_bp
    from .routes.payments import bp as payment_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(payment_bp, url_prefix="/api/payments")
    app.register_blueprint(transfer_bp, url_prefix="/api/transfer")
    app.register_blueprint(webhook_bp, url_prefix="/api/webhook")

    return app
