# Fatura OCR Proxy Sunucusu

Bu sunucu, masaüstü programınızın (.exe) Mistral AI'ye **doğrudan** bağlanmasını
engeller. Mistral API anahtarı yalnızca bu sunucuda saklanır.

## 1. Yerelde Test Etme

```bash
cd proxy_backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env
# .env dosyasını açıp gerçek MISTRAL_API_KEY ve CLIENT_TOKENS değerlerini girin

# Rastgele güvenli bir istemci token'ı üretmek için:
python -c "import secrets; print(secrets.token_hex(32))"

uvicorn app:app --host 0.0.0.0 --port 8000 --env-file .env
```

Tarayıcıda `http://localhost:8000/health` açarak çalıştığını doğrulayın.

## 2. Canlıya (Internet'e) Alma

Birkaç seçenek, kolaydan zora:

**A) Railway / Render / Fly.io (önerilen, en kolay)**
- Bu klasörü bir GitHub reposuna atın (`.env` dosyasını **eklemeyin**, `.gitignore`'a koyun)
- Railway/Render'da "New Web Service" oluşturup repoyu bağlayın
- Ortam değişkenlerini (MISTRAL_API_KEY, CLIENT_TOKENS) platformun "Environment
  Variables" ekranından girin (dosya olarak değil, panelden)
- Platform size otomatik bir HTTPS URL verir (örn. `https://sizin-servis.up.railway.app`)

**B) Kendi VPS'iniz (DigitalOcean, Hetzner vb.)**
- Sunucuya uvicorn'u sistemd servisi olarak kurun
- Önüne nginx koyup `certbot` ile ücretsiz HTTPS sertifikası alın
- `.env` dosyasını sunucuda saklayın, asla dışarı göndermeyin

**HTTPS zorunludur** — HTTP kullanırsanız istemci token'ı ağ trafiğinde açık
görünür ve tüm çabanız boşa gider.

## 3. Güvenlik Notları

- Her `.exe` kopyasına/kullanıcıya **farklı** bir `CLIENT_TOKENS` girdisi verin.
  Biri kötüye kullanılırsa sadece o token'ı `.env`'den silip sunucuyu yeniden
  başlatarak erişimini kesebilirsiniz — Mistral anahtarınıza dokunmanıza gerek kalmaz.
- `RATE_LIMIT_PER_MINUTE` değerini gerçek kullanım paternlerinize göre ayarlayın.
- Sunucu loglarını (`logger.info(...)` satırları) düzenli kontrol ederek
  anormal kullanım olup olmadığını izleyin.
- İleride isterseniz Google Drive yükleme işlemini de bu proxy üzerinden
  yönlendirebiliriz (aynı desen: sır sunucuda kalır, istemci sadece istek atar).
