#!/usr/bin/env python3
from app import create_app, db
from flask_migrate import Migrate
import os

app = create_app(os.getenv("FLASK_ENV") or "development")
migrate = Migrate(app, db)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
