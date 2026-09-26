"""
Sentinel - Spotify eklentisi (core/spotify_plugin.py)

Tek araç: spotify_play <şarkı adı [sanatçı]>

Kurulum:
  pip install spotipy
  export SPOTIPY_CLIENT_ID=...
  export SPOTIPY_CLIENT_SECRET=...
  export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback   (dashboard'daki ile BİREBİR aynı olmalı)
  python core/spotify_plugin.py     <- bir kez giriş yapmak için

Not: Hata metinleri web_search ile aynı mantıkta "ERROR: ..." ile başlar,
böylece system prompt'taki hata yönetimi kuralları aynen işler.
"""
import os

import requests
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "user-modify-playback-state user-read-playback-state"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"
CACHE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".spotify_cache")
)


def _auth_manager() -> SpotifyOAuth:
    return SpotifyOAuth(
        scope=SCOPE,
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT),
        cache_path=CACHE_PATH,
        open_browser=False,  # WSL'de tarayıcı açmaya çalışıp takılmasın
    )


def _client():
    """Kayıtlı token varsa (gerekirse yenileyerek) client döner, yoksa None."""
    auth = _auth_manager()
    token = auth.get_cached_token()
    if not token:
        return None
    return spotipy.Spotify(auth_manager=auth)


def _pick_device(sp):
    """Aktif cihazı seç; aktif yoksa ilk görünen cihazı; hiç yoksa None."""
    devices = sp.devices().get("devices", [])
    if not devices:
        return None
    for d in devices:
        if d.get("is_active"):
            return d["id"]
    return devices[0]["id"]


def play(query: str) -> str:
    query = query.strip()
    if not query:
        return "ERROR: empty_result (boş sorgu, şarkı adını yaz)"

    try:
        sp = _client()
        if sp is None:
            return (
                "ERROR: spotify_auth (giriş yapılmamış). YENİDEN DENEME. Kullanıcıya "
                "'python core/spotify_plugin.py' komutuyla bir kez giriş yapması gerektiğini söyle."
            )

        items = sp.search(q=query, type="track", limit=5)["tracks"]["items"]
        if not items:
            return "ERROR: empty_result (Spotify'da bu sorguyla şarkı bulunamadı)"
        track = items[0]

        device_id = _pick_device(sp)
        if device_id is None:
            return (
                "ERROR: spotify_no_device (açık Spotify cihazı yok). YENİDEN DENEME. "
                "Kullanıcıya Windows'ta Spotify uygulamasını açıp bir kez bir şey çalıp "
                "durdurmasını söyle."
            )

        sp.start_playback(device_id=device_id, uris=[track["uri"]])
        artists = ", ".join(a["name"] for a in track["artists"])
        return f"Çalınıyor: {track['name']} - {artists}"

    except SpotifyException as e:
        if e.http_status == 403:
            return (
                "ERROR: spotify_premium (oynatma kontrolü reddedildi, Spotify Premium "
                "gerekiyor olabilir). YENİDEN DENEME."
            )
        if e.http_status == 404:
            return "ERROR: spotify_no_device (cihaz bulunamadı). YENİDEN DENEME."
        return f"ERROR: spotify (HTTP {e.http_status}). YENİDEN DENEME."
    except requests.exceptions.RequestException as e:
        return f"ERROR: spotify bağlantı hatası ({type(e).__name__})"
    except Exception as e:  # eksik env değişkeni vb.
        return f"ERROR: spotify ({type(e).__name__}: {e}). YENİDEN DENEME."


if __name__ == "__main__":
    # Tek seferlik giriş: linki Windows tarayıcında aç, izin ver, yönlendirilen
    # (hata sayfası görünse de) adres çubuğundaki URL'yi buraya yapıştır.
    auth = _auth_manager()
    print("Bu linki tarayıcıda aç ve izin ver:\n")
    print(auth.get_authorize_url())
    redirected = input("\nİzinden sonra adres çubuğundaki URL'yi yapıştır: ").strip()
    code = auth.parse_response_code(redirected)
    auth.get_access_token(code)
    print("Giriş tamam, token kaydedildi.")