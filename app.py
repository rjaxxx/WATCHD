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


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email    = request.form['email']
        password = request.form['password']
        db = get_db()
        existing = db.execute(
            'SELECT user_id FROM users WHERE username = ? OR email = ?',
            [username, email]
        ).fetchone()
        if existing:
            error = 'Username or email already taken.'
        else:
            db.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                [username, email, generate_password_hash(password)]
            )
            db.commit()
            return redirect(url_for('login'))
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db   = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ?',
            [username]
        ).fetchone()
        if user is None:
            error = 'Username not found.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Incorrect password.'
        else:
            session.clear()
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            return redirect(url_for('index'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# run

if __name__ == '__main__':
    app.run(debug=True)