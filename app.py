import os
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user


# Loads variables from the .env file into the environment
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure the SQLite database and disable modification tracking to save resources
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///watchd.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)

# Set up Flask-Login for session management and route protection
login_manager = LoginManager(app)
login_manager.login_view = 'login' 


@login_manager.user_loader
def load_user(user_id):
    # Retrieves the user object based on the user_id stored in the session
    return db.session.get(User, int(user_id))

# Base URLs and keys for the TMDB API
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE = 'https://api.themoviedb.org/3'
TMDB_IMG = 'https://image.tmdb.org/t/p/w500'


# Database Models

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Establish one-to-many relationships for easy querying (e.g., user.watched)
    watched = db.relationship('Watched', backref='user', lazy=True)
    watchlist = db.relationship('Watchlist', backref='user', lazy=True)

    def get_id(self):
        return str(self.user_id)


class Media(db.Model):
    # Stores basic media info locally to avoid hitting the TMDB API on every page load
    __tablename__ = 'media'
    media_id = db.Column(db.Integer, primary_key=True)
    tmdb_id = db.Column(db.String(20), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    release_year = db.Column(db.Integer)
    poster_url = db.Column(db.String(300))

    # Prevents duplicate entries for the same movie or TV show
    __table_args__ = (db.UniqueConstraint('tmdb_id', 'media_type'),)


class Watched(db.Model):
    # Junction table linking users to media they have already seen
    __tablename__ = 'watched'
    watched_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey('media.media_id'), nullable=False)
    rating = db.Column(db.Integer)
    review = db.Column(db.Text)
    watched_on = db.Column(db.DateTime, server_default=db.func.now())

    media = db.relationship('Media')
    __table_args__ = (db.UniqueConstraint('user_id', 'media_id'),)


class Watchlist(db.Model):
    # Junction table linking users to media they want to watch
    __tablename__ = 'watchlist'
    watchlist_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    media_id = db.Column(db.Integer, db.ForeignKey('media.media_id'), nullable=False)
    added_on = db.Column(db.DateTime, server_default=db.func.now())

    media = db.relationship('Media')
    __table_args__ = (db.UniqueConstraint('user_id', 'media_id'),)


# Forms

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class SearchForm(FlaskForm):
    q = StringField('Search', validators=[DataRequired()])
    type = SelectField('Type', choices=[('movie', 'Movies'), ('tv', 'TV Shows')])


# Utility Functions

@app.context_processor
def inject_globals():
    # Injects TMDB_IMG directly into all Jinja templates so it does not need to be passed in every render_template call
    return dict(TMDB_IMG=TMDB_IMG)


def get_or_create_media(tmdb_id, media_type, title=None, release_year=None, poster_url=None):
    # Checks if media exists in the local database. If not, fetches details from TMDB and saves it.
    media = Media.query.filter_by(tmdb_id=str(tmdb_id), media_type=media_type).first()
    if media:
        return media


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
    # Retrieves comprehensive media details from the TMDB API for the detailed view page
    url = f'{TMDB_BASE}/{media_type}/{tmdb_id}'
    params = {'api_key': TMDB_API_KEY, 'language': 'en-US'}
    resp = requests.get(url, params=params)
    return resp.json() if resp.status_code == 200 else None

# Caches genres in memory to prevent exceeding TMDB API rate limits on frequent page reloads
GENRE_CACHE = {}

def get_genres(media_type='movie'):
    cache_key = media_type
    if cache_key in GENRE_CACHE:
        return GENRE_CACHE[cache_key]

    url = f'{TMDB_BASE}/genre/{media_type}/list'
    params = {'api_key': TMDB_API_KEY, 'language': 'en-US'}
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            genres = {str(genre['id']): genre['name'] for genre in data.get('genres', [])}
            GENRE_CACHE[cache_key] = genres
            return genres
        return {}
    except:
        return {}


# Routes

@app.route('/')
def index():
    # Fetches today's trending media, applies selected genre filters, and sorts the results
    trending = []
    sort_by = request.args.get('sort', 'popularity.desc')
    genre_id = request.args.get('genre', '')

    try:
        resp = requests.get(
            f'{TMDB_BASE}/trending/all/day',
            params={'api_key': TMDB_API_KEY, 'language': 'en-US'},
            timeout=5
        )
        if resp.status_code == 200:
            trending = resp.json().get('results', [])
            if current_user.is_authenticated:
                # Appends personal watch status flags (in_watchlist, in_watched) to the API results
                trending = add_status_to_items(trending, current_user.user_id)

            # Merges movie and TV genres to populate the filter dropdown comprehensively
            genres = get_genres('movie')
            genres_tv = get_genres('tv')
            for k, v in genres_tv.items():
                if k not in genres:
                    genres[k] = v

            if genre_id and genre_id not in genres:
                genre_id = ''

            # Filters the API results by the selected genre ID
            if genre_id:
                trending = [item for item in trending if genre_id in [str(g) for g in item.get('genre_ids', [])]]

            # Defines sorting functions and applies the user-selected sort order
            sort_map = {
                'popularity.desc': lambda x: x.get('popularity', 0),
                'vote_average.desc': lambda x: x.get('vote_average', 0),
                'vote_count.desc': lambda x: x.get('vote_count', 0),
                'release_date.desc': lambda x: x.get('release_date') or x.get('first_air_date') or '1970-01-01',
                'title.asc': lambda x: (x.get('title') or x.get('name') or '').lower(),
            }
            sort_key = sort_map.get(sort_by, sort_map['popularity.desc'])
            trending.sort(key=sort_key, reverse=(sort_by != 'title.asc'))

    except Exception as e:
        print(f"Error fetching trending: {e}")
        trending = []

    return render_template('index.html', 
                           trending=trending, 
                           genres=genres,
                           selected_genre=genre_id,
                           selected_sort=sort_by)


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# Auth Routes

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # Verifies the username or email does not already exist
        existing = User.query.filter(
            (User.username == form.username.data) |
            (User.email == form.email.data)
        ).first()
        
        if existing:
            form.username.errors.append('Username or email already taken.')
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=generate_password_hash(form.password.data)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('index'))
            
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        # Authenticates by comparing the provided password against the stored hash
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


# Search Route

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    results = []
    query = request.args.get('q', '')
    type_ = request.args.get('type', 'movie')

    if query:
        # Queries the TMDB search endpoint and attaches local user watch status to the results
        resp = requests.get(
            f'{TMDB_BASE}/search/{type_}',
            params={'api_key': TMDB_API_KEY, 'query': query, 'language': 'en-US'}
        )
        results = resp.json().get('results', [])
        results = add_status_to_items(results, current_user.user_id)

    form = SearchForm(data={'q': query, 'type': type_})
    return render_template('search.html', form=form, results=results,
                           query=query, type=type_)


# Watchlist Routes

@app.route('/watchlist')
@login_required
def watchlist():
    # Retrieves all watchlist items tied to the authenticated user
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
        
    # Ensures the media exists locally before attempting to link it to a user's watchlist
    media = get_or_create_media(tmdb_id, media_type, title, year, poster)
    existing = Watchlist.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).first()
    
    if not existing:
        watchlist_item = Watchlist(user_id=current_user.user_id, media_id=media.media_id)
        db.session.add(watchlist_item)
        db.session.commit()
        
    return redirect(request.referrer or url_for('index'))


@app.route('/watchlist/remove', methods=['POST'])
@login_required
def remove_from_watchlist():
    # Deletes an item from the watchlist using the direct watchlist_id
    watchlist_id = request.form.get('watchlist_id')
    if watchlist_id:
        Watchlist.query.filter_by(watchlist_id=watchlist_id, user_id=current_user.user_id).delete()
        db.session.commit()
    return redirect(url_for('watchlist'))


@app.route('/watchlist/remove_by_media', methods=['POST'])
@login_required
def remove_from_watchlist_by_media():
    # Deletes an item from the watchlist based on its TMDB attributes (used primarily from detail views)
    tmdb_id = request.form.get('tmdb_id')
    media_type = request.form.get('media_type')
    
    if not tmdb_id or not media_type:
        return redirect(request.referrer or url_for('watchlist'))
    
    media = Media.query.filter_by(tmdb_id=str(tmdb_id), media_type=media_type).first()
    if media:
        Watchlist.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).delete()
        db.session.commit()
    
    return redirect(request.referrer or url_for('watchlist'))


# Watched Routes

@app.route('/watched')
@login_required
def watched():
    # Retrieves all watched items for the current user, ordered by most recently added
    items = Watched.query.filter_by(user_id=current_user.user_id).order_by(Watched.watched_on.desc()).all()
    return render_template('watched.html', items=items)


@app.route('/watched/add', methods=['POST'])
@login_required
def add_to_watched(): 
    tmdb_id = request.form.get('tmdb_id')
    media_type = request.form.get('media_type')
    title = request.form.get('title')
    year = request.form.get('year')
    poster = request.form.get('poster')
    rating = request.form.get('rating', type=int)
    review = request.form.get('review')

    if not tmdb_id or not media_type:
        return redirect(url_for('search'))
        
    media = get_or_create_media(tmdb_id, media_type, title, year, poster)
    
    # Automatically removes the item from the user's watchlist when marking it as watched
    Watchlist.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).delete()
    existing = Watched.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).first()
    
    # Creates a new record or updates the existing rating/review
    if not existing:
        watched_item = Watched(
            user_id=current_user.user_id,
            media_id=media.media_id,
            rating=rating,
            review=review
        )
        db.session.add(watched_item)
    else:
        existing.rating = rating
        existing.review = review
        
    db.session.commit()
    return redirect(request.referrer or url_for('index'))


@app.route('/watched/update', methods=['POST'])
@login_required
def update_watched():
    # Updates the rating and review of a previously watched item
    watched_id = request.form.get('watched_id')
    rating = request.form.get('rating', type=int)
    review = request.form.get('review')
    
    if watched_id:
        item = Watched.query.filter_by(watched_id=watched_id, user_id=current_user.user_id).first()
        if item:
            item.rating = rating
            item.review = review
            db.session.commit()
            
    return redirect(url_for('watched'))


@app.route('/watched/remove', methods=['POST'])
@login_required
def remove_from_watched():
    watched_id = request.form.get('watched_id')
    if watched_id:
        Watched.query.filter_by(watched_id=watched_id, user_id=current_user.user_id).delete()
        db.session.commit()
    return redirect(url_for('watched'))


def add_status_to_items(items, user_id):
    # Iterates through external API results and injects boolean flags indicating local database relationships
    for item in items:
        media_type = item.get('media_type')
        
        # Provides a fallback if the TMDB API response lacks an explicit media_type
        if not media_type:
            if 'title' in item:
                media_type = 'movie'
            elif 'name' in item:
                media_type = 'tv'
            else:
                item['in_watchlist'] = False
                item['in_watched'] = False
                continue
                
        media = Media.query.filter_by(tmdb_id=str(item['id']), media_type=media_type).first()
        
        # Checks for records in the junction tables if the media exists locally
        if media:
            item['in_watchlist'] = Watchlist.query.filter_by(user_id=user_id, media_id=media.media_id).first() is not None
            item['in_watched'] = Watched.query.filter_by(user_id=user_id, media_id=media.media_id).first() is not None
        else:
            item['in_watchlist'] = False
            item['in_watched'] = False
            
    return items


# Details Route

@app.route('/media/<media_type>/<tmdb_id>')
@login_required
def media_detail(media_type, tmdb_id):
    # Renders an extended view containing detailed TMDB data combined with local user context
    details = fetch_media_details(tmdb_id, media_type)
    if not details:
        return render_template('404.html'), 404
        
    media = get_or_create_media(tmdb_id, media_type)
    in_watchlist = Watchlist.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).first() is not None
    in_watched = Watched.query.filter_by(user_id=current_user.user_id, media_id=media.media_id).first()
    
    return render_template('media_detail.html',
                           details=details,
                           media=media,
                           in_watchlist=in_watchlist,
                           in_watched=in_watched)

# Profile Route

@app.route('/profile')
@login_required
def profile():
    # Display current users profile page 
    return render_template('profile.html', user=current_user)


if __name__ == '__main__':
    with app.app_context():
        # Generates SQLite tables upon application launch if they do not exist
        db.create_all()
    app.run(debug=True)