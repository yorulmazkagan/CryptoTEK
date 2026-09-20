# Q-ADAPTIVE — Canlı Demo Dağıtım Rehberi

Bu belge, projeyi tek konteyner halinde 7/24 çalışan bir canlı demoya dönüştürme
adımlarını içerir. Hedef platform **Hugging Face Spaces (Docker SDK)**; aynı
`Dockerfile` değişiklik gerektirmeden Fly.io, Render, Google Cloud Run ve
herhangi bir Docker uyumlu ortamda da çalışır.

---

## 1. Neden Docker konteyneri, neden serverless değil

Q-ADAPTIVE serverless bir platformda (Vercel, Netlify Functions) doğru çalışmaz.
Dört yapısal sebep:

| Sorun | Sonuç |
|---|---|
| `SlidingWindowThresholdCalibrator` süreç belleğinde 50 gözlemlik pencere tutar | Serverless'ta her istek yeni instance'a düşebilir → pencere hiç dolmaz, τ(t) kalıcı olarak soğuk başlangıç değeri 75.0'da kalır |
| Bundle boyut limiti (~250 MB) | `onnxruntime` + `scipy` + `scikit-learn` + `numpy` bu sınırı zorlar |
| ZK prover ayrı bir süreç olarak spawn edilir (`asyncio.create_subprocess_exec`) | Serverless fonksiyon içinden derlenmiş ikili çalıştırmak desteklenmez |
| Yürütme süresi limiti (Hobby: 10 sn) | STARK kanıt üretimi bu pencereye sığmayabilir |

Konteyner yaklaşımı bunların dördünü birden çözer: kalıcı süreç, boyut sınırı yok,
alt süreç serbest, süre sınırı yok.

---

## 2. Konteyner mimarisi

```
┌──────────────────────── Aşama 1: zk-builder (rust:slim) ────────────────────────┐
│  cargo build --release  →  target/release/q-adaptive-zk                          │
│  (LTO + codegen-units=1 + panic=abort; ilk derleme ~5-8 dk, sonrası önbellekli)  │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │ COPY --from=zk-builder
┌─────────────────────────────────────▼───────────── Aşama 2: runtime (python:3.11-slim) ┐
│  /app/Q-Adaptive-AI/                      ← FastAPI + ONNX + model artefaktları        │
│  /app/Q-Adaptive-ZK/target/release/...    ← derlenmiş prover binary'si                 │
│  /app/Q-Adaptive-ZK/proof_payload.json    ← yedek payload (prover henüz koşmadıysa)    │
│  /app/stitch_..._dashboards/index.html    ← Dashboard SPA                              │
│                                                                                         │
│  USER user (UID 1000)   ·   WORKDIR /app/Q-Adaptive-AI   ·   CMD python run_server.py  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Kritik detaylar:**

- **Dizin düzeni korunmalıdır.** `src/api.py`, ZK ve dashboard köklerini kendi
  konumuna göre (`parent.parent`) çözer. `/app` altındaki yapı repo yapısıyla birebir aynıdır.
- **UID 1000.** HF Spaces konteynerleri root olmayan kullanıcıyla çalışır.
  Ayrıca prover, çalışma dizinine `proof_payload.json` yazar — bu yüzden
  `/app` dizini `user`'a `chown` edilir.
- **Model çalışma zamanında eğitilmez.** `.onnx`, `.joblib` ve
  `calibration_metadata.json` repoda mevcuttur ve imaja gömülür; konteyner
  saniyeler içinde ayağa kalkar.
- **Tek worker.** τ(t) kalibratörü süreç belleğinde durum tuttuğu için birden
  fazla worker pencereyi bölerdi.

---

## 3. Yerel doğrulama (dağıtımdan önce zorunlu)

```bash
cd Proje

# İmajı derle (ilk seferde Rust derlemesi nedeniyle ~8-12 dk sürer)
docker build -t q-adaptive .

# Çalıştır
docker run --rm -p 7860:7860 q-adaptive
```

Kontrol listesi:

```bash
# 1) Sağlık kontrolü — model yüklendi mi, kuyruk kuruldu mu
curl -s http://localhost:7860/api/health | python3 -m json.tool
# Beklenen: status=healthy, model_loaded=true, zk_queue_max=50

# 2) Normal işlem — panik modu tetiklenmemeli
curl -s -X POST http://localhost:7860/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"Islem_Sikligi":1.1,"IP_Sapmasi":0.02,"Gas_Sapmasi":0.05}' \
  | python3 -m json.tool
# Beklenen: action=SAFE, armor_tier=ML-DSA-44

# 3) Private key çalınması senaryosu — STARK prover çalışmalı
curl -s -X POST http://localhost:7860/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"Islem_Sikligi":2.0,"IP_Sapmasi":0.95,"Gas_Sapmasi":15.5}' \
  | python3 -m json.tool
# Beklenen: action=TRIGGER_PANIC_MODE, armor_tier=ML-DSA-87,
#           prover_time_ms > 0  ← 0 ise binary çalışmıyor, önbelleğe düşülmüş demektir
```

Ardından tarayıcıda `http://localhost:7860` → dashboard'un dört sekmesi de
veri göstermeli; Simülasyon Enjektörü'nden üç profil de tetiklenmeli.

---

## 4. Hugging Face Spaces'e dağıtım

### 4.1 Space oluştur

1. https://huggingface.co/new-space
2. **Owner:** kendi hesabınız · **Space name:** `q-adaptive-ai-guardian`
3. **License:** Apache 2.0
4. **SDK:** `Docker` → `Blank`
5. **Hardware:** `CPU basic · 2 vCPU · 16 GB` (ücretsiz)
6. **Visibility:** `Public`

> Space'in yapılandırması `README.md` başındaki YAML frontmatter'dan okunur
> (`sdk: docker`, `app_port: 7860`). Bu blok repoya eklenmiştir; silmeyin.

### 4.2 Kodu gönder

> **ÖNEMLİ — bu repo doğrudan push edilemez.** `Proje/` reponun git geçmişinde
> 25 MB'lık `.pptx` dosyaları var (`docs/assets/Q_ADAPTIVE_Master_Deck_140.pptx`
> ve 3 tanesi daha). Hugging Face, Git LFS dışında 10 MB üstü dosya kabul
> etmez; `git push` reddedilir. Dosyaları silmek bile yetmez — geçmişte
> kaldıkları sürece push engellenir.
>
> Çözüm: `make-space.sh` betiği, yalnızca konteynerin ihtiyaç duyduğu
> dosyalardan oluşan temiz bir klasör üretir (≈5 MB) ve oraya sıfırdan git
> geçmişi kurulur. GitHub reposu hiç etkilenmez.

```bash
# 1) Temiz Space klasörünü üret (Bloq/q-adaptive-space oluşur)
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/Proje"
bash make-space.sh

# 2) Space klasöründe git geçmişi başlat
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/q-adaptive-space"
git init
git add -A
git commit -m "Q-ADAPTIVE (AI Guardian) — canlı demo konteyneri"
git branch -M main

# 3) HF remote'unu ekle ve gönder
git remote add origin https://huggingface.co/spaces/<KULLANICI_ADI>/q-adaptive-ai-guardian
git push -u origin main --force
```

> **Kimlik doğrulama:** HF, parola yerine erişim token'ı ister.
> Settings → Access Tokens → `write` yetkili token oluşturun; kullanıcı adı
> olarak HF kullanıcı adınızı, parola olarak token'ı yapıştırın.

Kod değiştiğinde güncelleme:

```bash
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/Proje" && bash make-space.sh
cd "$HOME/Masaüstü/Antigravity Demolar/Bloq/q-adaptive-space"
git add -A && git commit -m "güncelleme" && git push
```

`make-space.sh` yeniden çalıştırıldığında mevcut `.git` klasörünü korur,
dolayısıyla remote ayarları ve push geçmişi kaybolmaz.

### 4.3 Derlemeyi izle

Space sayfasında **Logs → Build**. Rust derlemesi ilk seferde ~8-12 dakika sürer.
Ardından **Logs → Container**'da şu satırlar görünmelidir:

```
✅ ONNX InferenceSession yüklendi: q_adaptive_guardian.onnx
✅ Kalibrasyon yüklendi — mean_d=..., std_d=...
✅ ZK prover binary doğrulandı: .../q-adaptive-zk
ZK kuyruk kapasitesi gerekçesi: 20 çekirdek ; 6.8 GB / 0.5 GB-per-proof = 13 → min = 13 → clamp[1,64] = 13
✅ Async ZK kanıt kuyruğu oluşturuldu (maxsize=13)
   ^ bu sayı ÖRNEKTİR — boş belleğe bağlı. Aynı makinede bir sonraki
     çalıştırmada 7 de çıkabilir; gerekçe satırı hangi hesaptan geldiğini söyler.
✅ Sunucu isteklere hazır.
```

Canlı adres: `https://<KULLANICI_ADI>-q-adaptive-ai-guardian.hf.space`

---

## 5. Dağıtım sonrası sertleştirme (önerilir)

Endpoint herkese açık olacağı için:

1. **CORS'u daralt.** `src/api.py` içindeki `allow_origins=["*"]` yerine
   Space alan adınızı yazın. Tek origin'den servis edildiği için `["*"]`'a gerek yoktur.
2. **Basit hız sınırı.** ZK kuyruğu yalnızca kanıt üretimini sınırlar;
   `/api/predict`'in ONNX yolu sınırsızdır. IP başına dakikada N istek sınırı
   (`slowapi`) eklemek demoyu kötüye kullanıma karşı korur.

   Kuyruk kapasitesi sabit değildir — `_resolve_queue_capacity()` bunu Space'in
   çekirdek sayısı ve boş belleğinden türetir. Ücretsiz CPU Space'te bu genelde
   2 civarıdır, yerel bir geliştirme makinesinde 13–20 olabilir. Değeri
   `Q_ADAPTIVE_ZK_QUEUE_MAX` ile sabitleyebilirsiniz; gerçekleşen değer ve
   gerekçesi `/api/health` yanıtında yayınlanır.
3. **Uyku modu.** Ücretsiz CPU Space'ler uzun süreli hareketsizlikte uyuyabilir.
   Space Settings → *Sleep time* ayarını kapatın; alternatif olarak dış bir
   uptime monitörü (ör. UptimeRobot) `/api/health` adresini 5 dakikada bir
   çağırarak konteyneri uyanık tutar. **Jüri sunumundan önce mutlaka
   adresi bir kez açın.**

---

## 6. Alternatif platformlar (aynı Dockerfile)

| Platform | Komut | Not |
|---|---|---|
| Fly.io | `fly launch --dockerfile Dockerfile` | Kendi alan adınızı bağlayabilirsiniz. `fly.toml` içinde `auto_stop_machines = false` yapın, aksi halde uyur. ~$5/ay. |
| Render | Dashboard → New Web Service → Docker | Ücretsiz katman 15 dk hareketsizlikte uyur (~50 sn soğuk açılış). Always-on için Starter ($7/ay). |
| Cloud Run | `gcloud run deploy --source .` | `--min-instances=1` verilmezse soğuk başlangıç olur; verilirse ücretlidir. Bellek en az 1 GiB ayarlayın. |

---

## 7. Faz 2 — Akıllı sözleşmeleri testnet'e alma (opsiyonel)

Dashboard'un 4. sekmesi (On-Chain State Monitor) şu an simülasyon verisiyle
çalışır. Gerçek zincir verisine bağlamak için:

1. `Q-Adaptive-Contracts` altına Hardhat veya Foundry kurulumu ekle
2. `QAdaptiveAccount` + `QAdaptivePaymaster`'ı Sepolia'ya deploy et
   (ERC-4337 EntryPoint v0.7 adresi ile)
3. Paymaster'a test ETH yatır
4. Dashboard'un 4. sekmesini bir RPC sağlayıcısı (Alchemy/Infura) üzerinden
   gerçek `epoch`, `commitment root` ve `UserOperationEvent` verisine bağla

Bu, jüri üzerindeki etkiyi belirgin şekilde artırır ancak ayrı bir iş kalemidir;
canlı demo bu olmadan da eksiksiz çalışır.
