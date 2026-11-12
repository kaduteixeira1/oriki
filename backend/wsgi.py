"""Ponto de entrada: `flask` (FLASK_APP=wsgi.py) e `gunicorn wsgi:app`."""
from app import create_app

app = create_app()
