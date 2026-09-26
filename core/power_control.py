"""
Sistem güç/kilit kontrolü.
Kilitleme geri döndürülebilir, onaysız çalışır.
Kapatma (shutdown) GERİ DÖNDÜRÜLEMEZ - bu yüzden modelin itaatine güvenmek
yerine KOD SEVİYESİNDE de bir güvenlik payı var: her zaman gecikmeli
zamanlanır (varsayılan 120sn) ve ayrı bir cancel_shutdown ile geri alınabilir.
"""
import subprocess


def lock_computer(query: str = "") -> str:
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=10)
        return "Bilgisayar kilitlendi."
    except Exception as e:
        return f"ERROR: kilitleme başarısız ({e})"


def request_shutdown(query: str = "") -> str:
    """
    query içinde bir sayı varsa (saniye) o kadar gecikmeyle kapatır,
    yoksa varsayılan 120 saniye kullanılır - kullanıcının fikrini
    değiştirmesi için bir güvenlik penceresi.
    """
    delay = 120
    digits = "".join(ch for ch in query if ch.isdigit())
    if digits:
        delay = int(digits)

    try:
        subprocess.run(["shutdown.exe", "/s", "/t", str(delay)], timeout=10)
        return (f"Bilgisayar {delay} saniye içinde kapanacak şekilde zamanlandı. "
                f"Vazgeçilirse cancel_shutdown ile iptal edilebilir.")
    except Exception as e:
        return f"ERROR: kapatma zamanlanamadı ({e})"


def cancel_shutdown(query: str = "") -> str:
    try:
        subprocess.run(["shutdown.exe", "/a"], timeout=10)
        return "Zamanlanmış kapatma iptal edildi."
    except Exception as e:
        return f"ERROR: iptal başarısız oldu, muhtemelen zaten zamanlanmış bir kapatma yoktu ({e})"