"""
Telegram entegrasyonu - basit long-polling üzerinden, ekstra kütüphane gerektirmez.
Ön koşul: TELEGRAM_TOKEN ortam değişkeni ayarlı olmalı (@BotFather'dan alınır).

GÜVENLİK: bota ilk yazan kişi otomatik olarak "sahip" (owner) olarak kaydedilir,
sonrasında SADECE o chat_id'den gelen mesajlar işlenir. Yani token'ı kimseyle
paylaşma, ve botu ilk kez sen çalıştırdığında ilk mesajı SEN at.
"""
import os
import time
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

_owner_chat_id = None
_last_update_id = 0


def send_message(chat_id: int, text: str):
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        print(f"[telegram] mesaj gönderilemedi: {e}")


def send_document(chat_id: int, file_path: str) -> bool:
    """Yerel bir dosyayı Telegram'a belge olarak yükler. Başarılıysa True,
    değilse False döner - çağıran taraf (file_sender) bunu ERROR: olarak
    modele iletebilsin diye burada exception fırlatmıyoruz."""
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": f},
                timeout=60,
            )
        resp.raise_for_status()
        return True
    except (OSError, requests.exceptions.RequestException) as e:
        print(f"[telegram] dosya gönderilemedi: {e}")
        return False


def poll_updates(on_message):
    """
    Sonsuz döngüde Telegram'dan yeni mesaj bekler (30sn long-polling).
    Yeni bir mesaj geldiğinde on_message(text, chat_id) çağrılır.
    """
    global _owner_chat_id, _last_update_id

    if not TOKEN:
        print("[telegram] TELEGRAM_TOKEN ayarlı değil, Telegram devre dışı.")
        return

    print("[telegram] dinleniyor... (ilk mesajı sen at, sahiplik öyle kaydedilir)")
    while True:
        try:
            resp = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"offset": _last_update_id + 1, "timeout": 30},
                timeout=35,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])
        except requests.exceptions.RequestException as e:
            print(f"[telegram] bağlantı hatası, 5sn sonra tekrar denenecek: {e}")
            time.sleep(5)
            continue

        for update in updates:
            _last_update_id = update["update_id"]
            message = update.get("message")
            if not message or "text" not in message:
                continue

            chat_id = message["chat"]["id"]

            if _owner_chat_id is None:
                _owner_chat_id = chat_id
                print(f"[telegram] sahip kaydedildi: chat_id={chat_id}")
            elif chat_id != _owner_chat_id:
                continue  # başkası yazdıysa tamamen görmezden gel

            on_message(message["text"], chat_id)


def send_typing(chat_id: int):
    try:
        requests.post(f"{BASE_URL}/sendChatAction", data={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except requests.exceptions.RequestException:
        pass


def get_owner_chat_id():
    """Şu ana kadar kaydedilmiş sahip chat_id'sini döner, henüz kimse yazmadıysa None."""
    return _owner_chat_id