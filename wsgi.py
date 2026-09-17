"""Ponto de entrada para servidores WSGI de produção (PythonAnywhere, Gunicorn)."""

from app import create_app

application = create_app()
