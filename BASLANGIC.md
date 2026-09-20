# Q-ADAPTIVE — Sıfırdan Canlıya Alma (Koyeb)

Bu belge projeyi 7/24 çalışan ücretsiz bir canlı demoya dönüştürür.
Bilgisayarınıza **hiçbir şey kurulmaz** — Docker imajını Koyeb kendi
sunucusunda derler.

**Toplam süre:** ~30 dakika (yarısı bekleme).

| # | Aşama | Süre |
|---|---|---|
| 1 | Temiz klasörü üret | 1 dk |
| 2 | GitHub reposu oluştur ve gönder | 5 dk |
| 3 | Koyeb hesabı + servis kurulumu | 5 dk |
| 4 | Derlemeyi izle | 10-15 dk (bekleme) |
| 5 | Canlı testler | 5 dk |

---

## Neden Koyeb?

İlk plan Hugging Face Spaces'ti; ancak 2026'da yapılan değişiklikle
**Docker Space'ler PRO plan gerektiriyor** ($9/ay). Ücretsiz kalan tek
seçenek olan Static Space yalnızca dosya sunar, Python backend'i çalıştırmaz.

Koyeb ücretsiz katmanı bu proje için uygun olan tek gerçek alternatif:

| Özellik | Koyeb ücretsiz |
|---|---|
| Süre sınırı | Yok, süresiz |
| Uyku modu | **Yok — 7/24 ayakta** |
| Kredi kartı | Gerekmiyor |
| Kaynak | 512 MB RAM / 0.1 vCPU |
| Docker | Dockerfile'ı GitHub'dan okuyup kendisi derler |

> **Bilinen risk:** 512 MB RAM bu proje için dar.
> `onnxruntime + scikit-learn + scipy + pandas` yaklaşık 350-420 MB tutuyor.
> Sığması bekleniyor ama pay az. Konteyner `OOMKilled` verirse
> `Q-Adaptive-AI/src/model.py` içindeki gereksiz `pandas` / `joblib`
> importları ayıklanarak ~80 MB kazanılabilir; o da yetmezse Google Cloud
> Run'a (1 GB) geçilir. Aynı Dockerfile her ikisinde de çalışır.

---

## AŞAMA 1 — Temiz klasörü üret

```bash
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/Proje"
bash make-space.sh
```

**Neden gerekli?** `Proje/` reposunun git geçmişinde 25 MB'lık dört `.pptx`
dosyası var. Bu betik yalnızca konteynerin ihtiyaç duyduğu dosyalardan
(~5 MB) oluşan temiz bir klasör üretir. Ana GitHub reponuz etkilenmez.

Çıktının sonunda `✅ Space klasörü hazır.` görmelisiniz.
Klasör: `Bloq/q-adaptive-space`

---

## AŞAMA 2 — GitHub reposu

Koyeb kaynak kodu GitHub'dan okur, o yüzden önce oraya göndereceğiz.

### 2.1 — Repoyu oluştur (tarayıcıda)

https://github.com/new

| Alan | Değer |
|---|---|
| Repository name | `q-adaptive-live` |
| Visibility | **Public** |
| Initialize with README | **İşaretlemeyin** (boş kalmalı) |

**Create repository**'ye basın.

### 2.2 — Gönder

```bash
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/q-adaptive-space"
git init
git add -A
git commit -m "Q-ADAPTIVE (AI Guardian) — canlı demo konteyneri"
git branch -M main
git remote add origin git@github.com:yorulmazkagan/q-adaptive-live.git
git push -u origin main
```

> SSH anahtarınız zaten kurulu (mevcut `CryptoTEK` reposu SSH kullanıyor),
> bu yüzden parola sorulmayacak. Sorarsa HTTPS'e geçin:
> `git remote set-url origin https://github.com/yorulmazkagan/q-adaptive-live.git`

---

## AŞAMA 3 — Koyeb servisi

### 3.1 — Hesap

https://www.koyeb.com → **Sign up** → **Continue with GitHub**

GitHub yetkilendirmesinde Koyeb'in repolarınızı okumasına izin verin.
Kredi kartı istenmez.

### 3.2 — Servisi oluştur

**Create Service** → **Web Service**

| Ayar | Değer |
|---|---|
| Source | **GitHub** |
| Repository | `yorulmazkagan/q-adaptive-live` |
| Branch | `main` |
| Builder | **Dockerfile** (Buildpack değil — mutlaka değiştirin) |
| Dockerfile location | `Dockerfile` (kök dizin) |
| Instance type | **Free** |
| Region | **Frankfurt** (Türkiye'ye en yakın) |
| Service name | `q-adaptive` |

### 3.3 — Port ve sağlık kontrolü

**Exposed ports** bölümünde:

| Alan | Değer |
|---|---|
| Port | `7860` |
| Protocol | `HTTP` |
| Path | `/` |

**Health checks** bölümünde (varsayılan TCP yerine):

| Alan | Değer |
|---|---|
| Protocol | `HTTP` |
| Port | `7860` |
| Path | `/api/health` |
| Grace period | `120` saniye |

> Grace period önemli: konteyner ONNX modelini yüklerken birkaç saniye
> sürer, kısa bir süre verilirse Koyeb servisi ölü sanıp yeniden başlatır.

**Deploy**'a basın.

---

## AŞAMA 4 — Derlemeyi izle

Servis sayfasında **Deployments → Build logs**.

Rust derlemesi ilk seferde 10-15 dakika sürer; loglar uzun süre
`Compiling winterfell...` satırlarında ilerler. Normaldir.

Derleme bitince **Runtime logs**'ta şunları görmelisiniz:

```
✅ ONNX InferenceSession yüklendi: q_adaptive_guardian.onnx
✅ Kalibrasyon yüklendi — mean_d=..., std_d=...
✅ ZK prover binary doğrulandı: .../q-adaptive-zk
ZK kuyruk kapasitesi gerekçesi: 20 çekirdek ; 6.8 GB / 0.5 GB-per-proof = 13 -> min = 13 -> clamp[1,64] = 13
✅ Async ZK kanıt kuyruğu oluşturuldu (maxsize=13)
✅ Sunucu isteklere hazır.
```

Servis durumu **Healthy** olduğunda canlı adresiniz üstte görünür:

```
https://q-adaptive-<ORG_ADI>.koyeb.app
```

---

## AŞAMA 5 — Canlı testler

`<ADRES>` yerine Koyeb'in verdiği adresi yazın.

```bash
# 1) Sağlık kontrolü
curl -s https://<ADRES>/api/health | python3 -m json.tool
```

Beklenen: `"status": "healthy"`, `"model_loaded": true`, `"zk_queue_max": 50`

```bash
# 2) Normal kullanıcı — panik modu TETİKLENMEMELİ
curl -s -X POST https://<ADRES>/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"Islem_Sikligi":1.1,"IP_Sapmasi":0.02,"Gas_Sapmasi":0.05}' \
  | python3 -m json.tool
```

Beklenen: `"action": "SAFE"`, `"armor_tier": "ML-DSA-44"`

```bash
# 3) Private key çalınması — STARK prover ÇALIŞMALI
curl -s -X POST https://<ADRES>/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"Islem_Sikligi":2.0,"IP_Sapmasi":0.95,"Gas_Sapmasi":15.5}' \
  | python3 -m json.tool
```

Beklenen: `"action": "TRIGGER_PANIC_MODE"`, `"armor_tier": "ML-DSA-87"`,
**`"prover_time_ms"` sıfırdan büyük**.

> 0.1 vCPU'da STARK üretimi yerel makinenizden çok daha yavaştır
> (18 ms yerine 1-3 saniye). Bu beklenen davranıştır, hata değil.

Son olarak tarayıcıda `https://<ADRES>` → dashboard'un dört sekmesi de
veri göstermeli, Simülasyon Enjektörü'nün üç profili de çalışmalı.

---

## Kod değiştiğinde güncelleme

```bash
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/Proje" && bash make-space.sh
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/q-adaptive-space"
git add -A && git commit -m "güncelleme" && git push
```

Koyeb push'u algılayıp otomatik yeniden derler. `make-space.sh` mevcut
`.git` klasörünü koruduğu için remote ayarları kaybolmaz.

---

## Sunum öncesi kontrol listesi

- [ ] Koyeb servis durumu **Healthy**
- [ ] Canlı adres tarayıcıda açılıyor
- [ ] Simülasyon Enjektörü'nde üç profil de çalışıyor
- [ ] Panik modunda `prover_time_ms > 0`
- [ ] Adresi sunum slaytına ekleyin

---

## Sorun giderme

| Belirti | Sebep / Çözüm |
|---|---|
| Build `Compiling` sırasında kesiliyor | Derleme zaman aşımı — Rust katmanını devre dışı bırakan yedek Dockerfile'a geçeriz |
| Konteyner `OOMKilled` | 512 MB yetmedi — import ayıklama ya da Cloud Run'a geçiş |
| `prover_time_ms: 0` | ZK binary çalışmıyor; Runtime logs'ta `⚠️ ZK prover binary'si bulunamadı` var mı bakın |
| Health check `unhealthy` | Grace period kısa kalmış olabilir, 120 sn'ye çıkarın |
| Dashboard açılıyor ama butonlar çalışmıyor | Tarayıcı konsolunu (F12) açıp hatayı paylaşın |

Takıldığınız yerde ilgili logun **son 30 satırını** olduğu gibi paylaşın.
