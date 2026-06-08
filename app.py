from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import requests
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///watchd.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login' 


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE = 'https://api.themoviedb.org/3'
TMDB_IMG = 'https://image.tmdb.org/t/p/w500'


# models

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    user_id       = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at    = db.Column(db.DateTime, server_default=db.func.now())

    watched   = db.relationship('Watched', backref='user', lazy=True)
    watchlist = db.relationship('Watchlist', backref='user', lazy=True)

    def get_id(self):
        return str(self.user_id)


class Media(db.Model):
    __tablename__ = 'media'
    media_id     = db.Column(db.Integer, primary_key=True)
    tmdb_id      = db.Column(db.String(20), nullable=False)
    media_type   = db.Column(db.String(10), nullable=False)
    title        = db.Column(db.String(200), nullable=False)
    release_year = db.Column(db.Integer)
    poster_url   = db.Column(db.String(300))

    __table_args__ = (db.UniqueConstraint('tmdb_id', 'media_type'),)


class Watched(db.Model):
    __tablename__ = 'watched'
    watched_id = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    media_id   = db.Column(db.Integer, db.ForeignKey('media.media_id'), nullable=False)
    rating     = db.Column(db.Integer)
    review     = db.Column(db.Text)
    watched_on = db.Column(db.DateTime, server_default=db.func.now())

    media = db.relationship('Media')

    __table_args__ = (db.UniqueConstraint('user_id', 'media_id'),)


class Watchlist(db.Model):
    __tablename__ = 'watchlist'
    watchlist_id = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    media_id     = db.Column(db.Integer, db.ForeignKey('media.media_id'), nullable=False)
    added_on     = db.Column(db.DateTime, server_default=db.func.now())

    media = db.relationship('Media')

    __table_args__ = (db.UniqueConstraint('user_id', 'media_id'),)


# forms

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email    = StringField('Email',    validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class SearchForm(FlaskForm):
    q    = StringField('Search', validators=[DataRequired()])
    type = SelectField('Type', choices=[('movie', 'Movies'), ('tv', 'TV Shows')])


# helpful stuff

# automatically set TMDB_IMG variable to definition
@app.context_processor
def inject_globals():
    return dict(TMDB_IMG=TMDB_IMG)

# checks if media already exists in database, otherwise will search using API
def get_or_create_media(tmdb_id, media_type, title=None, release_year=None, poster_url=None):
    media = Media.query.filter_by(tmdb_id=str(tmdb_id), media_type=media_type).first()
    if media:
        return media

    # find title if not already in database
    if title is None:
        url = f'{TMDB_BASE}/{media_type}/{tmdb_id}'
        params = {'api_key': TMDB_API_KEY, 'language': 'en-US'}
        resp = requests.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get('title') or data.get('name')
            date_field = data.get('release_date') or data.get('first_air_date')
            release_year = date_field[:4] if date_field else None
            poster_url = data.get('poster_path')
        else:
            title = "Unknown Title"

    # define media to new values
    media = Media(
        tmdb_id=str(tmdb_id),
        media_type=media_type,
        title=title,
        release_year=release_year,
        poster_url=poster_url
    )
    db.session.add(media)
    db.session.commit()
    return media


def fetch_media_details(tmdb_id, media_type):
    url = f'{TMDB_BASE}/{media_type}/{tmdb_id}'
    params = {'api_key': TMDB_API_KEY, 'language': 'en-US'}
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        return resp.json()
    return None


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
    form = RegisterForm()
    if form.validate_on_submit():

        existing = User.query.filter(
            (User.username == form.username.data) |
            (User.email == form.email.data)
        ).first()
        if existing:
            form.username.errors.append('Username or email already taken.')
        else:
            user = User(
                username      = form.username.data,
                email         = form.email.data,
                password_hash = generate_password_hash(form.password.data)
            )
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None:
            form.username.errors.append('Username not found.')
        elif not check_password_hash(user.password_hash, form.password.data):
            form.password.errors.append('Incorrect password.')
        else:
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    results = []
    query   = request.args.get('q', '')
    type_   = request.args.get('type', 'movie')

    if query:
        resp    = requests.get(
            f'{TMDB_BASE}/search/{type_}',
            params={'api_key': TMDB_API_KEY, 'query': query, 'language': 'en-US'}
        )
        results = resp.json().get('results', [])


    form = SearchForm(data={'q': query, 'type': type_})
    return render_template('search.html', form=form, results=results,
                           query=query, type=type_)


# watchlist routes
@app.route('/watchlist')
@login_required
def watchlist():
    items = Watchlist.query.filter_by(user_id=current_user.user_id).all()
    return render_template('watchlist.html', items=items)


@app.route('/watchlist/add', methods=['POST'])
@login_required
def add_to_watchlist():
    tmdb_id = request.form.get('tmdb_id')
    media_type = request.form.get('media_type')
    title = request.form.get('title')
    year = request.form.get('year')
    poster = request.form.get('poster')
    if not tmdb_id or not media_type:
        return redirect(url_for('search'))
    media = get_or_create_media(tmdb_id, media_type, title, year, poster)
    existing = Watchlist.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).first()
    if not existing:
        watchlist_item = Watchlist(user_id=current_user.user_id, media_id=media.media_id)
        db.session.add(watchlist_item)
        db.session.commit()
    return redirect(request.referrer or url_for('search'))

#still need to add remove

# watched routes
@app.route('/watched')
@login_required
def watched():
    items = Watched.query.filter_by(user_id=current_user.user_id).order_by(Watched.watched_on.desc()).all()
    return render_template('watched.html', items=items)


# run

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)