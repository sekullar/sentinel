"""
Google Calendar entegrasyonu.
Ön koşul: Google Cloud Console'dan indirilen credentials.json bu klasöre (core/)
konmalı. İlk çalıştırmada tarayıcı açılıp izin isteyecek, sonrasında token.json
otomatik oluşup yenilenir - bir daha tarayıcı açılmaz.
"""
import os
import re
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")


def _normalize_datetime(dt_str: str) -> str:
    """
    Google Calendar API, dateTime alanının RFC3339 (saniye dahil) olmasını
    zorunlu tutuyor ama hata vermeden önce hiçbir açıklayıcı mesaj vermiyor.
    Model saniyeyi atlarsa (YYYY-MM-DDTHH:MM), burada otomatik ":00" ekleriz -
    modelin format hassasiyetine güvenmek yerine kodun kendisi garanti eder.
    """
    dt_str = dt_str.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", dt_str):
        return dt_str + ":00"
    return dt_str


def _get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def list_upcoming(query: str = "") -> str:
    """Önümüzdeki 7 gündeki etkinlikleri döner."""
    try:
        service = _get_service()
        now = datetime.datetime.utcnow().isoformat() + "Z"
        week_later = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=week_later,
            maxResults=10, singleEvents=True, orderBy="startTime",
        ).execute()
        events = events_result.get("items", [])
    except Exception as e:
        return f"ERROR: takvim bağlantı hatası ({e})"

    if not events:
        return "ERROR: empty_result"

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        lines.append(f"- {event.get('summary', '(başlıksız)')}: {start}")
    return "\n".join(lines)


def create_event(query: str) -> str:
    """
    Beklenen format: "başlık|YYYY-MM-DDTHH:MM|YYYY-MM-DDTHH:MM"
    (başlık|başlangıç|bitiş) - sistem promptu modele bu formatı öğretiyor.
    """
    parts = query.split("|")
    if len(parts) != 3:
        return "ERROR: takvim etkinliği oluşturulamadı (format hatası: 'başlık|başlangıç|bitiş' bekleniyor)"

    title, start, end = (p.strip() for p in parts)
    start, end = _normalize_datetime(start), _normalize_datetime(end)
    try:
        service = _get_service()
        event = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "Europe/Istanbul"},
            "end": {"dateTime": end, "timeZone": "Europe/Istanbul"},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
    except Exception as e:
        return f"ERROR: takvim bağlantı hatası ({e})"

    return f"Etkinlik oluşturuldu: {created.get('htmlLink')}"


def _find_event_by_title(service, title_query: str, days_ahead: int = 60):
    """
    Önümüzdeki `days_ahead` gün içinde başlığı title_query'yi İÇEREN ilk etkinliği
    bulur (case-insensitive). Bulamazsa None döner.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    later = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).isoformat() + "Z"
    events_result = service.events().list(
        calendarId="primary", timeMin=now, timeMax=later,
        maxResults=50, singleEvents=True, orderBy="startTime",
    ).execute()
    events = events_result.get("items", [])

    query_lower = title_query.strip().lower()
    for event in events:
        if query_lower in event.get("summary", "").lower():
            return event
    return None


def delete_event(query: str) -> str:
    """
    Beklenen format: "silinecek_etkinliğin_başlığı" (tam başlık gerekmez, içeren yeterli).
    DİKKAT: bu geri döndürülemez bir işlem - yanlış eşleşme riskine karşı, sadece
    önümüzdeki 60 gün içindeki İLK eşleşen etkinliği siler.
    """
    title_query = query.strip()
    if not title_query:
        return "ERROR: takvim etkinliği silinemedi (hangi etkinlik olduğu belirtilmemiş)"

    try:
        service = _get_service()
        event = _find_event_by_title(service, title_query)
        if event is None:
            return f"ERROR: empty_result - '{title_query}' ile eşleşen bir etkinlik bulunamadı"

        service.events().delete(calendarId="primary", eventId=event["id"]).execute()
    except Exception as e:
        return f"ERROR: takvim bağlantı hatası ({e})"

    start = event["start"].get("dateTime", event["start"].get("date"))
    return f"Silindi: '{event.get('summary')}' ({start})"


def update_event(query: str) -> str:
    """
    Beklenen format: "aranacak_başlık|yeni_başlık|yeni_başlangıç|yeni_bitiş"
    (YYYY-MM-DDTHH:MM formatında). Aranacak başlıkla eşleşen önümüzdeki 60 gün
    içindeki İLK etkinlik güncellenir.
    """
    parts = query.split("|")
    if len(parts) != 4:
        return ("ERROR: takvim etkinliği güncellenemedi (format hatası: "
                "'aranacak_başlık|yeni_başlık|yeni_başlangıç|yeni_bitiş' bekleniyor)")

    search_title, new_title, new_start, new_end = (p.strip() for p in parts)
    new_start, new_end = _normalize_datetime(new_start), _normalize_datetime(new_end)

    try:
        service = _get_service()
        event = _find_event_by_title(service, search_title)
        if event is None:
            return f"ERROR: empty_result - '{search_title}' ile eşleşen bir etkinlik bulunamadı"

        event["summary"] = new_title
        event["start"] = {"dateTime": new_start, "timeZone": "Europe/Istanbul"}
        event["end"] = {"dateTime": new_end, "timeZone": "Europe/Istanbul"}

        updated = service.events().update(
            calendarId="primary", eventId=event["id"], body=event
        ).execute()
    except Exception as e:
        return f"ERROR: takvim bağlantı hatası ({e})"

    return f"Güncellendi: {updated.get('htmlLink')}"