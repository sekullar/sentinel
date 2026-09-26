"""
Sentinel - Dosya Gönderme Eklentisi (file_sender.py)

İzinli klasörler (SENTINEL_ALLOWED_DIRECTORIES) içindeki bir dosyayı
Telegram'a gönderir. file_explorer'dan AYRI bir plugin dosyası, ama izinli-
klasör doğrulamasını (resolve_allowed_path) core.file_explorer'dan import
ediyor - iki modülün "izinli" tanımı asla birbirinden sapmasın diye.
"""
import os
from core.file_explorer import resolve_allowed_path

# Telegram Bot API'nin sendDocument için belge boyutu limiti (~50 MB).
MAX_TELEGRAM_FILE_BYTES = 50 * 1024 * 1024


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def send_file(query: str) -> str:
    """
    query: gönderilecek dosyanın (izinli klasör altındaki) yolu.

    Dönüş: TOOL_RESULT olarak modele gidecek metin (ERROR: ile başlayan
    durumlar mevcut main.py hata-yönetimi bloğuyla uyumlu).
    """
    file_path = query.strip()

    if not file_path:
        return "ERROR: dosya yolu belirtilmedi"

    # 1) Telegram bağlı mı? (owner henüz bota yazmadıysa gönderim yapılamaz)
    from core import telegram_bot  # döngüsel importu önlemek için burada
    owner_chat_id = telegram_bot.get_owner_chat_id()

    if owner_chat_id is None:
        return "ERROR: telegram_not_connected (henüz kimse bota Telegram'dan yazmadı, gönderilecek adres yok)"

    # 2) İzinli klasör doğrulaması (core.file_explorer ile AYNI mantık)
    try:
        real_path = resolve_allowed_path(file_path)
    except ValueError as e:
        return f"ERROR: {e}"

    if not os.path.isfile(real_path):
        return f"ERROR: dosya bulunamadı ya da bir klasör: {file_path}"

    # 3) Boyut kontrolü
    size_bytes = os.path.getsize(real_path)
    if size_bytes > MAX_TELEGRAM_FILE_BYTES:
        return (
            f"ERROR: file_too_large ({_human_size(size_bytes)}, "
            f"Telegram limiti {_human_size(MAX_TELEGRAM_FILE_BYTES)})"
        )

    # 4) Gönderim
    success = telegram_bot.send_document(owner_chat_id, real_path)

    if not success:
        return "ERROR: dosya Telegram'a gönderilirken bir sorun oluştu"

    return f"OK: '{os.path.basename(real_path)}' ({_human_size(size_bytes)}) Telegram'a gönderildi"