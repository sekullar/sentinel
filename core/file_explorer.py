"""
Sentinel - İzinli Klasörlerde Dosya Gezinme (file_explorer.py)

SENTINEL_ALLOWED_DIRECTORIES ortam değişkeninde (virgülle ayrılmış mutlak
yollar) tanımlı klasörler ve alt klasörleriyle sınırlı; roots/list/find/
read/search işlemlerini tek bir explore(query) girişinden yönlendirir.

Path doğrulama (allowed_dirs / resolve_allowed_path) burada tanımlı ve
core/file_sender.py bunu DOĞRUDAN buradan import ediyor - aynı mantığı iki
yerde ayrı ayrı yazmıyoruz, "izinli" tanımının iki modülde birbirinden
sapması (güvenlik açığı riski) böylece engellenmiş oluyor.
"""
import os
import fnmatch
from datetime import datetime

ALLOWED_DIRS_ENV = "SENTINEL_ALLOWED_DIRECTORIES"

# read/search'ün içeriğine bakacağı, "metin dosyası" saydığımız uzantılar.
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml",
    ".xml", ".ini", ".cfg", ".js", ".ts", ".html", ".css", ".sh",
}

MAX_READ_BYTES = 200 * 1024       # read için tek dosya üst sınırı
MAX_FIND_RESULTS = 200
MAX_SEARCH_RESULTS = 100


# ---------------------------------------------------------------------------
# ORTAK DOĞRULAMA (file_sender.py da bunu import ediyor)
# ---------------------------------------------------------------------------
def allowed_dirs() -> list:
    raw = os.environ.get(ALLOWED_DIRS_ENV, "")
    return [os.path.realpath(p.strip()) for p in raw.split(",") if p.strip()]


def resolve_allowed_path(requested_path: str) -> str:
    """requested_path'i normalize eder, izinli klasörlerden birinin altında
    olduğunu doğrular. Değilse ValueError fırlatır."""
    real_path = os.path.realpath(requested_path)
    roots = allowed_dirs()

    if not roots:
        raise ValueError(f"{ALLOWED_DIRS_ENV} ayarlı değil")

    for root in roots:
        if real_path == root or real_path.startswith(root + os.sep):
            return real_path

    raise ValueError(f"'{requested_path}' izinli klasörlerin dışında")


# ---------------------------------------------------------------------------
# YARDIMCILAR
# ---------------------------------------------------------------------------
def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _format_entry(full_path: str) -> str:
    """list/find'in tek bir satırını üretir: tip, (dosyaysa) boyut+tarih,
    ve HER ZAMAN tam yol - model bir sonraki turda bu yolu doğrudan
    kopyalayabilsin, kendi kendine path birleştirmek zorunda kalmasın."""
    name = os.path.basename(full_path)

    if os.path.isdir(full_path):
        return f"[KLASÖR] {name}  ->  {full_path}"

    try:
        stat = os.stat(full_path)
        size = _human_size(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"[DOSYA]  {name}  |  {size}  |  {mtime}  ->  {full_path}"
    except OSError:
        return f"[DOSYA]  {name}  ->  {full_path}"


# ---------------------------------------------------------------------------
# İŞLEMLER
# ---------------------------------------------------------------------------
def _roots() -> str:
    roots = allowed_dirs()
    if not roots:
        return f"ERROR: {ALLOWED_DIRS_ENV} ayarlı değil"
    return "İzinli klasörler:\n" + "\n".join(f"- {r}" for r in roots)


def _list_dir(path: str) -> str:
    if not path:
        return "ERROR: klasör yolu belirtilmedi"

    try:
        real_path = resolve_allowed_path(path)
    except ValueError as e:
        return f"ERROR: {e}"

    if not os.path.isdir(real_path):
        return f"ERROR: '{path}' bir klasör değil (ya da bulunamadı)"

    try:
        entries = sorted(os.listdir(real_path))
    except OSError as e:
        return f"ERROR: klasör okunamadı ({e})"

    if not entries:
        return f"'{real_path}' boş."

    full_paths = [os.path.join(real_path, e) for e in entries]
    # klasörler önce, sonra dosyalar
    dirs = [p for p in full_paths if os.path.isdir(p)]
    files = [p for p in full_paths if not os.path.isdir(p)]

    lines = [_format_entry(p) for p in dirs] + [_format_entry(p) for p in files]
    return f"'{real_path}' içeriği ({len(lines)} öğe):\n" + "\n".join(lines)


def _find(folder: str, pattern: str) -> str:
    folder = folder.strip()
    fallback_note = ""

    if not folder:
        return "ERROR: klasör yolu belirtilmedi"

    # "-" verilirse (folder bilinmiyorsa) TÜM izinli köklerde ara.
    if folder == "-":
        search_roots = allowed_dirs()
        if not search_roots:
            return f"ERROR: {ALLOWED_DIRS_ENV} ayarlı değil"
    else:
        try:
            search_roots = [resolve_allowed_path(folder)]
            if not os.path.isdir(search_roots[0]):
                raise ValueError(f"'{folder}' bir klasör değil (ya da bulunamadı)")
        except ValueError:
            # Model (özellikle küçük yerel modeller) burada sık sık geçersiz/
            # izin dışı bir yol uyduruyor ("roots", yanlış kullanıcı adı vb.).
            # Hata döndürüp kullanıcıyı takılı bırakmak yerine, "-" ile aynı
            # şekilde davranıp TÜM izinli köklerde ara - modelin niyeti zaten
            # "klasörü bulamıyorum" idi.
            search_roots = allowed_dirs()
            if not search_roots:
                return f"ERROR: {ALLOWED_DIRS_ENV} ayarlı değil"
            fallback_note = f"(Not: verdiğin '{folder}' geçerli/izinli bir klasör değildi, bunun yerine TÜM izinli klasörlerde arandı)\n"

    pattern = pattern.strip() or "*"
    has_wildcard = any(ch in pattern for ch in "*?[")

    if has_wildcard:
        # Kullanıcı zaten bir desen verdi (*.pdf, rapor?.txt vb.) - olduğu gibi kullan.
        matcher = lambda name: fnmatch.fnmatch(name.lower(), pattern.lower())
    else:
        # Uzantı verilmedi: adda (uzantısız gövdesinde de) ALT DİZE olarak ara -
        # "rapor" hem "rapor.pdf" hem "rapor_2024.docx" ile eşleşir.
        term = pattern.lower()
        matcher = lambda name: term in os.path.splitext(name)[0].lower() or term in name.lower()

    matches = []

    for root in search_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            # Hem KLASÖR hem DOSYA adlarını eşleştir - "Kodlar" bir klasörse de bulunmalı.
            for name in list(dirnames) + filenames:
                if matcher(name):
                    matches.append(os.path.join(dirpath, name))
                    if len(matches) >= MAX_FIND_RESULTS:
                        break
            if len(matches) >= MAX_FIND_RESULTS:
                break
        if len(matches) >= MAX_FIND_RESULTS:
            break

    if not matches:
        where = "tüm izinli klasörlerde" if (folder == "-" or fallback_note) else f"'{search_roots[0]}' altında"
        return f"{fallback_note}empty_result: '{pattern}' ile {where} bulunamadı"

    lines = [_format_entry(p) for p in sorted(set(matches))]
    suffix = " (limit doldu, daha fazla sonuç olabilir)" if len(matches) >= MAX_FIND_RESULTS else ""
    return f"{fallback_note}{len(lines)} sonuç bulundu{suffix}:\n" + "\n".join(lines)


def _read(path: str) -> str:
    if not path:
        return "ERROR: dosya yolu belirtilmedi"

    try:
        real_path = resolve_allowed_path(path)
    except ValueError as e:
        return f"ERROR: {e}"

    if not os.path.isfile(real_path):
        return f"ERROR: '{path}' bir dosya değil (ya da bulunamadı)"

    ext = os.path.splitext(real_path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return f"ERROR: desteklenmeyen dosya türü '{ext}' (bu araç sadece düz metin dosyalarını okuyabilir)"

    size = os.path.getsize(real_path)
    try:
        with open(real_path, "r", encoding="utf-8", errors="strict") as f:
            content = f.read(MAX_READ_BYTES)
    except UnicodeDecodeError:
        return f"ERROR: '{path}' metin olarak okunamadı (ikili/desteklenmeyen kodlama)"
    except OSError as e:
        return f"ERROR: dosya okunamadı ({e})"

    truncated_note = ""
    if size > MAX_READ_BYTES:
        truncated_note = f"\n\n[NOT: dosya {_human_size(size)}, sadece ilk {_human_size(MAX_READ_BYTES)} gösteriliyor]"

    return f"'{real_path}' içeriği:\n{content}{truncated_note}"


def _search_text(folder: str, term: str) -> str:
    if not folder:
        return "ERROR: klasör yolu belirtilmedi"
    if not term.strip():
        return "ERROR: aranacak ifade belirtilmedi"

    try:
        real_folder = resolve_allowed_path(folder)
    except ValueError as e:
        return f"ERROR: {e}"

    if not os.path.isdir(real_folder):
        return f"ERROR: '{folder}' bir klasör değil (ya da bulunamadı)"

    term_lower = term.strip().lower()
    results = []

    for dirpath, dirnames, filenames in os.walk(real_folder):
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in TEXT_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, name)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if term_lower in line.lower():
                            results.append(f"{full_path}:{lineno}: {line.strip()[:200]}")
                            if len(results) >= MAX_SEARCH_RESULTS:
                                break
            except OSError:
                continue
            if len(results) >= MAX_SEARCH_RESULTS:
                break
        if len(results) >= MAX_SEARCH_RESULTS:
            break

    if not results:
        return f"empty_result: '{term}' ifadesi '{real_folder}' altındaki metin dosyalarında bulunamadı"

    suffix = " (limit doldu, daha fazla sonuç olabilir)" if len(results) >= MAX_SEARCH_RESULTS else ""
    return f"{len(results)} eşleşme bulundu{suffix}:\n" + "\n".join(results)


# ---------------------------------------------------------------------------
# GİRİŞ NOKTASI - main.py PLUGIN_SPECS'teki file_explorer bu fonksiyonu çağırır
# ---------------------------------------------------------------------------
def explore(query: str) -> str:
    """
    query formatı main.py'deki prompt ile birebir eşleşir:
      roots|-
      list|/mnt/c/.../Documents
      find|/mnt/c/.../Documents|*.pdf
      read|/mnt/c/.../Documents/notlar.txt
      search|/mnt/c/.../Documents|aranan ifade
    """
    if not query or "|" not in query:
        return "ERROR: geçersiz format, 'işlem|argüman' bekleniyor"

    action, _, rest = query.partition("|")
    action = action.strip().lower()
    args = rest.split("|")

    if action == "roots":
        return _roots()
    elif action == "list":
        return _list_dir(args[0].strip())
    elif action == "find":
        folder = args[0].strip()
        pattern = args[1].strip() if len(args) > 1 else "*"
        return _find(folder, pattern)
    elif action == "read":
        return _read(args[0].strip())
    elif action == "search":
        folder = args[0].strip()
        term = args[1].strip() if len(args) > 1 else ""
        return _search_text(folder, term)
    else:
        return f"ERROR: bilinmeyen işlem '{action}'"