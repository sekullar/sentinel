import threading
import time
import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

NOTIFIED_IDS_PATH = "notified_mail_ids.json"


def _load_notified_ids() -> set:
    if os.path.exists(NOTIFIED_IDS_PATH):
        try:
            with open(NOTIFIED_IDS_PATH, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def _save_notified_ids(ids: set):
    try:
        with open(NOTIFIED_IDS_PATH, "w") as f:
            json.dump(list(ids), f)
    except Exception as e:
        print(f"[BG_SERVICE] notified_ids kaydedilemedi: {e}")


def check_gmail_loop(ask_ai_fn):
    """
    Her 60 saniyede bir Gmail'i kontrol eder. SADECE daha önce bildirilmemiş
    yeni mailleri bulur, ham veriyi ask_ai_fn'e (gerçek AI döngüsüne) verir -
    özetleme işini script değil, model kendisi yapar. Aynı mail bir daha
    bildirilmez (notified_mail_ids.json'da kalıcı olarak işaretlenir).
    """
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    notified_ids = _load_notified_ids()

    print(f"\n[BG_SERVICE] Arka plan mail nöbetçisi başlatıldı (60 sn döngü, {len(notified_ids)} mail zaten bildirilmiş)")

    while True:
        try:
            if not os.path.exists('gmail_tokens.json'):
                print("[BG_SERVICE] gmail_tokens.json bulunamadı.")
                time.sleep(60)
                continue

            creds = Credentials.from_authorized_user_file('gmail_tokens.json', SCOPES)
            service = build('gmail', 'v1', credentials=creds)

            results = service.users().messages().list(userId='me', q='is:unread', maxResults=5).execute()
            messages = results.get('messages', [])

            new_messages = [m for m in messages if m['id'] not in notified_ids]

            if new_messages:
                print(f"[BG_SERVICE] {len(new_messages)} YENİ mail bulundu, modele iletiliyor...")

                output = []
                for msg in new_messages:
                    msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                    headers = msg_data['payload']['headers']
                    sender = next((h['value'] for h in headers if h['name'] == 'From'), "Bilinmeyen Gönderici")
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "Konu Yok")
                    snippet = msg_data.get('snippet', '')
                    output.append(f"[Gönderen: {sender}, Konu: {subject}, İçerik: {snippet}]")
                    notified_ids.add(msg['id'])

                raw_data = " || ".join(output)

                # Modele, mail_plugin.check_mail ile AYNI talimatı veriyoruz -
                # tutarlılık için. Bu bir SYSTEM_EVENT, kullanıcı yazmadı.
                synthetic_prompt = (
                    f"SYSTEM_EVENT (yeni_mail): Gmail'de {len(new_messages)} yeni okunmamış "
                    f"mail geldi.\n"
                    f"HAM VERİ:\n{raw_data}\n\n"
                    "SİSTEM UYARISI: Bu mailleri KESİNLİKLE alt alta madde madde listeleme! "
                    "Kendi inisiyatifini kullan, acil/önemli olanı vurgula ve tümünü tek bir "
                    "doğal, akıcı paragraf halinde kullanıcıya özetle."
                )

                ask_ai_fn(synthetic_prompt)
                _save_notified_ids(notified_ids)
            else:
                print("[BG_SERVICE] Yeni (bildirilmemiş) mail yok.")

        except Exception as e:
            print(f"[BG_SERVICE] Hata: {e}")

        time.sleep(60)


def start_all_services(ask_ai_fn):
    """Tüm arka plan görevlerini toplayıp başlatan ana fonksiyon."""
    mail_thread = threading.Thread(
        target=check_gmail_loop,
        args=(ask_ai_fn,),
        daemon=True,
    )
    mail_thread.start()