# -*- coding: utf-8 -*-
"""
FATURA OCR PROXY SUNUCUSU
==========================
Bu sunucu, masaustu programinizin (.exe) Mistral AI OCR servisine
DOGRUDAN erisimini engeller. Mistral API anahtari SADECE bu sunucuda
saklanir, hicbir zaman istemciye (.exe) gonderilmez.

Akis:
  1) .exe programi, fatura goruntusunu bu sunucuya yollar (kendi
     istemci token'i ile kimlik dogrulayarak)
  2) Bu sunucu, kendi Mistral API anahtarini kullanarak Mistral'a istek atar
  3) Sonuc metnini .exe programina geri doner

Calistirmadan once:
  pip install fastapi uvicorn httpx python-multipart --break-system-packages

  .env dosyasi olusturun (asagidaki .env.example'a bakin) ve icine
  gercek MISTRAL_API_KEY ve CLIENT_TOKENS degerlerini yazin.

Calistirma (test/gelistirme):
  uvicorn app:app --host 0.0.0.0 --port 8000

Uretimde (canli sunucuda):
  - HTTPS zorunlu (reverse proxy: nginx + certbot, veya Render/Railway/Fly.io
    gibi platformlarin otomatik HTTPS'i)
  - CLIENT_TOKENS'i gercek, tahmin edilemez, uzun rastgele degerlerle doldurun
  - Rate limiting aktif edin (asagida basit bir surumu var)
"""

import os
import time
import base64
import logging
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fatura-ocr-proxy")

# ════════════════════════════════════════════════════════
#  AYARLAR (ortam degiskenlerinden okunur - koda YAZILMAZ)
# ════════════════════════════════════════════════════════

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
OCR_TIMEOUT = 20.0

# Gecerli istemci token'lari: "token": "aciklama/sahibi" seklinde.
# Ortam degiskeninden virgulle ayrilmis "token1:isim1,token2:isim2" formatinda okunur.
# Ornek: CLIENT_TOKENS="a1b2c3...:ofis-pc-1,d4e5f6...:muhasebe-pc-2"
def _client_tokens_yukle():
    ham = os.environ.get("CLIENT_TOKENS", "")
    sozluk = {}
    for parca in ham.split(","):
        parca = parca.strip()
        if not parca:
            continue
        if ":" in parca:
            tok, isim = parca.split(":", 1)
        else:
            tok, isim = parca, "bilinmiyor"
        sozluk[tok.strip()] = isim.strip()
    return sozluk

CLIENT_TOKENS = _client_tokens_yukle()

# Basit rate limiting: her token icin dakikada max istek sayisi
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))
_istek_kayitlari = defaultdict(deque)  # token -> zaman damgalari deque'si

if not MISTRAL_API_KEY:
    logger.warning("UYARI: MISTRAL_API_KEY ortam degiskeni bos! Sunucu OCR isteklerini karsilayamaz.")
if not CLIENT_TOKENS:
    logger.warning("UYARI: CLIENT_TOKENS ortam degiskeni bos! Hicbir istemci kimlik dogrulayamaz.")

app = FastAPI(title="Fatura OCR Proxy", version="1.0")


# ════════════════════════════════════════════════════════
#  KIMLIK DOGRULAMA + RATE LIMIT
# ════════════════════════════════════════════════════════

def _token_dogrula(x_client_token: str | None):
    if not x_client_token or x_client_token not in CLIENT_TOKENS:
        raise HTTPException(status_code=401, detail="Gecersiz veya eksik istemci token'i")
    return CLIENT_TOKENS[x_client_token]


def _rate_limit_kontrol(token: str):
    simdi = time.time()
    kayit = _istek_kayitlari[token]
    # 60 saniyeden eski kayitlari at
    while kayit and simdi - kayit[0] > 60:
        kayit.popleft()
    if len(kayit) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Cok fazla istek - lutfen biraz bekleyin")
    kayit.append(simdi)


# ════════════════════════════════════════════════════════
#  ENDPOINT: /ocr  (fatura goruntusunu oku)
# ════════════════════════════════════════════════════════

@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    x_client_token: str | None = Header(default=None),
):
    isim = _token_dogrula(x_client_token)
    _rate_limit_kontrol(x_client_token)

    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="Sunucu yapilandirmasi eksik (API anahtari yok)")

    goruntu_bytes = await file.read()
    if len(goruntu_bytes) > 8 * 1024 * 1024:   # 8 MB sinirlama
        raise HTTPException(status_code=413, detail="Goruntu cok buyuk (max 8MB)")

    img_b64 = base64.b64encode(goruntu_bytes).decode("utf-8")

    istek_govde = {
        "model": "pixtral-12b-2409",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": f"data:image/png;base64,{img_b64}"},
                {"type": "text", "text": "Bu fatura goruntusundeki tum metni aynen cikar. Hicbir sey ekleme, sadece gorseldeki metni yaz."},
            ],
        }],
        "max_tokens": 2000,
    }

    try:
        async with httpx.AsyncClient(timeout=OCR_TIMEOUT) as client:
            r = await client.post(
                MISTRAL_URL,
                json=istek_govde,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                },
            )
            r.raise_for_status()
            veri = r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Mistral hata: {e.response.status_code} - {e.response.text[:300]}")
        raise HTTPException(status_code=502, detail="OCR servisinde hata olustu")
    except Exception as e:
        logger.error(f"Mistral istek hatasi: {e}")
        raise HTTPException(status_code=502, detail="OCR servisine ulasilamadi")

    metin = veri.get("choices", [{}])[0].get("message", {}).get("content", "")
    logger.info(f"OCR istegi basarili - istemci: {isim}")

    return JSONResponse({"metin": metin})


# ════════════════════════════════════════════════════════
#  SAGLIK KONTROLU
# ════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"durum": "calisiyor", "mistral_yapilandirildi": bool(MISTRAL_API_KEY)}
