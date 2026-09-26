import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# İzinler: Okuma, okundu olarak işaretleme ve gönderme yetkilerini kapsar
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def setup_gmail():
    creds = None
    
    # Daha önce oluşturulmuş bir token varsa onu kullan
    if os.path.exists('gmail_tokens.json'):
        creds = Credentials.from_authorized_user_file('gmail_tokens.json', SCOPES)
    
    # Token yoksa veya süresi dolmuşsa yeni yetki al
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Mevcut token yenileniyor...")
            creds.refresh(Request())
        else:
            print("Tarayıcı açılıyor, lütfen Gmail hesabınızla onay verin...")
            # Senin mevcut credentials.json dosyanı kullanıyoruz
            flow = InstalledAppFlow.from_client_secrets_file('core/credentials.json', SCOPES)
            # Port 8888 üzerinden yerel sunucu açıp onayı yakalar
            creds = flow.run_local_server(port=8888)
        
        # Gelecekte Sentinel'in şifresiz kullanabilmesi için kaydet
        with open('gmail_tokens.json', 'w') as token:
            token.write(creds.to_json())
        print("\nHARİKA! 'gmail_tokens.json' başarıyla oluşturuldu ve kaydedildi.")
    else:
        print("\nSistem zaten yetkili. 'gmail_tokens.json' kullanıma hazır.")

if __name__ == '__main__':
    setup_gmail()