# Sahne Akışı — 3 Dakikalık Jüri Sunumu

**Takım:** CryptoTEK · TAKIM ID 909630
**Arayüz:** `stitch_q_adaptive_ai_guardian_dashboards/index.html`

Bu koreografi arayüze **gömülüdür**. `Sunum Modu` düğmesine bas, `→` ve `←`
tuşlarıyla adımlar arasında gez, `Enter` ile koşuyu tetikle, `Esc` ile çık.
Her adımda hangi jüri itirazını cevapladığın ekranda yazılı durur — sahnede
menü aramak yok.

---

## Hazırlık

```bash
cd Q-Adaptive-ZK && cargo build --release && cd ..
cd Q-Adaptive-AI && python3 run_server.py
```

Tarayıcı: `http://127.0.0.1:8000`

Üst şeritte **● canlı** yazmalı. **● bağlantı yok** görüyorsan sunucu
ayakta değildir — arayüz bu durumda hiçbir sayı göstermez, örnek veriye
düşmez. Sahneye çıkmadan önce yeşil olduğunu doğrula.

---

## Adımlar

### 1 · Standart kullanıcı (0:00–0:25)

**Yap:** `Standart` → `Koştur`

**Göster:** risk ~11 < τ 75 · zırh ML-DSA-44 · **kanıt ÜRETİLMEDİ** ·
yürütme izinde yalnızca **ONNX çıkarım** aşaması var.

> **İtiraz:** *"Her işlemde ağır post-kuantum kripto mu koşturuyorsunuz?
> Maliyeti nasıl karşılıyorsunuz?"*
>
> **Cevap:** Hayır. Risk eşiğin altındayken kriptografik katman **hiç
> çalışmıyor** — şeritte tek bir aşama var. Maliyeti riske göre yönetiyoruz.

---

### 2 · Drainer saldırısı (0:25–1:05)

**Yap:** `Drainer` → `Koştur`

**Göster:** risk 100 ≥ τ 75 · zırh **ML-DSA-87** · kafes ızgarası
**4×4'ten 8×7'ye büyüdü** (16 → 56 hücre) · imza çubuğu 2.420 → 4.627 B'ye
uzadı · şeritte **12 aşama** yandı.

> **İtiraz:** *"AI'ın kararı kriptografiyi gerçekten etkiliyor mu, yoksa
> sadece bir etiket mi değişiyor?"*
>
> **Cevap:** Ekranda büyüdü. Kafes 16 elemandan 56'ya, imza 2.420 bayttan
> 4.627 bayta çıktı. Bu sayılar `fips204` kütüphanesinden **ölçüldü**, elle
> yazılmadı. Denetim öncesinde bu bir JSON metninden ibaretti.

**Şeride işaret et:** 12 aşamanın her birinin süresi ayrı ölçülüyor.
ML-DSA keygen ~0,3 ms, STARK prover ~5 ms. "Arkada ne oluyor" sorusunun
cevabı bu şerittir.

---

### 3 · Kurcalama testi (1:05–1:25)

**Yap:** Yeni koşu yok — zırh kartındaki rozetleri göster.

**Göster:** `imza doğrulandı` ✓ · `kurcalama reddedildi` ✓ · şeritte
**kurcalama testi** aşaması ve süresi.

> **İtiraz:** *"İmza doğrulaması gerçek mi, yoksa her zaman `true` mu
> dönüyor?"*
>
> **Cevap:** Her koşuda mesajın son biti çevrilip aynı imza tekrar
> doğrulanıyor. Reddedilmezse **koşu durur** — "imza doğrulandı" diyemeyiz.
> Bu bir birim testi değil, üretim akışının parçası; şeritte süresi
> görünüyor.

---

### 4 · Rotasyon (1:25–1:50)

**Yap:** Gas sapmasını biraz oynat → `Koştur`

**Göster:** Aynı zırh kademesi, ama **ρ' değişti** ve kafes ızgarasının
**tüm hücreleri renk değiştirdi**.

> **İtiraz:** *"Rotasyon gerçek mi? Gizli anahtar sabit mi kalıyor?"*
>
> **Cevap:** ρ' FIPS 204'ün ξ tohumu olarak kullanılıyor, yani **tüm anahtar
> çifti** yenileniyor — sadece matris değil. Tek bit değişince 56 hücrenin
> 56'sı değişiyor; bunu `hashing::tests::cig_etkisi_tek_bit` her koşuda
> doğruluyor.

---

### 5 · Determinizm (1:50–2:20)

**Yap:** Aynı senaryoyu **iki kez** koştur, ρ' alanını karşılaştır.

**Göster:** Üst şeritte `determinizm: evet` · aynı girdi → aynı ρ' → aynı
imza.

> **İtiraz:** *"Bu sadece rastgele sayı üretimi değil mi? Nasıl
> doğrulayalım?"*
>
> **Cevap:** Tam deterministik. Aynı girdi her makinede birebir aynı ρ',
> anahtar ve imzayı veriyor. Jüri koşuyu kendi makinesinde tekrarlayabilir.
> Denetim öncesinde `process::id()` karıştırılıyordu ve kanıt yeniden
> üretilemezdi.

---

### 6 · Sınırlar (2:20–3:00)

**Yap:** Alttaki amber paneli göster.

**Göster:** **İddia Etmediklerimiz** — yedi madde, kalıcı olarak ekranda.

> **İtiraz:** *"Neyi iddia etmiyorsunuz?"* (ya da Q&A'de gelecek herhangi
> bir sınır sorusu)
>
> **Cevap:** Zaten ekranda. STARK ML-DSA'yı devre içinde ispatlamıyor,
> kanıt zincirde doğrulanmıyor, veri sentetik, bağımsız denetim yok,
> mainnet konuşlandırması yok. Ve: **50 ECDSA imzası 3.250 bayt — bir STARK
> kanıtından küçük.** ECDSA calldata'da bizi yeniyor; takas post-kuantum
> güvenliği.

---

## Q&A için hazır cevaplar

| Soru | Nerede göstereceksin |
|---|---|
| "Calldata oranını nasıl hesapladınız?" | Alt şerit → *Calldata formülü* — formül ve girdileri ekranda, yeniden hesaplanabilir |
| "Zincire ne gidiyor?" | Alt şerit → *AIR sınır koşulları* |
| "Ham veriyi görebilir miyiz?" | Alt şerit → *Ham yanıt (JSON)* |
| "STARK güvenlik seviyesi?" | Kanıt kartı → 80 bit. README'yi okuyan bir test bu sayıyı kodla hizalı tutuyor |
| "Sunucu çökerse ne olur?" | Sunucuyu durdur, sayfayı yenile → kırmızı bant, tüm alanlar `—`. **Hiçbir örnek sayı gösterilmez** |

---

## Sahne riski notu

Arayüz **hiçbir dış kaynak çekmez** — Tailwind, Chart.js, Google Fonts
yok. Projeksiyon makinesinde internet olmasa da tam olarak çalışır.
`test_api_contract.py::test_cdn_bagimliligi_yok` bunu her CI koşusunda
doğrular.

Arayüzdeki her sayı bir API alanından gelir; gelmiyorsa `—` gösterilir.
Gösterilen 38 alanın hepsinin API şemasında gerçekten var olduğu
`test_api_contract.py::test_her_bagli_alan_semada_var` ile sınanır.
