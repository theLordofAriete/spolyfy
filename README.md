# Spolyfy
Spotify + Lyrics

## 前準備
### Spotifyの準備
1. Spotifyのダッシュボードにアクセス
https://developer.spotify.com/dashboard
2. 「Creat app」を選択
3. 適宜入力する
「Redirect URIs」は.envのREDIRECT_URIと同じアクセス情報にする。  
例:http://127.0.0.1:8080  
注意:localhostは使えない。  

Client ID,Client secretを控えておく

### HTTP"S"の準備
ローカル以外で動かす場合は、spotifyのRedirect URIはHTTPS出なければならないという制限に引っかかる。
ローカル以外で動かす場合は、FlaskをHTTPSサーバーとして動かす必要がある。
https://developer.spotify.com/documentation/web-api/concepts/redirect_uri

server.keyとserver.csr,server.crt作成
```
openssl genrsa 2048 > server.key
openssl req -new -key server.key > server.csr
openssl x509 -req -days 3650 -signkey server.key < server.csr > server.crt
```

ファイルを移動する
```
mkdir cert
mv server.* ./cert
```

.envのREDIRECT_URIをhttpsに変更する
```
REDIRECT_URI='https://192.168.1.1:8080'
```

spolyfy_app.pyの一番最後の行を編集する
```
    app.run(debug=False, host="0.0.0.0", port=8080, ssl_context=('./cert/server.crt', './cert/server.key'))
```


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
