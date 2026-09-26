"""
Sistem durumu okuma - şimdilik sadece pil yüzdesi.
PowerShell/WMI üzerinden çalışır - hem native Windows'ta hem WSL'den
(interop ile powershell.exe çağrılarak) aynı şekilde işliyor.
"""
import subprocess


def get_battery_percent() -> str:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-CimInstance -ClassName Win32_Battery).EstimatedChargeRemaining"],
            capture_output=True, text=True, timeout=10,
        )
        value = result.stdout.strip()
        if not value:
            return "ERROR: pil bilgisi alınamadı (masaüstü PC ise pil olmayabilir)"
        return f"Pil: %{value}"
    except Exception as e:
        return f"ERROR: sistem durumu bağlantı hatası ({e})"


def get_status(query: str = "") -> str:
    return get_battery_percent()