"""
Sentinel - Faz 4: Dayanıklı eklenti mimarisi + Telegram + otomatik host bulma
             + Log ayrıştırması (core/logs.py)

Bu sürümde eklentiler artık statik import değil, TEK TEK ve GÜVENLİ şekilde
yükleniyor: bir eklentinin modülü/bağımlılığı eksikse (örneğin spotipy kurulu
değilse), SADECE o eklenti devre dışı kalıyor - motor çökmüyor, search_memory
gibi çekirdek özellikler çalışmaya devam ediyor.

Sistem promptu da artık elle yazılmıyor: her eklenti kendi prompt parçasını ve
örneğini PLUGIN_SPECS içinde taşıyor, sadece BAŞARIYLA yüklenen eklentilerin
parçaları nihai sisteme prompta ekleniyor. Yani model asla yüklü olmayan bir
aracı "var" sanıp çağırmaya çalışmıyor.

LOG AYRIŞTIRMASI: CLI artık sadece gerçek konuşmayı gösteriyor (Sen: / Sentinel: X).
Plugin yükleme, BG servisleri (mail nöbetçisi, away scheduler), ve her turdaki
ham model çıktısı + tool sonucu core/logs.py üzerinden sentinel.log dosyasına
yazılıyor. Canlı izlemek için ayrı bir terminalde: tail -f sentinel.log

İSTİSNA: Away mode'da model "SESSİZ" DIŞINDA bir şey söylerse (yani kendi kararıyla
kullanıcıya bir şey bildirmeye değer bulduysa - örn. pil kritik), bu hem CLI'ye
hem Telegram'a hem de log'a gider. Sadece "SESSİZ" olan cevaplar SADECE log'a gider.
"""

import subprocess
import threading
import importlib

import requests
import ollama

from core.parser import parse_model_output
from core.memory import MemoryStore
from core import telegram_bot
from core.logs import log


MODEL_NAME = "qwen3-coder:30b"  # kendi çektiğin model adıyla değiştir
MAX_TOOL_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# EKLENTİ KAYITLARI
# Her eklenti: hangi modülü import edeceği, model bir şey istediğinde hangi
# fonksiyonu çağıracağı, sistem promptuna ekleyeceği kendi bölümü ve örneği.
# Yeni bir eklenti eklemek için sadece bu listeye bir sözlük daha eklemen yeterli.
# ---------------------------------------------------------------------------

PLUGIN_SPECS = [
    {
        "name": "web_search",
        "module": "core.web_search",
        "tool_name": "web_search",
        "call": lambda mod, query: mod.search(query),
        "prompt": """## Web Araması
Güncel bir bilgiye (hava durumu, haberler, bir web sitesindeki bilgi, senin
eğitim verinde olmayan bir şey) ihtiyacın olduğunda şu formatta yaz:
<CALL_TOOL: web_search sorgu_metni |>
Bu araç sınırlı bir aylık kotaya sahip, bu yüzden TUTUMLU kullan: zaten bildiğin,
genel/zamana bağlı olmayan bir şey için (tanım, tarihi bilgi, genel kavram) ARAMA,
direkt kendi bilgini kullan. Sadece gerçekten güncel/değişken bir bilgi gerektiğinde
kullan.""",
        "example_title": "Web Araması",
        "example_body": """Kullanıcı: "Bugün Antalya'da hava nasıl?"
Senin çıktın: "Bakıyorum. <CALL_TOOL: web_search Antalya hava durumu bugün |>" """,
    },
    {
        "name": "file_explorer",
        "module": "core.file_explorer",
        "tool_name": "file_explorer",
        "call": lambda mod, query: mod.explore(query),
        "prompt": """## İzinli Klasörlerde Dosya Bulma ve Okuma
Bu araç yalnızca kullanıcı tarafından SENTINEL_ALLOWED_DIRECTORIES ayarıyla
izin verilmiş klasörlerde ve alt klasörlerinde çalışır. Ayar WSL Linux yolları
kullanır; Windows klasörleri örneğin /mnt/c/Users/kullanici/Documents biçimindedir.
Araç kodu her yolu ayrıca doğrular; prompttaki kuralları aşmaya çalışma.

Kullanıcı dosya veya klasör bulmayı, klasör içeriğini listelemeyi ya da desteklenen
bir metin dosyasını okumayı istediğinde bu aracı kullan. Dosya oluşturma, değiştirme,
silme, çalıştırma veya dosya sistemi dışında arama yeteneği YOKTUR.

İstek biçimleri:
- İzinli klasörleri öğren: <CALL_TOOL: file_explorer roots|- |>
- Klasör listele: <CALL_TOOL: file_explorer list|/mnt/c/Users/kullanici/Documents |>
Dosya/klasör adı ara: <CALL_TOOL: file_explorer find|KLASÖR|*.pdf |>
      KLASÖR hangi izinli klasör olduğunu bilmiyorsan "-" yaz, TÜM izinli
      klasörlerde arar (izin dışı bir yol UYDURMA, mutlaka ya bir izinli
      klasör ya da "-" olmalı). find hem DOSYA hem KLASÖR adlarıyla eşleşir
- Metin dosyası oku: <CALL_TOOL: file_explorer read|DOSYA_YOLU |>
- Metin içeriğinde ara: <CALL_TOOL: file_explorer search|KLASÖR|aranan ifade |>

Önce kullanıcının kastettiği izinli klasörü ve dosya adını belirle.
Kullanıcı bir dosya/klasörün TAM OLARAK NEREDE olduğunu bilmiyorsa,
  önce roots'a bakmana gerek yok - doğrudan find|-|aranan_isim çağırarak
tüm izinli klasörlerde tek seferde arayabilirsin. Yol belirtilmemiş
ve birden fazla izinli klasör varsa önce roots işlemiyle izinli klasörleri öğren;
hangisinin kastedildiği belirsizse kullanıcıya sor, kendin tahmin etme. Mutlak
yol yerine izinli bir klasöre göreli yol verilebilir. Dosya adını veya yolunu
uydurma. Bir dosyayı okurken yalnızca istenen içeriği getir; gereksiz büyük dosyaları
okuma. Araç PDF ve Office dosyalarının içeriğini okuyamaz; dosya aramasıyla adlarını
bulabilir. Araç bir ERROR döndürürse sınırları aşmaya çalışma; sonucu açıkça bildir.""",
        "example_title": "İzinli Klasörde Dosya Bulma ve Okuma",
        "example_body": """Kullanıcı: "Belgelerimdeki notlar.txt dosyasını oku."
Senin çıktın: "İzinli klasörlerimi kontrol edip dosyayı okuyorum. <CALL_TOOL: file_explorer roots|- |>"
Araç sonucu: "/mnt/c/Users/kullanici/Documents"
Senin çıktın: "Dosyayı açıyorum. <CALL_TOOL: file_explorer read|/mnt/c/Users/kullanici/Documents/notlar.txt |>"
Kullanıcı: "Masaüstümde sunum var mı?"
Senin çıktın: "İzinli klasörlerde sunum dosyalarını arıyorum. <CALL_TOOL: file_explorer find|/mnt/c/Users/kullanici/Desktop|*.pptx |>" """,
    },
    {
        "name": "spotify",
        "module": "core.spotify_plugin",
        "tool_name": "spotify_play",
        "call": lambda mod, query: mod.play(query),
        "prompt": """## Spotify
Kullanıcı bir şarkı açmak/çalmak istediğinde ("spotifydan X çal", "X'i aç") şu formatta yaz:
<CALL_TOOL: spotify_play şarkı adı sanatçı |>
Sorguya sadece şarkı adını yaz, biliyorsan sanatçıyı da ekle (emin değilsen ekleme).
"çal", "spotifydan" gibi kelimeleri sorguya KOYMA. Bu araç kota harcamaz, çekinmeden kullan.""",
        "example_title": "Spotify",
        "example_body": """Kullanıcı: "Spotifydan let it happen çal"
Senin çıktın: "Açıyorum. <CALL_TOOL: spotify_play let it happen tame impala |>" """,
    },
    {
        "name": "steam",
        "module": "core.steam_control",
        "tool_name": "launch_game",
        "call": lambda mod, query: mod.launch_game(query),
        "prompt": """## Oyun Başlatma
Kullanıcı bir Steam oyununu açmanı istediğinde şu formatta yaz:
<CALL_TOOL: launch_game oyun_adı |>
Oyun adını kullanıcının söylediği gibi, kısaltmadan/değiştirmeden geçir - eşleştirme
otomatik yapılıyor.""",
        "example_title": "Oyun Başlatma",
        "example_body": """Kullanıcı: "CS2'yi açar mısın?"
Senin çıktın: "Açıyorum. <CALL_TOOL: launch_game CS2 |>" """,
    },
    {
        "name": "calendar_list",
        "module": "core.calendar_plugin",
        "tool_name": "calendar_list",
        "call": lambda mod, query: mod.list_upcoming(query),
        "prompt": """## Takvim - Listeleme
Kullanıcı önümüzdeki etkinliklerini/toplantılarını sorduğunda ("yarın toplantım var
mı", "bu hafta ne var") şu formatta yaz:
<CALL_TOOL: calendar_list - |>
(sorgu içeriği önemli değil, her zaman önümüzdeki 7 günü döner)""",
        "example_title": "Takvim - Listeleme",
        "example_body": """Kullanıcı: "Yarın toplantım var mı?"
Senin çıktın: "Kontrol ediyorum. <CALL_TOOL: calendar_list - |>" """,
    },
    {
        "name": "calendar_create",
        "module": "core.calendar_plugin",
        "tool_name": "calendar_create",
        "call": lambda mod, query: mod.create_event(query),
        "prompt": """## Takvim - Etkinlik Ekleme
Kullanıcı bir etkinlik/hatırlatma/toplantı eklemeni istediğinde şu KESİN formatta yaz
(başka hiçbir şekilde değil):
<CALL_TOOL: calendar_create başlık|YYYY-MM-DDTHH:MM|YYYY-MM-DDTHH:MM |>
Tarih/saati bugünün tarihine göre SEN hesapla (kullanıcı "yarın 15:00" derse tam
tarihe çevir). Bitiş saatini kullanıcı belirtmezse başlangıçtan 1 saat sonrasını yaz.""",
        "example_title": "Takvim - Etkinlik Ekleme",
        "example_body": """Kullanıcı: "Yarın saat 15:00'e diş hekimi randevusu ekle" (bugün 2026-09-25)
Senin çıktın: "Ekliyorum. <CALL_TOOL: calendar_create Diş Hekimi Randevusu|2026-09-26T15:00|2026-09-26T16:00 |>" """,
    },
    {
        "name": "calendar_delete",
        "module": "core.calendar_plugin",
        "tool_name": "calendar_delete",
        "call": lambda mod, query: mod.delete_event(query),
        "prompt": """## Takvim - Etkinlik Silme

Kullanıcı mevcut bir etkinliği silmek/kaldırmak istediğinde şu formatta yaz:

<CALL_TOOL: calendar_delete etkinlik_bilgisi |>

Etkinliği mümkün olduğunca açık tanımla. Kullanıcı tarih veya saat belirttiyse
bunları da ekle. Belirsiz birden fazla etkinlik varsa rastgele seçim yapma,
önce netleştir.""",
        "example_title": "Takvim - Etkinlik Silme",
        "example_body": """Kullanıcı: "Yarınki toplantıyı sil"

Senin çıktın: "Siliyorum. <CALL_TOOL: calendar_delete yarınki toplantı |>" """,
    },
    {
        "name": "calendar_update",
        "module": "core.calendar_plugin",
        "tool_name": "calendar_update",
        "call": lambda mod, query: mod.update_event(query),
        "prompt": """## Takvim - Etkinlik Güncelleme

Kullanıcı mevcut bir etkinliğin bilgilerini değiştirmek istediğinde şu formatta yaz:

<CALL_TOOL: calendar_update mevcut_etkinlik|yeni_bilgiler |>

Mevcut etkinliği ilk bölümde, değiştirilmesini istediği bilgileri ikinci bölümde
belirt. Kullanıcı tarih/saat verirse YYYY-MM-DDTHH:MM formatına çevir.
Belirtilmeyen bilgileri değiştirme. Belirsiz birden fazla etkinlik varsa önce netleştir.""",
        "example_title": "Takvim - Etkinlik Güncelleme",
        "example_body": """Kullanıcı: "Yarınki toplantıyı saat 15:00'e al"

Senin çıktın: "Güncelliyorum. <CALL_TOOL: calendar_update yarınki toplantı|2026-09-26T15:00 |>" """,
    },
    {
        "name": "mail_check",
        "module": "core.mail_plugin",
        "tool_name": "check_mail",
        "call": lambda mod, query: mod.check_mail(query),
        "prompt": """## E-Posta Kontrolü
Kullanıcı e-postalarını kontrol etmeni istediğinde şu formatta yaz:
<CALL_TOOL: check_mail HESAP_TÜRÜ |>
HESAP_TÜRÜ sadece 'gmail' veya 'outlook' olabilir.
ÖNEMLİ: Sistemde iki farklı hesap bağlıdır. Kullanıcı açıkça hangi hesaba bakacağını söylemediyse KESİNLİKLE tool çağırma! Normal bir cevap yazarak ona "Gmail'e mi yoksa okul hesabına (Outlook) mı bakayım?" diye sor.""",
        "example_title": "E-Posta Kontrol",
        "example_body": """Kullanıcı: "Yeni mail var mı?"
Senin çıktın: "Hangi hesabına bakmamı istersin? Gmail mi yoksa Outlook (okul) mu?"
Kullanıcı: "Okul hesabıma bak"
Senin çıktın: "Hemen kontrol ediyorum. <CALL_TOOL: check_mail outlook |>" """,
    },
    {
        "name": "mail_send",
        "module": "core.mail_plugin",
        "tool_name": "send_mail",
        "call": lambda mod, query: mod.send_mail(query),
        "prompt": """## E-Posta Gönderme
Kullanıcı bir e-posta göndermeni istediğinde şu formatta yaz:
<CALL_TOOL: send_mail HESAP_TÜRÜ|KİME_ADRES|KONU|İÇERİK |>
ÖNEMLİ: Kullanıcı maili hangi hesabından (gmail/outlook) göndereceğini belirtmediyse tool'u ASLA çağırma, önce ona sor! Ayrıca kime, konu veya içerik eksikse yine tool çağırma, eksik bilgileri doğal bir şekilde kullanıcıdan iste.""",
        "example_title": "E-Posta Gönderme",
        "example_body": """Kullanıcı: "Ahmet hocaya ödevimi at"
Senin çıktın: "Bunu okul (Outlook) hesabından mı yoksa kişisel (Gmail) adresinden mi göndereyim? Ayrıca e-posta adresini, konuyu ve mesajın içeriğini de belirtir misin?" """,
    },
    {
        "name": "away_toggle",
        "module": "core.away_state",
        "tool_name": "toggle_away_mode",
        "call": lambda mod, query: mod.toggle(query),
        "prompt": """## Away Mode - Açma/Kapama
Kullanıcı gitmek üzere olduğunu belirttiğinde ("gidiyorum", "çıkıyorum",
"bilgisayar açık kalsın" gibi doğal ifadelerle - kesin bir komut beklemeden
niyeti sen fark et) şu formatta yaz:
<CALL_TOOL: toggle_away_mode aç |>
Kullanıcı geri döndüğünde ("geldim", "away modunu kapat" gibi) şu formatta yaz:
<CALL_TOOL: toggle_away_mode kapat |>""",
        "example_title": "Away Mode Açma",
        "example_body": """Kullanıcı: "Ben gidiyorum, bilgisayar açık kalsın."
Senin çıktın: "Tamam, göz kulak olurum. <CALL_TOOL: toggle_away_mode aç |>" """,
    },
    {
        "name": "system_monitor",
        "module": "core.system_monitor",
        "tool_name": "battery_status",
        "call": lambda mod, query: mod.get_status(query),
        "prompt": """## Pil Durumu
Pil yüzdesini öğrenmen gerektiğinde (kullanıcı sorduğunda; away mode
SYSTEM_EVENT'inde zaten geliyorsa tekrar sormana gerek yok) şu formatta yaz:
<CALL_TOOL: battery_status - |>""",
        "example_title": "Pil Durumu",
        "example_body": """Kullanıcı: "Pilim yüzde kaç?"
Senin çıktın: "Bakıyorum. <CALL_TOOL: battery_status - |>" """,
    },
    {
        "name": "power_lock",
        "module": "core.power_control",
        "tool_name": "lock_computer",
        "call": lambda mod, query: mod.lock_computer(query),
        "prompt": """## Bilgisayarı Kilitleme
Kullanıcı bilgisayarı kilitlemeni istediğinde şu formatta yaz:
<CALL_TOOL: lock_computer - |>
Bu geri döndürülebilir bir işlem, onay gerektirmez.""",
        "example_title": "Kilitleme",
        "example_body": """Kullanıcı: "Bilgisayarı kilitle."
Senin çıktın: "Kilitliyorum. <CALL_TOOL: lock_computer - |>" """,
    },
    {
        "name": "power_shutdown",
        "module": "core.power_control",
        "tool_name": "request_shutdown",
        "call": lambda mod, query: mod.request_shutdown(query),
        "prompt": """## Bilgisayarı Kapatma (KRİTİK - ONAY ŞART)
Bu GERİ DÖNDÜRÜLEMEZ bir eylem. Away mode'da bile olsan, kullanıcı AÇIKÇA
"evet kapat" demeden bu tool'u ASLA çağırma - önce sor, cevabı bekle, sonraki
turda karar ver. Onay aldıktan sonra şu formatta yaz:
<CALL_TOOL: request_shutdown 120 |>
(sayı: kaç saniye sonra kapanacağı - kullanıcının fikrini değiştirebilmesi
için bir güvenlik payı, çok düşük tutma)""",
        "example_title": "Kapatma (Sadece Onay Sonrası)",
        "example_body": """Kullanıcı: "Evet, kapatabilirsin."
Senin çıktın: "Kapatıyorum, 2 dakika içinde kapanacak. <CALL_TOOL: request_shutdown 120 |>" """,
    },
    {
        "name": "power_cancel_shutdown",
        "module": "core.power_control",
        "tool_name": "cancel_shutdown",
        "call": lambda mod, query: mod.cancel_shutdown(query),
        "prompt": """## Kapatmayı İptal Etme
Zamanlanmış bir kapatmayı iptal etmen gerektiğinde şu formatta yaz:
<CALL_TOOL: cancel_shutdown - |>""",
        "example_title": "Kapatmayı İptal Etme",
        "example_body": """Kullanıcı: "Dur dur, kapatma, vazgeçtim!"
Senin çıktın: "Tamam, iptal ediyorum. <CALL_TOOL: cancel_shutdown - |>" """,
    },
    {
        "name": "file_explorer",
        "module": "core.file_explorer",
        "tool_name": "file_explorer",
        "call": lambda mod, query: mod.explore(query),
        "prompt": """## İzinli Klasörlerde Dosya Bulma ve Okuma
Bu araç yalnızca kullanıcı tarafından SENTINEL_ALLOWED_DIRECTORIES ayarıyla
izin verilmiş klasörlerde ve alt klasörlerinde çalışır. Ayar WSL Linux yolları
kullanır; Windows klasörleri örneğin /mnt/c/Users/kullanici/Documents biçimindedir.
Araç kodu her yolu ayrıca doğrular; prompttaki kuralları aşmaya çalışma.
 
Kullanıcı dosya veya klasör bulmayı, klasör içeriğini listelemeyi ya da desteklenen
bir metin dosyasını okumayı istediğinde bu aracı kullan. Dosya oluşturma, değiştirme,
silme, çalıştırma veya dosya sistemi dışında arama yeteneği YOKTUR.
 
İstek biçimleri:
- İzinli klasörleri öğren: <CALL_TOOL: file_explorer roots|- |>
- Klasör listele: <CALL_TOOL: file_explorer list|/mnt/c/Users/kullanici/Documents |>
- Dosya adı/deseni ara: <CALL_TOOL: file_explorer find|KLASÖR|*.pdf |>
- Metin dosyası oku: <CALL_TOOL: file_explorer read|DOSYA_YOLU |>
- Metin içeriğinde ara: <CALL_TOOL: file_explorer search|KLASÖR|aranan ifade |>
 
Önce kullanıcının kastettiği izinli klasörü ve dosya adını belirle. Yol belirtilmemiş
ve birden fazla izinli klasör varsa önce roots işlemiyle izinli klasörleri öğren;
hangisinin kastedildiği belirsizse kullanıcıya sor, kendin tahmin etme. Mutlak
yol yerine izinli bir klasöre göreli yol verilebilir. Dosya adını veya yolunu
uydurma. Bir dosyayı okurken yalnızca istenen içeriği getir; gereksiz büyük dosyaları
okuma. Araç PDF ve Office dosyalarının içeriğini okuyamaz; dosya aramasıyla adlarını
bulabilir. Araç bir ERROR döndürürse sınırları aşmaya çalışma; sonucu açıkça bildir.
 
find işleminde kullanıcı uzantı belirtmeden ("rapor dosyasını bul" gibi) bir isim
verirse, deseni OLDUĞU GİBİ (uzantısız) geç - araç bunu dosya adında alt dize olarak
arar ve uzantıdan bağımsız eşleştirir (örn. "rapor" -> rapor.pdf, rapor_2024.docx
gibi hepsini bulur). Kullanıcı özellikle bir uzantı/joker karakter belirtirse
(*.pdf, rapor?.txt gibi) onu olduğu gibi geç.
 
Her list/find sonucunda her satırda dosyanın/klasörün TAM YOLU da veriliyor
("-> /mnt/c/..." kısmı). Bir klasörün içine bakman gerektiğinde bu tam yolu
KENDİN BİRLEŞTİRMEYE ÇALIŞMA, doğrudan o satırdaki tam yolu bir sonraki
list/find/read çağrısında birebir kullan.""",
        "example_title": "İzinli Klasörde Dosya Bulma ve Okuma",
        "example_body": """Kullanıcı: "Belgelerimdeki notlar.txt dosyasını oku."
Senin çıktın: "İzinli klasörlerimi kontrol edip dosyayı okuyorum. <CALL_TOOL: file_explorer roots|- |>"
Araç sonucu: "/mnt/c/Users/kullanici/Documents"
Senin çıktın: "Dosyayı açıyorum. <CALL_TOOL: file_explorer read|/mnt/c/Users/kullanici/Documents/notlar.txt |>"
Kullanıcı: "Masaüstümde sunum var mı?"
Senin çıktın: "İzinli klasörlerde sunum dosyalarını arıyorum. <CALL_TOOL: file_explorer find|/mnt/c/Users/kullanici/Desktop|*.pptx |>"
Kullanıcı: "Belgelerimde rapor diye bir dosya arıyorum, uzantısını bilmiyorum."
Senin çıktın: "Arıyorum. <CALL_TOOL: file_explorer find|/mnt/c/Users/kullanici/Documents|rapor |>" """,
    },
 
# --- ADIM 2 ---
# Aynı listede, yukarıdaki file_explorer girişinin HEMEN ARDINDAN (ayrı bir
# yeni sözlük olarak) şunu ekle:
 
    {
        "name": "file_send",
        "module": "core.file_sender",
        "tool_name": "file_send",
        "call": lambda mod, query: mod.send_file(query),
        "prompt": """## İzinli Klasörlerden Telegram'a Dosya Gönderme
Kullanıcı izinli bir klasördeki bir dosyayı Telegram'a atmanı/göndermeni istediğinde
şu formatta yaz (bu istek CLI'den gelse bile geçerlidir, dosya Telegram'a gider):
<CALL_TOOL: file_send DOSYA_YOLU |>
DOSYA_YOLU izinli bir klasörün altında olmalı - emin değilsen önce file_explorer'ın
roots/list/find işlemleriyle tam yolu bul, sonra bu aracı çağır. Araç kendi içinde
hem izinli klasör kontrolü hem Telegram bağlantı kontrolü yapar; Telegram bağlı
değilse (owner henüz bota yazmadıysa) ERROR: telegram_not_connected döner - bu
durumda kullanıcıya Telegram'dan bota bir mesaj atması gerektiğini söyle.""",
        "example_title": "Dosya Gönderme (Telegram)",
        "example_body": """Kullanıcı: "Belgelerimdeki rapor.pdf dosyasını telegrama at"
Senin çıktın: "Gönderiyorum. <CALL_TOOL: file_send /mnt/c/Users/kullanici/Documents/rapor.pdf |>" """,
    },
]


def load_plugins() -> list:
    """
    Her eklentiyi tek tek, izole şekilde yüklemeye çalışır. Biri başarısız
    olursa sadece onu atlar, diğerlerini ve çekirdeği hiç etkilemez.
    Yükleme durumu artık CLI'ye değil log'a yazılıyor.
    """
    active = []

    for spec in PLUGIN_SPECS:
        try:
            module = importlib.import_module(spec["module"])
            active.append({**spec, "module_obj": module})
            log(f"[PLUGIN] {spec['name']} aktif")

        except Exception as e:
            log(
                f"[PLUGIN] {spec['name']} devre dışı ({type(e).__name__}: {e})",
                level="warning",
            )

    return active


ACTIVE_PLUGINS = load_plugins()


def _make_handler(module_obj, call_fn):
    """Closure'daki 'late binding' hatasına düşmemek için ayrı bir factory."""
    return lambda query, memory: call_fn(module_obj, query)


TOOL_HANDLERS = {
    "search_memory": lambda query, memory: memory.search(query),
}


for _p in ACTIVE_PLUGINS:
    TOOL_HANDLERS[_p["tool_name"]] = _make_handler(
        _p["module_obj"],
        _p["call"],
    )


def build_system_prompt() -> str:
    """Sistem promptunu, SADECE başarıyla yüklenmiş eklentilerin parçalarından derler."""

    parts = [
        """Sen Sentinel'sin, kullanıcının yerel makinesinde çalışan bir yapay zeka çekirdeğisin."""
    ]

    parts.append(
        """## Hafızaya Bakma
Eski konuşmaları hatırlaman gerektiğini düşündüğünde (kullanıcı "hatırlıyor musun",
"daha önce demiştim" gibi bir şey sorduğunda, ya da bağlamı netleştirmek için geçmişe
bakman gerektiğinde), normal cevap yazmak yerine SADECE şu formatta yaz:
<CALL_TOOL: search_memory sorgu_metni |>"""
    )

    # build_system_prompt() içinde, "Hafızaya Bakma" parts.append'inden hemen
# SONRA, "for p in ACTIVE_PLUGINS: parts.append(p["prompt"])" satırından
# ÖNCEYE eklenecek yeni blok:

    parts.append(
        """## Sistem Bilgisi Konusunda EZBERDEN KONUŞMA YASAĞI
İzinli klasörlerin hangileri olduğu, kaç tane olduğu, yolları ne olduğu gibi
SİSTEME ÖZEL bilgileri SANA ÖNCEDEN VERİLMEDİ - bunlar SADECE ilgili tool
çağrısıyla (file_explorer roots|- |>) öğrenilebilir. Bu tür bir soru geldiğinde:
- ASLA ezberden, tahminden ya da "tipik" bir dizin yapısından (/home/user/...,
  Projects, Music, Downloads gibi örnek/şablon yollardan) CEVAP UYDURMA.
- Bu bilgiyi az önceki bir TOOL_RESULT'ta görmediysen, MUTLAKA önce ilgili
  tool'u çağır, sonucu bekle, SADECE o sonuçtaki gerçek verilerle cevap ver.
- Emin olmadığın HERHANGİ bir sistem bilgisi için aynı kural geçerli: önce
  tool çağır, sonra cevapla - asla "muhtemelen şöyledir" diye tahmin yazma."""
    )

    for p in ACTIVE_PLUGINS:
        parts.append(p["prompt"])

    parts.append(
        """Yukarıdakilerden herhangi birine ihtiyacın yoksa hiç kullanma, direkt cevap ver.
Tag'den sonra başka bir şey yazma. Tek seferde SADECE BİR tool çağırabilirsin."""
    )

    parts.append(
        """## Hafızaya Kaydetme
Kullanıcı sana kalıcı, ileride işine yarayacak bir bilgi verdiğinde (kim olduğu,
nerede yaşadığı, bir tercihi, açıkça "bunu hatırla" dediği bir şey) bunu KENDİ
CÜMLELERİNLE kısa bir özet halinde şu formatta işaretle:
<SAVE_MEMORY: özet_bilgi |>
Bunu normal cevabınla AYNI çıktıda, cevabının sonuna ekleyerek kullanabilirsin.
Geçici, önemsiz şeyler için (selamlaşma, "tamam" gibi kısa onaylar) bunu kullanma."""
    )

    parts.append(
        """## Ön Anons (Narration)
Bir tool çağırmadan önce, ne yaptığını kısaca haber veren bir cümle kur - kullanıcı
seni sessizce beklemesin. Bu cümleyi HER tool çağrısında yap, atlamamaya çalış."""
    )

    examples = [
        (
            "Hafıza",
            """Kullanıcı: "Ben X Üniversitesi'nde okuyorum, Y Yurdu'nda kalıyorum."
Senin çıktın: "Not aldım, iyi çalışmalar! <SAVE_MEMORY: Kullanıcı X Üniversitesi
öğrencisi, Y Yurdu'nda kalıyor |>""",
        ),
        (
            "Hafızaya Bakma",
            """Kullanıcı: "Sana daha önce nerede okuduğumu söylemiş miydim?"
Senin çıktın: "Kontrol ediyorum... <CALL_TOOL: search_memory kullanıcının okuduğu üniversite |>""",
        ),
    ]

    for p in ACTIVE_PLUGINS:
        examples.append(
            (p["example_title"], p["example_body"])
        )

    example_text = "\n\n".join(
        f"### Örnek {i + 1} - {title}\n{body}"
        for i, (title, body) in enumerate(examples)
    )

    parts.append(example_text)

    parts.append(
        """## Hata Yönetimi
Bir TOOL_RESULT içinde "ERROR:" ile başlayan bir mesaj görürsen, önce hata türünü ayırt:

- Mesaj bir BAĞLANTI sorunundan bahsediyorsa ("bağlantı hatası", "Connection refused",
"timeout" gibi kelimeler geçiyorsa), bu genelde ilgili servisin bilgisayarda kurulu
olmadığı ya da çalışmadığı anlamına gelir. Bu durumda YENİDEN DENEME — tekrar denemek
sonucu değiştirmez. Bunun yerine kullanıcıya kısa ve net bir şekilde açıkla, teknik
detaya boğma.
- Mesaj "empty_result" diyorsa, bu servis çalışıyor ama sorgunla alakalı bir şey
bulamadı demektir. Bu durumda sorgunu farklı kelimelerle YENİDEN dene.
- Mesaj "spotify_auth", "spotify_no_device" veya "spotify_premium" diyorsa YENİDEN
DENEME - mesajdaki talimatı kullanıcıya kısa ve net söyle.

### Örnek - Bağlantı Hatası
TOOL_RESULT: [ERROR: web_search bağlantı hatası (Connection refused)]
Senin çıktın: "Web araması şu anda çalışmıyor gibi görünüyor, muhtemelen ilgili servis
kurulu değil ya da başlatılmamış. Bu konuda sana şu an yardımcı olamıyorum." """
    )

    parts.append(
        """## Away Mode - Arka Plan Olaylarını Yorumlama
Periyodik olarak sana "SYSTEM_EVENT (away_mode, elapsed: Ndk): ..." formatında bir
mesaj gelecek - bu kullanıcı yazmadı, arka plan servisi otomatik üretti. Bunu
değerlendirirken:

- Süre arttıkça (özellikle pil azaldıkça) dikkatini artır - sessizlik geçerli bir varsayılan
  davranıştır, her event'e bir tepki vermek ZORUNDA değilsin.
- Süre azalmasa bile şarj azsa eylem yapmayı düşün. Ortalama %40 civarında eylem yapmaya başlayabilirsin.
- Söyleyecek/yapacak bir şeyin YOKSA, tam olarak şu tek kelimeyi yaz, başka HİÇBİR
  ŞEY ekleme: SESSİZ
- Geri döndürülebilir/zararsız aksiyonlar (bilgisayarı kilitleme gibi) için onay
  gerekmez, kendi kararını ver.
- GERİ DÖNDÜRÜLEMEZ aksiyonlar (kapatma) için ASLA kendi başına karar verme - sadece
  SOR, kullanıcının cevabını bekle, cevap gelene kadar hiçbir tool çağırma.
- Emin olamadığın bir durumda varsayma, sadece durumu bildir ve sor.

### Örnek - Sessizlik Doğru Davranış
SYSTEM_EVENT (away_mode, elapsed: 8dk): Pil: %91
Senin çıktın: SESSİZ

### Örnek - Pil Azaldı, Sadece Sorarak (Aksiyon YOK)
SYSTEM_EVENT (away_mode, elapsed: 95dk): Pil: %14
Senin çıktın: "Pil %14'e düştü ve 95 dakikadır yoksun, bilgisayarı kapatayım mı?"
(Bu turda HİÇBİR tool çağırma - sadece sor. Kullanıcı "evet" derse BİR SONRAKİ
turda request_shutdown'ı çağırabilirsin, bu turda değil.)"""
    )

    return "\n\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()


def _get_wsl_gateway_ip():
    """WSL içindeyken Windows host'un gerçek IP'sini route tablosundan okur."""

    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
        )

        for line in result.stdout.splitlines():
            parts = line.split()

            if "default" in parts:
                return parts[parts.index("via") + 1]

    except Exception:
        pass

    return None


def find_ollama_host() -> str:
    """
    Olası Ollama adreslerini sırayla dener: localhost, 127.0.0.1, ve (WSL
    ise) Windows host'un gerçek IP'si. İlk çalışanı döner.
    """

    candidates = [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]

    wsl_ip = _get_wsl_gateway_ip()

    if wsl_ip:
        candidates.append(f"http://{wsl_ip}:11434")

    for url in candidates:
        try:
            r = requests.get(
                f"{url}/api/tags",
                timeout=2,
            )

            if r.ok:
                return url

        except requests.exceptions.RequestException:
            continue

    raise RuntimeError(
        "Ollama'ya hiçbir adresten bağlanılamadı. Kontrol et:\n"
        "  - Windows'ta Ollama, OLLAMA_HOST=0.0.0.0 ile yeniden başlatıldı mı?\n"
        "  - Windows Defender Güvenlik Duvarı'nda 11434 portu açık mı?\n"
        "  - Ollama gerçekten çalışıyor mu (görev çubuğunu kontrol et)?"
    )


def execute_tool(tool_name: str, query: str, memory: MemoryStore) -> str:
    handler = TOOL_HANDLERS.get(tool_name)

    if handler is None:
        return f"ERROR: bilinmeyen ya da yüklenmemiş eklenti '{tool_name}'"

    result = handler(query, memory)

    if isinstance(result, list):
        return "\n".join(result) if result else "(hiçbir şey bulunamadı)"

    return result


def run_turn(
    history: list,
    memory: MemoryStore,
    client: ollama.Client,
    reply_fn,
) -> str:
    """Model nihai bir cevaba ulaşana kadar (gerekirse tool çağırarak) döner.

    Her turun ham model çıktısı ve (varsa) tool sonucu, debug amacıyla
    CLI'ye değil sadece log dosyasına yazılır.
    """

    attempts = 0

    while True:
        response = client.chat(
            model=MODEL_NAME,
            messages=history,
            options={"num_ctx": 8192},

        )

        raw = response["message"]["content"]
        log(f"[MODEL_RAW] {raw}")

        parsed = parse_model_output(raw)

        if parsed.memory_to_save:
            memory.add(
                parsed.memory_to_save,
                role="fact",
            )

        if parsed.is_final:
            reply_fn(parsed.narration)
            return parsed.narration

        attempts += 1

        if attempts > MAX_TOOL_ATTEMPTS:
            log(
                f"[TOOL] '{parsed.tool_name}' {MAX_TOOL_ATTEMPTS} denemede "
                f"sonuçlanmadı, modele doğrudan cevap vermesi söyleniyor.",
                level="warning",
            )

            history.append(
                {
                    "role": "assistant",
                    "content": raw,
                }
            )

            history.append(
                {
                    "role": "user",
                    "content": "SYSTEM_NOTE: Çok denedin, artık doğrudan cevap ver.",
                }
            )

            attempts = 0
            continue

        if parsed.narration:
            reply_fn(parsed.narration)

        tool_result_text = execute_tool(
            parsed.tool_name,
            parsed.query,
            memory,
        )

        log(
            f"[TOOL:{parsed.tool_name}] query={parsed.query!r} -> {tool_result_text}"
        )

        history.append(
            {
                "role": "assistant",
                "content": raw,
            }
        )

        history.append(
            {
                "role": "user",
                "content": f"TOOL_RESULT: [{tool_result_text}]",
            }
        )


def process_message(
    user_input: str,
    reply_fn,
    history: list,
    memory: MemoryStore,
    client: ollama.Client,
    lock: threading.Lock,
):
    with lock:
        history.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        final_answer = run_turn(
            history,
            memory,
            client,
            reply_fn,
        )

        history.append(
            {
                "role": "assistant",
                "content": final_answer,
            }
        )


def main():
    log("Ollama aranıyor...")

    try:
        ollama_host = find_ollama_host()

    except RuntimeError as e:
        # Bu kritik bir başlangıç hatası, program hiç çalışamayacak - CLI'de görünmeli.
        print(f"\nHATA:\n{e}")
        return

    log(f"Ollama bulundu: {ollama_host}")

    client = ollama.Client(host=ollama_host)

    memory = MemoryStore(ollama_client=client)

    history = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    lock = threading.Lock()

    # ---------------------------------------------------------------
    # ARKA PLAN SERVİSLERİ (mail nöbetçisi, away mode scheduler vb.) -
    # Telegram'dan BAĞIMSIZ, main.py açılır açılmaz başlar. Cevabı kime
    # göndereceğini (chat_id) HER seferinde dinamik olarak sorar - henüz
    # kimse Telegram'a yazmadıysa (owner kayıtlı değilse) Telegram'a
    # göndermez.
    #
    # LOG/CLI AYRIMI: Model "SESSİZ" dediyse (kendi kararıyla söyleyecek bir
    # şeyi yok demektir) SADECE log'a yazılır, CLI'de hiç görünmez. Model
    # SESSİZ DIŞINDA bir şey söylediyse (yani kendi kararıyla önemli/kritik
    # bir şey bildirmeye değer bulduysa) bu hem log'a hem CLI'ye hem de
    # (owner kayıtlıysa) Telegram'a gider.
    # ---------------------------------------------------------------
    def ask_ai_fn(text: str):
        owner_chat_id = telegram_bot.get_owner_chat_id()

        def broadcast_reply_fn(t: str):
            if t.strip().upper() == "SESSİZ":
                log("[AWAY] Model 'SESSİZ' dedi, hiçbir yere gönderilmiyor.")
                return

            log(f"[AWAY] {t}")
            print(f"Sentinel: {t}\n")

            if owner_chat_id is not None:
                telegram_bot.send_message(owner_chat_id, t)

        process_message(text, broadcast_reply_fn, history, memory, client, lock)

    try:
        from core.background_tasks import start_all_services
        bg_thread = threading.Thread(
            target=start_all_services, args=(ask_ai_fn,), daemon=True
        )
        bg_thread.start()
        log("[STARTUP] arka plan servisleri (mail nöbetçisi) başlatıldı")
    except Exception as e:
        log(f"[STARTUP] arka plan servisleri devre dışı ({e})", level="warning")

    try:
        from core.away_scheduler import start as start_away_scheduler
        start_away_scheduler(ask_ai_fn)
        log("[STARTUP] away mode scheduler başlatıldı")
    except Exception as e:
        log(f"[STARTUP] away mode scheduler devre dışı ({e})", level="warning")

    def telegram_on_message(text: str, chat_id: int):
        # ---------------------------------------------------------
        # TYPING GÖSTERGESİ
        # ---------------------------------------------------------

        stop_typing = threading.Event()

        def typing_loop():
            while not stop_typing.is_set():
                telegram_bot.send_typing(chat_id)
                stop_typing.wait(4)

        typing_thread = threading.Thread(
            target=typing_loop,
            daemon=True,
        )

        typing_thread.start()

        # ---------------------------------------------------------
        # MESAJI İŞLE
        # ---------------------------------------------------------

        reply_fn = lambda t: telegram_bot.send_message(
            chat_id,
            t,
        )

        try:
            process_message(
                text,
                reply_fn,
                history,
                memory,
                client,
                lock,
            )

        finally:
            stop_typing.set()

    # -------------------------------------------------------------
    # TELEGRAM POLLING
    # -------------------------------------------------------------

    try:
        telegram_thread = threading.Thread(
            target=telegram_bot.poll_updates,
            args=(telegram_on_message,),
            daemon=True,
        )

        telegram_thread.start()
        log("[STARTUP] telegram polling başlatıldı")

    except Exception as e:
        log(f"[STARTUP] telegram devre dışı ({e})", level="warning")

    # -------------------------------------------------------------
    # CLI - buradan aşağısı DOKUNULMADI, davranış aynen korunuyor.
    # -------------------------------------------------------------

    print(f"Sentinel [Faz 4] - model: {MODEL_NAME}")
    print("Canlı loglar için ayrı bir terminalde: tail -f sentinel.log")
    print("Çıkmak için 'exit' yaz.\n")

    while True:
        user_input = input("Sen: ").strip()

        if user_input.lower() in ("exit", "quit"):
            break

        if not user_input:
            continue

        cli_reply_fn = lambda t: print(
            f"Sentinel: {t}\n"
        )

        process_message(
            user_input,
            cli_reply_fn,
            history,
            memory,
            client,
            lock,
        )


if __name__ == "__main__":
    main()