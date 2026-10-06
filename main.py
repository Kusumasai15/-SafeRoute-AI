"""Vercel's Flask entry point; local development still uses run.py."""
from app import create_app

app = create_app()
