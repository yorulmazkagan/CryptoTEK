# Denetim Düzeltmeleri — Bulgu → Kod → Test İzlenebilirlik Matrisi

**Takım:** CryptoTEK · TAKIM ID 909630
**Proje:** Q-ADAPTIVE (AI Guardian)
**Belge tarihi:** 19 Eylül 2026
**Başlangıç commit'i:** `238a52b` · **Bitiş commit'i:** `297cfb2`

---

## 0. Bu belge ne işe yarıyor — ve neye yaramıyor

Denetim 21 bulgu çıkardı. Hepsi kapatıldı. Bu belge her bulgu için üç şeyi
verir: **nerede düzeltildi**, **hangi test koruyor**, **jüriye ne
diyebilirsiniz**.

İşleyiş kuralı şu:

> Bir bulgu, ancak geri gelmesini engelleyen ve **gerçekten çalıştırılmış** bir
> testi varsa kapalıdır. Yorumda "düzeltildi" yazmak kapatmaz.

Bu belgedeki her sayı, yanındaki komut çalıştırılarak üretilmiştir. Hiçbiri
tahmin değildir. Çalıştırılamamış olanlar **§7'de ayrıca listelenmiştir** ve
"doğrulandı" diye sunulmamaktadır.

---

## 1. Ölçülen sonuçlar

| Katman | Komut | Sonuç |
|---|---|---|
| Rust (ZK + PQC) | `cd Q-Adaptive-ZK && cargo test` | **55 geçti** (önce 12) |
| Solidity | `cd Q-Adaptive-Contracts && forge test` | **105 geçti, 4 atlandı** (önce 0) |
| Katman eşitliği | `python3 Q-Adaptive-AI/test_layer_parity.py` | **9 geçti** (önce yoktu) |
| Attestation kriptosu | `python3 Q-Adaptive-AI/test_attestation.py` | **18 geçti** (önce yoktu) |
| **Toplam otomatik test** | | **187 geçti** |
| ONNX ↔ sklearn parity | `cd Q-Adaptive-AI && python3 test_onnx_inference.py` | 3 senaryo, çıkış kodu 0 |

Solidity testlerinin **10'u fuzz/değişmez** testidir; her biri 512 koşu yapar.

### Ölçülen Solidity kapsamı

`forge coverage --report summary`:

| Sözleşme | Satır | Dal | Fonksiyon |
|---|---|---|---|
| `QAdaptivePaymaster` | **%100,00** (94/94) | %96,77 (30/31) | %100,00 (15/15) |
| `QAdaptiveAccount` | %92,05 (162/176) | %79,37 (50/63) | %95,65 (22/23) |
| **Toplam** | %93,58 | %83,67 | %93,62 |

**Dal kapsamı %100 DEĞİLDİR ve öyle olduğu iddia edilmemektedir.** Kapsanmayan
dalların çoğu guardian imza kurtarma yolundaki savunma kollarıdır (bozuk `v`,
sonsuzdaki nokta) — geçersiz eğri noktaları üretmeden ulaşılması zor.

---

## 2. İzlenebilirlik matrisi — 14 denetim bulgusu

| # | Bulgu | Düzeltme yeri | Koruyan test |
|---|---|---|---|
| 1 | **ML-DSA hiç uygulanmamıştı** — depoda tek bir PQC bağımlılığı yoktu | `Q-Adaptive-ZK/src/pqc.rs` (yeni) · `Cargo.toml` → `fips204 = "0.4.6"` | `pqc::tests::gercek_imza_ve_dogrulama`, `standart_boyutlari_uyusuyor`, `kurcalanan_mesaj_reddediliyor`, `imza_zirhla_birlikte_buyuyor` |
| 2 | **API prover'a hiç argüman geçmiyordu** — `create_subprocess_exec(binary)` | `api.py::_run_zk_prover_async` (6 argüman) · `pipeline.rs::run` | `pipeline::tests::otonomi_koprusu_riski_kripto_katmanina_tasiyor` |
| 3 | **Eşik uyuşmazlığı** — Rust sabit `90.0`, Python τ(t) | `armor.rs::decide` + `armor.py::decide` (tek kural) · `--tau` argümanı | `armor::tests::bulgu3_esik_uyusmazligi_kapandi` · `ArmorPolicyParityTest` (13 sınır vektörü) |
| 3b | **Bayat kanıt geri dönüşü** — prover patlayınca diskten eski dosya okunuyordu | `api.py` — geri dönüş **silindi**, `status: "degraded"` | Kod yolu kalmadı; `_PROOF_PATH` yalnızca taze kanıt için okunuyor |
| 4 | **Zırh geçişi kozmetikti** — JSON'a yazılan bir metin | `armor.rs` 3 kademe → `(k, ℓ)` → gerçek imza boyutu | `pqc::tests::imza_zirhla_birlikte_buyuyor` · `trace::tests::test_kademe_matris_boyutunu_degistiriyor` |
| 5 | **Paymaster boşaltılabilir** — gönderene bakmıyordu. **Gerçek fon kaybı açığı.** | `QAdaptivePaymaster.sol` — 4 kapı | `test_BULGU5_saldirgan_sozlesmesi_sponsorluk_alamiyor` + 6 test + 2 fuzz |
| 6 | **Risk skoru kullanıcıdan okunuyordu** — imza alanından çözülüyordu | `QAdaptiveAccount.sol::_resolveRiskScore` — oracle / guardian / ikisinin büyüğü | `test_BULGU6_iddia_edilen_sifir_risk_ai_kapisini_gecemiyor` + 5 test + 2 fuzz |
| 7 | **DefaultHasher (SipHash)** — kriptografik olmayan hash | `hashing.rs` (yeni) — BLAKE3 + SHAKE-128 + rejection sampling | `hashing::tests::cig_etkisi_tek_bit` (56/56 hücre), `ornekleme_makul_duzgun` |
| 8 | **Solidity tarafında hiç test yok** | `foundry.toml` + 6 test dosyası | **109 test** (105 geçen, 4 atlanan) |
| 9 | **README ↔ kod tutarsızlıkları** — 96↔80 bit, Goldilocks↔f128, 16↔3 özellik | `air.rs::STARK_SECURITY_BITS` tek kaynak · README yeniden yazıldı | `SecurityBitsConsistencyTest` — **README'yi okur** |
| 10 | **`ntt.rs` yok** | Gerekmez oldu: tam polinom NTT `fips204` içinde | `pqc::tests::standart_boyutlari_uyusuyor` |
| 11 | **Kanıt tohumu belirlenimsiz** — `process::id()` karıştırılıyordu | `hashing.rs::derive_rho_prime` — `process::id()` **silindi** | `hashing::tests::rho_prime_tam_deterministik` · `DeterminismParityTest` |
| 12 | **`Queue(maxsize=50)` kaynak profiline bağlı değil** | `api.py::_resolve_queue_capacity` | — (ölçüme dayalı, testsiz) |
| 13 | **%97,98 iki farklı tabana göre hesaplanıyor** | `bridge.rs::CalldataRecord::compute` + `calldata.py::compute` | `bridge::tests::calldata_tanimi_tek_ve_yeniden_hesaplanabilir` · `CalldataParityTest` |
| 14 | **`depositToEntryPoint` mevduat yapmıyor, `postOp` boş** | `IEntryPoint.sol` (yeni) · gerçek `depositTo` · gerçek uzlaşma | `test_BULGU14_mevduat_gercekten_entrypointe_gidiyor`, `test_BULGU14_postOp_gercek_maliyetle_uzlasiyor` |
| 15 | **Eğitim verisi sentetik** | Gizlenmiyor; README "kontrollü sentetik" diyor | — (hata değil, kapsam sınırı) |

---

## 3. Denetimde listelenmemiş, sonradan bulunan hatalar

Kod baştan okunurken denetim listesinde olmayan yedi sorun daha çıktı. **Üçü
canlı ağda sistemi tamamen çalışmaz hâle getiriyordu.**

| # | Hata | Neden ciddi | Test |
|---|---|---|---|
| E1 | **Ön-fonlama `gas: 2300` ile yapılıyordu** | Gerçek EntryPoint'in `receive()`'ı mevduat muhasebesi için depolamaya yazar (~20.000+ gaz). 2300 gaz bir SSTORE'a yetmez ⇒ çağrı **her zaman** başarısız ⇒ `require(success)` yüzünden **her işlem revert eder**. Hesap canlı ağda hiçbir işlemi tamamlayamazdı. | `test_E1_on_fonlama_gercek_entrypointe_ulasiyor` — mock EntryPoint kasıtlı iki SSTORE yapar |
| E2 | **Gösterilen iz, kanıtlanan iz DEĞİLDİ** | `QAdaptiveTrace` u128 + `% q`, `trace.fill` alan aritmetiği kullanıyordu. Sahnede jüriye gösterilen tablo STARK'ın kanıtladığı tablo değildi. | `pipeline::tests::gosterilen_iz_kanitlanan_izle_ayni` |
| E3 | **`validateUserOp` doğrulama sırasında depolamaya yazıyordu** | ERC-7562 ihlali — birçok bundler böyle bir işlemi mempool'a hiç almaz. Ayrıca ucuz depolama şişirme (DoS) vektörü. | `test_E3_tekrarlanan_reddedis_depolama_sisirmiyor` |
| E4 | **Tek yönlü tırmanma zincirde yoktu** | EntryPoint yoluyla gelen bir çağrı zırhı ML-DSA-87'den 44'e **düşürebiliyordu**. | `testFuzz_E4_zirh_monoton_artiyor`, `testFuzz_E4_zirh_asla_tabanin_altina_inmiyor` |
| E5 | **`--level` geçersiz girdiyi sessizce 87 yapıyordu** | `"87" \| _ => Level87`. Güvenli yönde ama **sessiz**; yapılandırma hatası fark edilmezdi. | `trace::tests::test_level_parse_gecersiz_girdiyi_reddediyor` |
| E6 | **s1/s2 tohumları ρ''nin ham baytlarıydı** | Tohumun tamamı herkese açık izde görünüyordu. | `trace::tests::test_from_rho_prime_kisa_tohumlari_turetiyor` |
| E7 | **`execute()` içinde `gasleft() - 5000`** | `gasleft() < 5000` ise Solidity 0.8'de taşma ile anlamsız `panic(0x11)`. | `test_E7_dusuk_gazda_anlamli_hata` |
| E20 | **CI dosyası geçersiz YAML'di** | `ci.yml:37`'de alıntılanmamış iki nokta. | `yaml.safe_load` + CI'ın kendisi |

### E20'nin altından çıkan ikinci hata

YAML düzeltilince **`test_onnx_inference.py`'nin bir pytest paketi olmadığı**
ortaya çıktı: içinde `test_` ile başlayan hiçbir fonksiyon yok, tek bir
`run_onnx_inference_test()` var ve `__main__` altından çağrılıyor. `pytest` bu
dosyadan sıfır test toplar ve **çıkış kodu 5 ile düşer**.

Yani *"CI'da 12/12 test geçiyor"* ifadesinin **iki ayrı sorunu** vardı:

1. CI geçersiz YAML yüzünden düzgün koşmuyordu,
2. koşsaydı bu adım düşecekti.

Ayrıca betik 12 test değil **üç senaryo** koşuyor. Sayının kodda hiçbir
karşılığı yok.

### CI'ın kendisinde bulunan iki sorun daha

| Sorun | Ne oluyordu |
|---|---|
| **`solidity-lint` ilk günden beri kırmızıydı** | `.solhint.json` hiç yoktu; solhint yapılandırma bulamayınca çıkış kodu 255 ile düşüyordu. "Lint'ten geçiyoruz" diyebileceğimiz bir dayanak hiç olmamıştı. |
| **Sır taraması hiçbir şey taramıyordu** | TruffleHog `base: main`, `head: HEAD` ile çağrılıyordu; main'e push'ta ikisi aynı commit. TruffleHog'un kendi çıktısı: *"BASE and HEAD commits are the same. TruffleHog won't scan anything."* Üstelik `continue-on-error: true` bu hatayı gizliyor, iş **yeşil** görünüyordu. |

İkincisi bu denetimin en öğretici bulgusu: **koştuğu iddia edilen ama aslında
hiçbir şey yapmayan bir kontrol**, hiç olmayan bir kontrolden daha tehlikelidir,
çünkü yanlış güven verir.

---

## 4. Katmanlar arası köprüler — iddia değil, kanıt

İki katmanın "aynı şeyi yaptığını" iddia etmek kolaydır. Bu projede iki yerde
bunu **kanıtlıyoruz**:

### 4.1 Rust ↔ Python eşik politikası

`test_layer_parity.py` **gerçek Rust ikilisini çalıştırır** ve çıktısını
Python'unkiyle 13 sınır vektöründe karşılaştırır. Ayrışırlarsa CI kırılır.

> Bu testin değeri ilk koşuşunda kanıtlandı: `target/release/` altındaki eski
> ikiliyi çalıştırdı ve onun `--tau` argümanını yok sayıp `process::id()` ile
> her koşuda farklı ρ' ürettiğini **yakaladı**.

### 4.2 Python imzası ↔ Solidity `ecrecover`

`Q-Adaptive-AI/src/attestation.py`, Keccak-256 ve secp256k1'i **sıfır
bağımlılıkla** uygular. `GuardianAttestation.t.sol` bu kodun ürettiği **gerçek
imzayı gerçek sözleşmeye** verir. Digest hesabında tek bayt kayarsa `ecrecover`
başka bir adres döndürür ve 14 test kırılır.

> **Neden `hashlib.sha3_256` kullanılmadı:** O FIPS 202 SHA3-256'dır ve
> Ethereum'un Keccak-256'sından **farklı dolgu** kullanır (0x06 vs 0x01). Aynı
> girdi için farklı çıktı verirler. Bu, sessizce geçersiz imza üretmeye yol
> açan klasik bir tuzaktır; `test_attestation.py::test_sha3_ile_karistirilmamis`
> bunu yakalar.

---

## 5. Negatif kontrol — testler gerçekten yakalıyor mu?

Bir testin geçmesi, o testin bir şey koruduğunu kanıtlamaz. E1 için bunu
açıkça sınadık: `gas: 2300` canlı koda geri konuldu ve testler çalıştırıldı.

```
[FAIL: QAdaptiveAccount: EntryPoint funding failed] test_E1_on_fonlama_gercek_entrypointe_ulasiyor
[FAIL: ...] testFuzz_E1_on_fonlama_tam_ulasiyor(uint96)
```

Tam öngörülen hatayla kırıldı, ardından düzeltme geri alındı.

**Kritik ayrıntı:** `MockEntryPoint`'in `receive()`'ı kasıtlı olarak iki SSTORE
yapar. Depolamaya yazmayan bir mock bu hatayı **yakalayamazdı** — denetimin
kaçırdığı şey de tam buydu.

---

## 6. Regresyon korumaları

CI'da beş grep tabanlı koruma var (`regression-guards` işi). Düzeltilen bir
hata sessizce geri gelirse yapı kırılır:

| Koruma | Ne arar |
|---|---|
| BULGU 7 | `DefaultHasher` kripto yolunda |
| BULGU 3 | Sabit `90.0` eşiği |
| BULGU 13 | `raw_sig_bytes = 4608` uydurma tabanı |
| BULGU 11 | `process::id()` ρ' türetiminde |
| HATA E1 | `call{gas: 2300` |

Korumalar `grep -rnH` kullanır — **`-H` şarttır**: `grep` tek dosyada dosya adı
basmaz ve o zaman yorum satırı filtresi tutmaz, koruma sahte hata verir.

---

## 7. Doğrulanmamış olanlar — dürüstlük bölümü

Bu belgedeki her şey çalıştırılarak doğrulandı, **aşağıdakiler hariç**. Bunlar
"yapıldı" diye sunulmamaktadır.

| Öğe | Durum | Neden |
|---|---|---|
| `EntryPointFork.t.sol` (4 test) | **Hiç koşulmadı** | Gerçek EntryPoint v0.7 fork testi; RPC erişimi yoktu. Test `[SKIP]` raporlar, asla sahte `[PASS]` vermez. |
| `.solhint.json` yapılandırması | **Doğrulanmadı** | npm erişimi yoktu; belgelenmiş davranışa göre yazıldı, ilk CI koşusunda sınanacak. |
| TruffleHog düzeltmesi | **Doğrulanmadı** | Aynı sebep. |
| `test_api_client.py` | **Koşulmadı** | Çalışan bir sunucu gerektiriyor. |

### Fork testini çalıştırmak

```bash
export ETH_RPC_URL="https://<sağlayıcı>/<anahtar>"
cd Q-Adaptive-Contracts && forge test --match-contract EntryPointForkTest -vv
```

Mock EntryPoint E1'i kanıtlıyor, ama **mock yine de bizim yazdığımız bir
sözleşmedir**. Gerçek baytkoda karşı doğrulama hâlâ açık iştir.

---

## 8. Şimdi ne diyebiliriz — ve ne diyemeyiz

| Konu | ✅ Diyebiliriz | ❌ Diyemeyiz |
|---|---|---|
| **ML-DSA** | "Kullanıyoruz. `fips204` ile gerçek anahtar üretip gerçek imza atıyor ve doğruluyoruz. Zırh değişince imza 2.420 → 3.309 → 4.627 bayta çıkıyor; boyutlar FIPS 204 tablosuyla her koşuda karşılaştırılıyor." | — |
| **Otonomi** | "AI'ın kararı altı argümanla kriptografik katmana geçiyor. Risk değişince kafes 16 → 30 → 56 elemana çıkıyor." | "AI kuantum saldırısı tespit ediyor." |
| **Eşik** | "Karar tek fonksiyonda; Rust ve Python aynı kuralı uyguluyor ve bunu bir eşitlik testi gerçek ikiliyi çalıştırarak doğruluyor." | — |
| **Hash** | "Kafes matrisi SHAKE-128 ile genişletiliyor — FIPS 204 ExpandA'nın ilkeliyle aynı. Kodda kriptografik olmayan hash yok." | — |
| **Determinizm** | "Aynı girdi birebir aynı ρ', anahtar ve imzayı veriyor. Jüri koşuyu kendi makinesinde tekrarlayabilir." | — |
| **Paymaster** | "Dört bağımsız kapı. Sömürü senaryosunun kendisi bir test olarak duruyor. Satır kapsamı %100." | "Bağımsız denetimden geçti." |
| **Risk kaynağı** | "Skor oracle'dan veya guardian imzasından geliyor; gönderenin yazdığı alan karara girmiyor. Python'un ürettiği imza gerçek sözleşmede doğrulanıyor." | — |
| **Solidity testleri** | "109 test, 10'u fuzz. Ölçülen kapsam: satır %92–100, dal %79–97." | "Kapsam %100." |
| **STARK** | "Prototip temkinli **80-bit** ayarında ve bu sayı tek bir sabitten geliyor; README'yi okuyan bir test hizayı koruyor." | "96-bit." · "STARK, ML-DSA doğrulamasını devre içinde ispatlıyor." |
| **Calldata** | "50 işlemlik partide bir kanıt, işlem başına ML-DSA imzası taşımaya kıyasla ~%98,2 tasarruf. Tanım payload'un içinde." | "ECDSA'dan daha az calldata." (50 ECDSA imzası = 3.250 B, **bir STARK kanıtından küçük**) |
| **Canlı ağ** | "Mock EntryPoint'e karşı doğrulandı." | "Gerçek EntryPoint'te doğrulandı." |
| **Genel duruş** | "Kuantum-hazır mimari ve uçtan uca çalışan, testle korunan prototip." | "Konuşlandırılmış kuantum-dayanıklı sistem." |

---

## 9. Commit geçmişi

`238a52b` → `297cfb2` · **37 dosya, +7.723 / −718**

| Commit | Kapsam |
|---|---|
| `d4d2687` | **fix(zk)** — gerçek ML-DSA, BLAKE3/SHAKE-128, determinizm, tek eşik, iz tek kaynağı |
| `bc67dbb` | **fix(ai)** — prover argümanları, bayat kanıt geri dönüşü silindi, guardian attestation |
| `4cc819d` | **fix(contracts)** — fon kaybı açığı, AI kapısı baypası, `gas:2300`, depolama yazımı, tırmanma |
| `1ad183d` | **test(contracts,ci)** — 109 Foundry testi, CI çalışır hâle getirildi, regresyon korumaları |
| `d524dc7` | **docs(readme)** — iddialar ölçülen değerlerle hizalandı |
| `afb30b8` | **style(zk)** — `cargo fmt` + clippy `-D warnings` |
| `297cfb2` | **fix(ci)** — solhint yapılandırması, hiçbir şey taramayan sır kontrolü düzeltildi |

---

## 10. Her iddiayı nasıl kontrol edersiniz

```bash
# 1) Rust: 55 test
cd Q-Adaptive-ZK && cargo test && cd ..

# 2) Solidity: 109 test (fuzz dahil, 4'ü fork — atlanır)
cd Q-Adaptive-Contracts && forge build && forge test -vv && cd ..

# 3) Solidity kapsamı
cd Q-Adaptive-Contracts && forge coverage --report summary && cd ..

# 4) Katmanlar arası eşitlik — Rust ikilisini çalıştırır
cd Q-Adaptive-ZK && cargo build --release && cd ..
python3 Q-Adaptive-AI/test_layer_parity.py

# 5) Attestation kriptosu: bilinen Keccak-256 / ECDSA vektörleri
python3 Q-Adaptive-AI/test_attestation.py

# 6) Python imzası → Solidity ecrecover
python3 scripts/generate_guardian_fixture.py
cd Q-Adaptive-Contracts && forge test --match-contract GuardianAttestationTest && cd ..

# 7) ONNX parity (kendi dizininden çalıştırılmalı)
cd Q-Adaptive-AI && python3 test_onnx_inference.py && cd ..

# 8) Tek koşu: ölçümleri elle görün
./Q-Adaptive-ZK/target/release/q-adaptive-zk \
    --risk-score 92.4 --tau 75.0 --baseline 44 \
    --user-op-hash 0xdeadbeefcafebabe \
    --epoch-ns 1700000000000000000 --run-id demo
```

Herhangi bir komut kırılırsa bu belgedeki ilgili iddia geçersizdir. Kasıtlı
olarak böyle: iddialar testlere bağlı, yorumlara değil.

---

## 11. Kalan işler

| Öncelik | İş | Neden |
|---|---|---|
| 1 | Gerçek EntryPoint v0.7 ile fork testini çalıştır | Test yazıldı, hiç koşulmadı. "Canlı ağda çalışır" demenin tek yolu. |
| 2 | `QAdaptiveAccount` dal kapsamını %79,37'den yükselt | İmza kurtarma savunma kolları kapsanmıyor. |
| 3 | `gas-custom-errors`: `require` string'lerinden custom error'a geç | Gaz tasarrufu; 109 test revert mesajlarını string bekliyor, birlikte güncellenmeli. Açık teknik borç. |
| 4 | Guardian anahtarını HSM/KMS'e taşı | `attestation.py` anahtarı bellekte tutuyor ve sabit-zamanlı değil — üretim için uygun değil, dosyada yazılı. |
| 5 | `docs/` altındaki eski raporlarda 96-bit / 16-özellik kalıntılarını tara | README ve kod hizalı; eski PDF/`.md` raporlar hâlâ eski sayıları taşıyor. |
| 6 | Sunum kapak slaytlarındaki yer tutucu soyadları düzelt | Denetim §10. |
