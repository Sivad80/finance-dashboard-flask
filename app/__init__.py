import os
from flask import Flask
from dotenv import load_dotenv

from .extensions import db, migrate

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Ensure Instance Folder Exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Basic Config
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

    # SQLite DB Inside /instance/app.db
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    from .routes import main
    app.register_blueprint(main)

    # Import Models So Flask-Migrate Can "See" Them
    from . import models # noqa: F401

    return app
