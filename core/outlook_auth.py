import urllib.parse
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8888/callback"
# offline_access, şifre sormadan yenileme yapması için şarttır
SCOPES = "offline_access Mail.Read" 

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'code' in query_components:
            auth_code = query_components['code'][0]
            self.wfile.write(b"<h1>Basarili!</h1><p>Bu pencereyi kapatabilirsiniz.</p>")
        else:
            self.wfile.write(b"<h1>Hata!</h1><p>Yetkilendirme kodu bulunamadi.</p>")

def get_tokens():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("HATA: Terminalde export komutlarını çalıştırmamışsın.")
        return

    global auth_code
    auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&response_mode=query&scope={urllib.parse.quote(SCOPES)}"
    
    print("1. Lütfen aşağıdaki linke tıklayıp öğrenci hesabınızla giriş yapın:\n")
    print(auth_url)
    print("\n2. Tarayıcıdan yanıt bekleniyor (8888 portu dinleniyor)...")

    server_address = ('localhost', 8888)
    httpd = HTTPServer(server_address, CallbackHandler)
    
    while auth_code is None:
        httpd.handle_request()

    print("\nYetki kodu başarıyla alındı. Kalıcı token'a çevriliyor...")

    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        'client_id': CLIENT_ID,
        'scope': SCOPES,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'client_secret': CLIENT_SECRET
    }

    response = requests.post(token_url, data=data)
    token_data = response.json()

    if 'refresh_token' in token_data:
        with open("outlook_tokens.json", "w") as f:
            json.dump(token_data, f, indent=4)
        print("\nHARİKA! 'outlook_tokens.json' dosyası başarıyla oluşturuldu.")
    else:
        print("\nBir hata oluştu:", token_data)

if __name__ == "__main__":
    get_tokens()