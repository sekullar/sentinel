"""
Brave Search API üzerinden web araması.
Ön koşul: BRAVE_API_KEY ortam değişkeni ayarlı olmalı (brave.com/search/api'den ücretsiz kayıt).
"""
import os
import requests

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RESULTS = 5


def search(query: str) -> str:
    """
    Brave'e sorguyu gönderir, ilk birkaç sonucu (başlık + özet) düz metin
    olarak döner. Bağlantı/API-key hatası ya da boş sonuç durumunda modele
    anlaşılır bir hata metni döner (crash etmez, model bunu görüp yorumlayabilsin).
    """
    
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return "ERROR: web_search bağlantı hatası (BRAVE_API_KEY ortam değişkeni ayarlı değil)"

    try:
        response = requests.get(
            BRAVE_URL,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            params={"q": query, "count": MAX_RESULTS},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"ERROR: web_search bağlantı hatası ({e})"

    data = response.json()
    results = data.get("web", {}).get("results", [])[:MAX_RESULTS]

    if not results:
        return "ERROR: empty_result"

    lines = []
    for r in results:
        title = r.get("title", "")
        snippet = r.get("description", "")
        url = r.get("url", "")
        lines.append(f"- {title}: {snippet} ({url})")

    return "\n".join(lines)

