from flask import Flask, jsonify, session, request, redirect
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import lyricsgenius
import google.generativeai as genai
import os
from dotenv import load_dotenv

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
# REDIRECT_URI = os.getenv('REDIRECT_URI')
# same as the one in Spotify app settings
REDIRECT_URI = 'http://127.0.0.1:8080'

# Spotipy setup
client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# LyricsGenius setup
genius = lyricsgenius.Genius(GENIUS_API_TOKEN)

# Gemini setup
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')


@app.route('/')
def index():

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
    return f'<h2>Hi {spotify.me()["display_name"]}, ' \
           f'<small><a href="/sign_out">[sign out]<a/></small></h2>' \
           f'<a href="/playlists">my playlists</a> | ' \
           f'<a href="/currently_playing">currently playing</a> | ' \
        f'<a href="/lyrics">Lyrics</a>' \

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
    track = spotify.current_user_playing_track()
    if track:
        return jsonify(track)
    return "No track currently playing."



def translate_to_japanese(text):
    """Translates the given text to Japanese using the Gemini API."""
    try:
        prompt = f"Translate the following English text to Japanese: {text}"
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
                'original_lyrics': 'No song playing',
                'translated_lyrics': 'No song playing'
            })

        track_name = current_track['item']['name']

        artist_name = current_track['item']['album']['artists'][0]['name']
        # just for debugging
        print(f"Track: {track_name}, Artist: {artist_name}")

        # Get lyrics from Genius
        print(f"Searching for lyrics for {track_name} by {artist_name}")
        song = genius.search_song(track_name, artist=artist_name)
        if song is None:
            return jsonify({
                'artist': artist_name,
                'track': track_name,
                'original_lyrics': 'Lyrics not found',
                'translated_lyrics': 'Lyrics not found'
            })

        lyrics = song.lyrics

        # Translate to Japanese if lyrics are in English
        print(f"Now translating lyrics to Japanese")
        translated_lyrics = translate_to_japanese(lyrics)

        return jsonify({
            'artist': artist_name,
            'track': track_name,
            'original_lyrics': lyrics,
            'translated_lyrics': translated_lyrics
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            'artist': 'Error',
            'track': 'Error',
            'original_lyrics': str(e),
            'translated_lyrics': str(e)
        })


if __name__ == '__main__':
    app.run(debug=True, port=8080)
