"""Shared extension instances to avoid circular imports."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
