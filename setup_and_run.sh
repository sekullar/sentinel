#!/bin/bash
# Sentinel - Tek komutla kurulum + bağlantı testi + çalıştırma (WSL / Linux)
set -e

echo "== 1/4: Sanal ortam kontrolü =="
if [ ! -f ".venv/bin/activate" ]; then
    echo "  .venv bulunamadı veya bozuk, yeniden oluşturuluyor..."
    rm -rf .venv
    python3 -m venv .venv || {
        echo "  HATA: venv oluşturulamadı. Şunu dene:"
        echo "    sudo apt install --reinstall python3-venv"
        exit 1
    }
fi
source .venv/bin/activate
echo "  Aktif: $(which python)"

echo ""
echo "== 2/4: Bağımlılıklar =="
pip install -q -r requirements.txt
echo "  Kuruldu."

echo ""
echo "== 3/4: Ollama adresi aranıyor =="
WIN_IP=$(ip route show default 2>/dev/null | awk '/default/ {print $3}')

CANDIDATES=("http://localhost:11434" "http://127.0.0.1:11434")
[ -n "$WIN_IP" ] && CANDIDATES+=("http://$WIN_IP:11434")

FOUND=""
for url in "${CANDIDATES[@]}"; do
    echo -n "  Deneniyor: $url ... "
    if curl -s -m 2 "$url/api/tags" > /dev/null 2>&1; then
        echo "BAŞARILI"
        FOUND="$url"
        break
    else
        echo "başarısız"
    fi
done

if [ -z "$FOUND" ]; then
    echo ""
    echo "  Hiçbir adrese bağlanılamadı. Kontrol et:"
    echo "   - Windows'ta Ollama, OLLAMA_HOST=0.0.0.0 ile yeniden başlatıldı mı?"
    echo "     (netstat -ano | findstr 11434  ->  0.0.0.0:11434 görmelisin)"
    echo "   - Windows Defender Güvenlik Duvarı'nda 11434 portu açık mı?"
    echo "     netsh advfirewall firewall add rule name=\"Ollama\" dir=in action=allow protocol=TCP localport=11434"
    exit 1
fi

export OLLAMA_HOST="$FOUND"
echo "  Kullanılacak adres: $OLLAMA_HOST"

echo ""
echo "== 4/4: Sentinel başlatılıyor =="
python main.py