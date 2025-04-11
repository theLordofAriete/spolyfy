# Spolyfy
Spotify + Lyrics

## 前準備
1. Spotifyのダッシュボードにアクセス
https://developer.spotify.com/dashboard
2. 「Creat app」を選択
3. 適宜入力する
「Redirect URIs」は.envのSPOTIPY_REDIRECT_URIと同じアクセス情報にする。  
例:http://127.0.0.1:8080  
注意:localhostは使えない。  

Client ID,Client secretを控えておく


## Install
Python3 and pip3
To install the required Python modules, run:
```bash
pip install flask spotipy lyricsgenius google-generativeai python-dotenv
```

### Troubleshooting


## run the app
1. Copy .env.sample to .env
2. Edit .env
3. run spolyfy_app.py
```bash
python3 spolyfy_app.py
```
