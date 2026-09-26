"""
Steam - oyun başlatma eklentisi.
Resmi bir "oyunu uzaktan başlat" API'si yok; Steam'in kendisi steam://run/<appid>
URI şemasını kullanıyor (masaüstü kısayolları da aynı mekanizmayı tetikliyor).
Appid'yi hardcode etmek yerine appmanifest_*.acf dosyalarından otomatik buluyoruz.
"""
import os
import re
import glob
import platform
import subprocess

# Native Windows ve WSL'den Windows'a bakış - ikisini de dener
CANDIDATE_STEAMAPPS_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps",
    "/mnt/c/Program Files (x86)/Steam/steamapps",
]


def _parse_library_folders(steamapps_dir: str) -> list[str]:
    """libraryfolders.vdf'i okuyup ek kütüphane yollarını (harici disk vb.) bulur."""
    paths = [steamapps_dir]
    vdf_path = os.path.join(steamapps_dir, "libraryfolders.vdf")
    if not os.path.isfile(vdf_path):
        return paths

    with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    for match in re.finditer(r'"path"\s*"([^"]+)"', content):
        raw_path = match.group(1).replace("\\\\", "\\")
        extra = os.path.join(raw_path, "steamapps")
        if os.path.isdir(extra) and extra not in paths:
            paths.append(extra)
    return paths


def _list_installed_games() -> dict[str, str]:
    """{oyun_adi_kucuk_harf: appid} sözlüğü döner."""
    games = {}
    for base_dir in CANDIDATE_STEAMAPPS_DIRS:
        if not os.path.isdir(base_dir):
            continue
        for lib_dir in _parse_library_folders(base_dir):
            for manifest in glob.glob(os.path.join(lib_dir, "appmanifest_*.acf")):
                try:
                    with open(manifest, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    continue
                appid_match = re.search(r'"appid"\s*"(\d+)"', content)
                name_match = re.search(r'"name"\s*"([^"]+)"', content)
                if appid_match and name_match:
                    games[name_match.group(1).lower()] = appid_match.group(1)
    return games


def launch_game(game_name: str) -> str:
    """
    Verilen isme en yakın eşleşen yüklü oyunu bulup steam://run/<appid> ile başlatır.
    """
    games = _list_installed_games()
    if not games:
        return "ERROR: Steam kütüphanesi bulunamadı (steamapps klasörü tespit edilemedi)"

    query = game_name.lower().strip()
    match = next((name for name in games if query in name or name in query), None)

    if not match:
        sample = ", ".join(list(games.keys())[:10])
        return f"ERROR: empty_result - '{game_name}' kütüphanede bulunamadı. Yüklü olanlardan bazıları: {sample}"

    appid = games[match]
    uri = f"steam://run/{appid}"

    try:
        if platform.system() == "Windows":
            os.startfile(uri)
        else:
            # WSL içinden Windows'a - cmd.exe üzerinden URI'yi tetikle
            subprocess.run(["cmd.exe", "/c", "start", "", uri], check=True)
    except Exception as e:
        return f"ERROR: oyun başlatılamadı ({e})"

    return f"'{match}' başlatıldı (Steam appid: {appid})."