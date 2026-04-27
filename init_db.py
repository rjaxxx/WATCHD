import sqlite3

conn = sqlite3.connect('watchd.db')
db = conn.cursor()

db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS media (
        media_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id      TEXT NOT NULL,
        media_type   TEXT NOT NULL,
        title        TEXT NOT NULL,
        release_year INTEGER,
        poster_url   TEXT,
        UNIQUE(tmdb_id, media_type)
    );

    CREATE TABLE IF NOT EXISTS watched (
        watched_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        media_id    INTEGER NOT NULL,
        rating      INTEGER CHECK(rating BETWEEN 1 AND 10),
        review      TEXT,
        watched_on  DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id)  REFERENCES users(user_id),
        FOREIGN KEY (media_id) REFERENCES media(media_id),
        UNIQUE(user_id, media_id)
    );

    CREATE TABLE IF NOT EXISTS watchlist (
        watchlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        media_id     INTEGER NOT NULL,
        added_on     DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id)  REFERENCES users(user_id),
        FOREIGN KEY (media_id) REFERENCES media(media_id),
        UNIQUE(user_id, media_id)
    );
''')

conn.commit()
conn.close()

print("Database created successfully!")
