import os
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def _parse_query(query):
    parts = [p.strip() for p in query.split("|")]
    account = parts[0].lower() if len(parts) > 0 else ""
    return account, parts

def check_mail(query):
    account, _ = _parse_query(query)
    
    if account != "gmail":
        return f"ERROR: Şu an sadece 'gmail' hesabı aktif. Kullanıcıya bunu outlook ile yapamadığını söyle."
    
    print("\n[DEBUG] Sentinel check_mail aracını tetikledi...")
    
    try:
        if not os.path.exists('gmail_tokens.json'):
            return "ERROR: Sistemde gmail_tokens.json bulunamadı."
            
        creds = Credentials.from_authorized_user_file('gmail_tokens.json')
        service = build('gmail', 'v1', credentials=creds)
        
        # Son 5 maili çekiyoruz
        results = service.users().messages().list(userId='me', maxResults=5).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return "empty_result: Gelen kutusunda hiç e-posta bulunamadı."
            
        # (check_mail içindeki for döngüsü bölümü)
        # Eskiden ["İşte son 5 mailin özeti:"] yazan yeri siliyoruz.
        output = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = msg_data['payload']['headers']
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "Bilinmeyen Gönderici")
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "Konu Yok")
            snippet = msg_data.get('snippet', '')
            
            # Veriyi güzel bir liste gibi değil, ham bir log formatında yolluyoruz
            output.append(f"[Gönderen: {sender}, Konu: {subject}, İçerik: {snippet}]")
            
        print("[DEBUG] Mailler başarıyla çekildi.")
        
        # Asıl Zeka Burada: Modelin aracı okuduğu an ezmesini engelleyecek kesin emir
        raw_data = " || ".join(output)
        return f"HAM VERİ:\n{raw_data}\n\nSİSTEM UYARISI: Bu mailleri KESİNLİKLE alt alta madde madde listeleme! Kendi inisiyatifini kullan, acil/önemli olanı vurgula ve tümünü tek bir doğal, akıcı paragraf halinde bana özetle."
        
    except Exception as e:
        print(f"[DEBUG] check_mail Hatası: {e}")
        return f"ERROR: Mailler okunurken sistemsel bir hata oluştu: {e}"

def send_mail(query):
    account, parts = _parse_query(query)
    
    if account != "gmail":
        return "ERROR: Sadece gmail aktif."
    
    if len(parts) < 4:
        return "ERROR: Eksik parametre girdin. Format 'hesap|kime|konu|içerik' olmalı."
    
    target = parts[1]
    subject = parts[2]
    body = parts[3]
    
    print(f"\n[DEBUG] Sentinel send_mail aracını tetikledi. Kime: {target}")
    
    try:
        if not os.path.exists('gmail_tokens.json'):
            return "ERROR: Sistemde gmail_tokens.json bulunamadı."
            
        creds = Credentials.from_authorized_user_file('gmail_tokens.json')
        service = build('gmail', 'v1', credentials=creds)
        
        message = MIMEText(body)
        message['to'] = target
        message['subject'] = subject
        
        raw_message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
        
        service.users().messages().send(userId='me', body=raw_message).execute()
        
        print("[DEBUG] Mail başarıyla gönderildi.")
        return f"[OK] Mail başarıyla {target} adresine gönderildi."
        
    except Exception as e:
        print(f"[DEBUG] send_mail Hatası: {e}")
        return f"ERROR: Mail gönderilirken yetki veya sistem hatası oluştu: {e}"