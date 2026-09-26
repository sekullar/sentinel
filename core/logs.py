"""
Sentinel - Log yönetimi (core/logs.py)

Amaç: CLI'de SADECE gerçek konuşma (Sen: / Sentinel: cevabın) görünsün.
Plugin yükleme, BG servisleri (mail nöbetçisi, away scheduler), ve ham model
çıktıları/tool sonuçları gibi her şey buraya, sentinel.log dosyasına akar.

Canlı izlemek için AYRI bir terminalde:
    tail -f sentinel.log

Kullanım (herhangi bir dosyada):
    from core.logs import log
    log("bir şeyler oldu")
    log("ciddi bir hata", level="error")
"""
import logging

_logger = logging.getLogger("sentinel")
_logger.setLevel(logging.DEBUG)

if not _logger.handlers:
    _handler = logging.FileHandler("sentinel.log", encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    _logger.addHandler(_handler)


def log(msg: str, level: str = "info") -> None:
    getattr(_logger, level, _logger.info)(msg)