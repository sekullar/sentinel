"""
Away mode aktifken periyodik olarak modele durum bildirimi (SYSTEM_EVENT)
gönderen arka plan servisi. background_tasks.py (mail nöbetçisi) ile AYNI
desen: ask_ai_fn üzerinden gerçek AI döngüsüne besleniyor - script kendi
kararını vermiyor, sadece veriyi topluyor, karar tamamen modele ait.
"""
import time
import threading
from core import away_state, system_monitor

CHECK_INTERVAL_SECONDS = 60  # 10 dakika


def away_scheduler_loop(ask_ai_fn):
    print("\n[BG_SERVICE] Away mode scheduler başlatıldı (10 dk döngü, away mode kapalıyken bekler)")

    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)

        if not away_state.is_active():
            continue

        elapsed = away_state.elapsed_minutes()
        battery_info = system_monitor.get_battery_percent()

        event_text = (
            f"SYSTEM_EVENT (away_mode, elapsed: {elapsed:.0f}dk): {battery_info}\n"
            "Bu bir arka plan olayıdır, kullanıcı yazmadı. Away mode sistem "
            "promptundaki talimatlara göre değerlendir."
        )
        print(f"[BG_SERVICE] Away mode event gönderiliyor (elapsed={elapsed:.0f}dk, {battery_info})")
        ask_ai_fn(event_text)


def start(ask_ai_fn):
    t = threading.Thread(target=away_scheduler_loop, args=(ask_ai_fn,), daemon=True)
    t.start()