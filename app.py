from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import sqlite3
import requests
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE = 'https://api.themoviedb.org/3'
TMDB_IMG = 'https://image.tmdb.org/t/p/w500'

def get_db():
    conn = sqlite3.connect('watchd.db')
    conn.row_factory = sqlite3.Row
    return conn

# routes

@app.route('/')
def index():
    return render_template('index.html')

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# run

if __name__ == '__main__':
    app.run(debug=True)