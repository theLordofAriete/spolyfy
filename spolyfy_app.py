from flask import Flask, jsonify, session, request, redirect, render_template
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import lyricsgenius
import google.generativeai as genai
import os
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import time
import socket
import csv
from datetime import datetime
import sqlite3
import hashlib

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Spotify API credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Genius API token
GENIUS_API_TOKEN = os.getenv('GENIUS_API_TOKEN')

# Gemini API key
GOOGLE_API_KEY = os.getenv('GEMINI_API_KEY')

# redirect_uri
REDIRECT_URI = os.getenv('REDIRECT_URI')
# same as the one in Spotify app settings
# REDIRECT_URI = 'http://127.0.0.1:8080'

# Spotipy setup
client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# LyricsGenius setup
genius = lyricsgenius.Genius(GENIUS_API_TOKEN)

# Gemini setup
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# SQLite database setup
DB_PATH = 'translations.db'

# Configure logging
log_file = './spolyfy.log'
log_level = logging.DEBUG
log_max_bytes = 30 * 1024 * 1024  # 30MB
log_backup_count = 5  # Rotate through 5 files

logger = logging.getLogger('spolyfy_logger')
logger.setLevel(log_level)

class CSVHandler(logging.Handler):
    def __init__(self, filename, mode='a', encoding='utf-8'):
        super().__init__()
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.stream = None
        self.writer = None
        self.open_file()
        # Write headers if file is empty
        self.write_headers_if_needed()

    def open_file(self):
        self.stream = open(self.filename, self.mode, encoding=self.encoding, newline='')
        self.writer = csv.writer(self.stream)

    def write_headers_if_needed(self):
        # Check if file is empty
        if os.path.getsize(self.filename) == 0:
            headers = ['Timestamp', 'Level', 'Track', 'Artist', 'Translated Lyrics', 'Remote Address', 'Translation Time (s)', 'Cache Used']
            self.writer.writerow(headers)
            self.stream.flush()

    def emit(self, record):
        try:
            log_data = record.msg
            timestamp = self.formatTime(record)
            level = record.levelname
            row = [timestamp, level] + log_data # Modified line
            self.writer.writerow(row)
            self.stream.flush()
        except Exception as e:
            print(f"CSV Logging error: {e}")

    def close(self):
        if self.stream:
            self.stream.close()

    def formatTime(self, record):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Create a rotating file handler
csv_handler = CSVHandler(
    log_file,
    mode='a',
    encoding='utf-8'
)

# Add the handler to the logger
logger.addHandler(csv_handler)

def init_db():
    """Initialize the SQLite database for storing translations."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS translations (
        id TEXT PRIMARY KEY,
        artist TEXT NOT NULL,
        track TEXT NOT NULL,
        translated_lyrics TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

def get_translation_from_db(artist_name, track_name):
    """Check if a translation exists in the database and return it if found."""
    # Create a unique key for the song
    song_key = f"{artist_name}|{track_name}"
    song_id = hashlib.md5(song_key.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT translated_lyrics FROM translations WHERE id = ?', (song_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        print(f"Translation found in cache for {track_name} by {artist_name}")
        return result[0]
    return None

def save_translation_to_db(artist_name, track_name, translated_lyrics):
    """Save a translation to the database."""
    # Create a unique key for the song
    song_key = f"{artist_name}|{track_name}"
    song_id = hashlib.md5(song_key.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO translations (id, artist, track, translated_lyrics)
    VALUES (?, ?, ?, ?)
    ''', (song_id, artist_name, track_name, translated_lyrics))
    conn.commit()
    conn.close()
    print(f"Translation saved to cache for {track_name} by {artist_name}")

# Initialize the database
init_db()

@app.route('/')
def index():
    spotify_username = None

    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager = spotipy.oauth2.SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                               client_secret=SPOTIFY_CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope='user-read-currently-playing',
                                               cache_handler=cache_handler,
                                               show_dialog=True)

    if request.args.get("code"):
        # Step 2. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # Step 1. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return f'<h2><a href="{auth_url}">Sign in</a></h2>'

    # Step 3. Signed in, display data
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    return render_template('web-page.html', spotify_username=spotify.me())
    # return f'<h2>Hi {spotify.me()["display_name"]}, ' \
    #        f'<small><a href="/sign_out">[sign out]<a/></small></h2>' \
    #        f'<a href="/playlists">my playlists</a> | ' \
    #        f'<a href="/currently_playing">currently playing</a> | ' \
    #     f'<a href="/lyrics">Lyrics</a>' \

@app.route('/currently_playing')
def currently_playing():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager = spotipy.oauth2.SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                               client_secret=SPOTIFY_CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    current_track = spotify.current_user_playing_track()
    track_name = current_track['item']['name']
    artist_name = current_track['item']['album']['artists'][0]['name']
    if current_track:
        return jsonify({
            'track_name': track_name,
            'artist_name': artist_name
            })
    return "No track currently playing."

def translate_to_japanese(text):
    """Translates the given text to Japanese using the Gemini API."""
    try:
        prompt = f"Your professional of translater who translate to japanese."\
                f"Translate the song lyrics to Japanese. "\
                f"If it's already in Japanese, return the original text. " \
                f"Make sure to keep the original meaning and context. "\
                f"In the output, please display the translation below the original text, and repeat this for each paragraph."\
                f"The beginning of the [[text]] may contain summary or background information about the song. Please ignore this."\
                f"Do not add any extra information. such as the explanation of meanings. please just answer the Transrated lyrics."\
                f"Here are the lyrics: {text}"

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Translation error: {e}")
        return "Translation failed"

@app.route('/lyrics')
def get_lyrics():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager = spotipy.oauth2.SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                               client_secret=SPOTIFY_CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    """
    Retrieves the currently playing song information from Spotify,
    fetches the lyrics from Genius, and translates them to Japanese if needed.
    Returns the song information, original lyrics, and translated lyrics as a JSON response.
    """
    try:
        # Get currently playing song
        current_track = spotify.current_user_playing_track()

        if current_track is None or current_track['item'] is None:
            return jsonify({
                'artist': 'No song playing',
                'track': 'No song playing',
                'translated_lyrics': 'No song playing'
            })

        track_name = current_track['item']['name']
        artist_name = current_track['item']['album']['artists'][0]['name']
        # just for debugging
        print(f"Track: {track_name}, Artist: {artist_name}")

        # ここでDBに既に翻訳された歌詞があるかどうかを既にあるかどうかを確認する。
        # もし、ある場合は、その歌詞を返す。
        # もし、ない場合は、Geniusから歌詞を取得する。
        # そして、その歌詞をDBに保存する。
        # Check if translation exists in database
        # Start timing the translation process
        get_lyrics_start_time = time.time()

        translated_lyrics = get_translation_from_db(artist_name, track_name)
        cache_used = translated_lyrics is not None

        # If not in database, Get lyrics from Genius then translate and save
        if translated_lyrics is None:
            # Get lyrics from Genius
            print(f"Searching for lyrics for {track_name} by {artist_name}")
            song = genius.search_song(track_name, artist=artist_name)
            if song is None:
                return jsonify({
                    'artist': artist_name,
                    'track': track_name,
                    'translated_lyrics': 'Lyrics not found'
                })

            lyrics = song.lyrics
            # print(f"Lyrics found: {lyrics}")

            # Translate lyrics to Japanese
            print(f"Now translating lyrics to Japanese")
            translated_lyrics = translate_to_japanese(lyrics)
            # Save translation to database
            save_translation_to_db(artist_name, track_name, translated_lyrics)

        
        # Calculate translation time
        get_lyrics_time = time.time() - get_lyrics_start_time
        print(f"get_lyrics time: {get_lyrics_time:.2f} seconds, Cache used: {'Yes' if cache_used else 'No'}")

        # Log the access
        # Get the remote address, which may be behind a proxy or load balancer
        if request:
            if request.headers.getlist("X-Forwarded-For"):
                remote_addr = request.headers.getlist("X-Forwarded-For")[0]
            elif hasattr(request, 'remote_addr'):
                remote_addr = request.remote_addr
            else:
                remote_addr = "Unknown"
        else:
            remote_addr = "Unknown"

        # Provide default values in case they are not available
        track_name = track_name if track_name else "Unknown Track"
        artist_name = artist_name if artist_name else "Unknown Artist"
        translated_lyrics = translated_lyrics if translated_lyrics else "No Lyrics"

        try:
            # Include translation time and cache usage in the log
            log_data = [track_name, artist_name, remote_addr, f"{get_lyrics_time:.2f}", "Yes" if cache_used else "No"]
            logger.log(logging.INFO, log_data)
        except Exception as e:
            print(f"Logging error: {e}")

        return jsonify({
            'artist': artist_name,
            'track': track_name,
            'translated_lyrics': translated_lyrics,
            'get_lyrics_time': f"{get_lyrics_time:.2f}",
            'cache_used': "Yes" if cache_used else "No"
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            'artist': 'Error',
            'track': 'Error',
            'translated_lyrics': str(e)
        })

@app.route('/force_lyrics')
def force_get_lyrics():
    """
    Retrieves the currently playing song information from Spotify,
    fetches the lyrics from Genius, and translates them to Japanese.
    This endpoint ignores the database cache and always performs a new translation.
    """
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager = spotipy.oauth2.SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                               client_secret=SPOTIFY_CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    try:
        # Get currently playing song
        current_track = spotify.current_user_playing_track()

        if current_track is None or current_track['item'] is None:
            return jsonify({
                'artist': 'No song playing',
                'track': 'No song playing',
                'translated_lyrics': 'No song playing'
            })

        track_name = current_track['item']['name']
        artist_name = current_track['item']['album']['artists'][0]['name']
        # just for debugging
        print(f"Track: {track_name}, Artist: {artist_name}")

        # Start timing the process
        get_lyrics_start_time = time.time()
        
        # Force new translation by ignoring cache
        print(f"Force re-getting lyrics for {track_name} by {artist_name}")
        
        # Get lyrics from Genius
        print(f"Searching for lyrics for {track_name} by {artist_name}")
        song = genius.search_song(track_name, artist=artist_name)
        if song is None:
            return jsonify({
                'artist': artist_name,
                'track': track_name,
                'translated_lyrics': 'Lyrics not found'
            })

        lyrics = song.lyrics
        # print(f"Lyrics found: {lyrics}")

        # Translate lyrics to Japanese
        print(f"Now translating lyrics to Japanese")
        translated_lyrics = translate_to_japanese(lyrics)
        
        # Save translation to database (update cache)
        save_translation_to_db(artist_name, track_name, translated_lyrics)
        
        # Calculate time
        get_lyrics_time = time.time() - get_lyrics_start_time
        print(f"Force re-get lyrics time: {get_lyrics_time:.2f} seconds")

        # Log the access
        # Get the remote address, which may be behind a proxy or load balancer
        if request:
            if request.headers.getlist("X-Forwarded-For"):
                remote_addr = request.headers.getlist("X-Forwarded-For")[0]
            elif hasattr(request, 'remote_addr'):
                remote_addr = request.remote_addr
            else:
                remote_addr = "Unknown"
        else:
            remote_addr = "Unknown"

        # Provide default values in case they are not available
        track_name = track_name if track_name else "Unknown Track"
        artist_name = artist_name if artist_name else "Unknown Artist"
        translated_lyrics = translated_lyrics if translated_lyrics else "No Lyrics"

        try:
            # Include time and force flag in the log
            log_data = [track_name, artist_name, remote_addr, f"{get_lyrics_time:.2f}", "Force"]
            logger.log(logging.INFO, log_data)
        except Exception as e:
            print(f"Logging error: {e}")

        return jsonify({
            'artist': artist_name,
            'track': track_name,
            'translated_lyrics': translated_lyrics,
            'get_lyrics_time': f"{get_lyrics_time:.2f}",
            'cache_used': "Force"
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            'artist': 'Error',
            'track': 'Error',
            'translated_lyrics': str(e)
        })

if __name__ == '__main__':
    app.run(debug=True, port=8080)
    # Uncomment the following line to run with SSL
    # app.run(debug=False, host="0.0.0.0", port=8080, ssl_context=('./cert/server.crt', './cert/server.key'))

