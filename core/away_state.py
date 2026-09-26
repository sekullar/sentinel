"""
Away mode durumu - basit, thread-safe bir bayrak.
Kaynak: kullanıcının "ben gidiyorum" / "away modunu aç" gibi doğal ifadeleri -
model bunu fark edip toggle_away_mode tool'unu çağırıyor, elle bir komut
beklemiyoruz.
"""
import threading
import datetime

_lock = threading.Lock()
_active = False
_started_at = None


def toggle(query: str) -> str:
    """
    query içinde "kapat"/"off"/"geldim" gibi bir kelime geçiyorsa kapatır,
    aksi halde açar (varsayılan: açma - model bu tool'u zaten "gidiyorum"
    niyetini fark ettiğinde çağıracağı için).
    """
    global _active, _started_at
    q = query.lower()

    with _lock:
        if any(word in q for word in ["kapat", "off", "geldim", "kapali", "kapalı"]):
            _active = False
            _started_at = None
            return "Away mode kapatıldı."
        else:
            _active = True
            _started_at = datetime.datetime.now()
            return "Away mode açıldı."


def is_active() -> bool:
    with _lock:
        return _active


def elapsed_minutes() -> float:
    with _lock:
        if _started_at is None:
            return 0.0
        return (datetime.datetime.now() - _started_at).total_seconds() / 60