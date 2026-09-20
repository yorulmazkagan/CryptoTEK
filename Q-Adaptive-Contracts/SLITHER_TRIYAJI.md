# Slither Bulgu Triyajı

**Koşu:** CI #10 · **Slither:** 0.11.6 · **Tarih:** 19 Eylül 2026

```
Number of high issues:          0
Number of medium issues:        4
Number of low issues:           9
Number of informational issues: 11
Number of optimization issues:  4
```

Slither bu depoda **daha önce hiç çalışmamıştı** — önce solhint yapılandırma
hatasıyla adıma sıra gelmiyordu, sonra `forge` kurulu olmadığı için anında
çöküyordu. `continue-on-error` her iki durumu da gizliyordu. Bu, bulguların
ilk kez okunduğu triyaj.

> **Sıfır yüksek önem dereceli bulgu.** Fon kaybı, reentrancy ve erişim
> kontrolü sınıflarında Slither bir şey görmedi.

---

## 1. Düzeltilen gerçek bulgular

### `missing-zero-check` — Account'ta sıfır adres kontrolü yoktu

Slither dört yerde işaret etti. İkisi **gerçek**, ikisi **kasıtlı**.

| Yer | Karar |
|---|---|
| `constructor._entryPoint` | ✅ **Düzeltildi.** Sıfır EntryPoint hesabı tamamen kullanılamaz kılar. Paymaster bu kontrolü zaten yapıyordu — **tutarsızlıktı**. |
| `constructor._owner` | ✅ **Düzeltildi.** Sıfır sahip, hesabı geri alınamaz şekilde sahipsiz bırakır. |
| `constructor._guardianSigner` | ⚪ **Kasıtlı.** Sıfır adres "guardian yok" demek; `_verifyAttestation` bunu açıkça ele alıyor (`if (guardianSigner == address(0)) return (0, false)`). |
| `setGuardianSigner(newSigner)` | ⚪ **Kasıtlı.** Aynı sebep — guardian kaynağını devre dışı bırakmanın yolu. |

### `solc-version` — `^0.8.19` bilinen ciddi derleyici hataları içeriyor

Slither üç hata saydı: `VerbatimInvalidDeduplication`,
`FullInlinerNonExpressionSplitArgumentEvaluationOrder`,
`MissingSideEffectsOnSelectorAccess`.

`foundry.toml` zaten `solc_version = "0.8.24"` ile derliyordu, ama **pragma
tabanı 0.8.19'du** — yani sözleşmeler teorik olarak hatalı bir derleyiciyle
derlenebilirdi.

✅ **Düzeltildi:** 12 dosyada pragma `^0.8.19` → `^0.8.24`. `.solhint.json`
içindeki `compiler-version` kuralı da aynı değere çekildi.

### `unindexed-event-address` — guardian rotasyonu filtrelenemiyordu

`GuardianSignerUpdated(address,address)` olayının hiçbir parametresi
`indexed` değildi.

✅ **Düzeltildi:** İki adres de `indexed`. Guardian rotasyonu denetim
açısından kritik bir olay ve belirli bir adrese göre filtrelenebilmeli.

---

## 1b. İkinci tur — kapı açıldıktan sonra çıkan 6 bulgu

`continue-on-error` kaldırılıp Slither gerçek bir kapı hâline gelince, ilk
triyajda görülmeyen iki dedektör daha bildirimde bulundu.

### `immutable-states` (4 bulgu) — setter eklendi, `immutable` YAPILMADI

Slither şunların hiç yeniden atanmadığını, dolayısıyla `immutable`
yapılabileceğini bildirdi:

| Alan | Slither haklı mıydı | Ne yapıldı |
|---|---|---|
| `QAdaptiveAccount.owner` | Evet, yalnızca kurucuda atanıyordu | `transferOwnership()` eklendi |
| `QAdaptiveAccount.aiCore` | Evet | `setAICore()` eklendi |
| `QAdaptivePaymaster.owner` | Evet | `transferOwnership()` eklendi |
| `QAdaptivePaymaster.epochDuration` | Evet | `setEpochDuration()` eklendi |

**Neden `immutable` yapmadık:** Bu bir *optimizasyon* bulgusu, güvenlik
bulgusu değil. Ve önerilen düzeltmeyi uygulamak bir **gerileme** olurdu:

- `owner` bu sözleşmelerde 11 + 5 fonksiyonu kapılıyor. Bir **akıllı
  hesapta** sahip anahtarının ele geçirilmesi gerçek bir senaryodur;
  sahipliği kalıcı olarak dondurmak o anahtardan kurtulma yolunu da
  kapatırdı.
- `aiCore` sabitlenirse, oracle sözleşmesi kullanımdan kalktığında ya da
  ele geçirildiğinde hesap kurtarılamaz hâle gelirdi.
- `epochDuration` zaten bir tutarsızlıktı: `updateLimits` diğer üç limiti
  güncelleyebiliyordu ama dönem uzunluğu dışarıda kalmıştı.

Yani eksik olan gaz optimizasyonu değil, **devir yeteneğiydi**. Alanları
gerçekten değiştirilebilir kılmak bulguyu meşru biçimde kapattı —
dedektörü susturarak değil. 12 yeni test eklendi.

### `missing-zero-check` (2 bulgu) — hedefli susturma

Kalan iki bulgu `_guardianSigner` (kurucu) ve `setGuardianSigner(newSigner)`.

**Sıfır adres burada KASITLI olarak geçerlidir:** "guardian yok" anlamına
gelir ve `_verifyAttestation` bunu açıkça ele alır
(`if (guardianSigner == address(0)) return (0, false)`). Sıfır kontrolü
eklemek, guardian imzası kaynağını devre dışı bırakma yeteneğini ortadan
kaldırırdı.

Dedektörün **tamamı kapatılmadı** — aynı dedektör `_entryPoint` ve `_owner`
için gerçek bir eksik yakalamıştı (bkz. §1). Bunun yerine tam o iki satırda
`// slither-disable-next-line missing-zero-check` kullanıldı ve gerekçe
koda yorum olarak yazıldı. `test_guardian_sifira_ayarlanabiliyor` bu
kararın bilinçli olduğunu sabitliyor.

> **Doğrulanmadı:** Bu iki susturma yorumu ve yeni setter'ların bulguları
> kapattığı yerelde sınanamadı (Slither pip ile kuruluyor, ağ erişimi
> yoktu). Bir sonraki CI koşusunda doğrulanacak. Susturma beklendiği gibi
> çalışmazsa burada gerekçesiyle güncellenecek — dedektör kapatılmayacak.

---

## 2. Gerekçeyle dışlanan bulgular

Bunlar `slither.config.json` içinde `detectors_to_exclude` ile dışlandı.
**Hiçbiri "uyarı çıkmasın diye" kapatılmadı.**

### `timestamp` (5 bulgu)

`block.timestamp` karşılaştırmaları: attestation son geçerliliği, 2 saatlik
zaman kilidi, paymaster dönem sayacı.

**Neden kabul edilebilir:** Madencinin zaman damgasını oynatabileceği aralık
saniye mertebesindedir. Bizim pencerelerimiz **2 saat** ve **1 gün**. Saniyelik
sapma bu ölçekte anlamsız. Zaman kilidi zaten bir hata değil, ürünün özelliği.

### `assembly` (3 bulgu)

İki kullanım var, ikisi de yorumlu:
- `QAdaptivePaymaster.validatePaymasterUserOp` — calldata'dan 4 baytlık
  fonksiyon seçicisini okumak
- `QAdaptiveAccount._verifyAttestation` — 65 baytlık ECDSA imzasını `r`/`s`/`v`'ye
  ayırmak
- `QAdaptiveAccount.execute` — revert sebebini olduğu gibi yukarı iletmek

**Neden kabul edilebilir:** Üçünün de Solidity'de assembly'siz dengi yok ya da
çok daha pahalı.

### `low-level-calls` (3 bulgu)

**Neden kabul edilebilir:** ERC-4337 bunu **zorunlu** kılıyor. EntryPoint
ön-fonlaması, `execute()` hedef çağrısı ve `transferHighValue` `.call` ile
yapılmak zorunda. Dahası, hata E1 tam da bu çağrılardan birine gaz stipend'i
konulmasından çıkmıştı — yani buradaki risk düşük seviyeli çağrının kendisi
değil, ona müdahale etmekti.

### `naming-convention` (3 bulgu)

`updateLimits(_maxCostPerOperation, _perAccountEpochQuota, _epochBudget)`
parametreleri alt çizgiyle başlıyor.

**Neden kabul edilebilir:** Alt çizgi, parametrelerin aynı adlı durum
değişkenlerini **gölgelemesini** önlemek için. Kaldırılırsa `maxCostPerOperation
= maxCostPerOperation` gibi bir gölgeleme hatası riski doğar.

### `unused-return` (4 bulgu)

`aiCore.getGlobalRiskStatus()` iki değer döndürüyor `(riskScore, isPanicMode)`
ve her çağrı yerinde yalnızca biri kullanılıyor.

**Neden kabul edilebilir:** `(, bool isPanicMode) = ...` deyimi Solidity'de
standart ve okunaklı. Kullanılmayan değeri bir değişkene atamak yeni bir
kullanılmayan-değişken uyarısı üretirdi.

---

## 3. Dışlanmayan ve açık kalan

`filter_paths` ile `lib/` ve `test/` dışlandı — üçüncü taraf kod ve testler.
**Sözleşmelerin kendisinde hiçbir dedektör kategorisi körlenmedi.**

`exclude_informational`, `exclude_low`, `exclude_medium`, `exclude_high`
bilinçli olarak `false`: yeni bir bulgu çıkarsa görünmesini istiyoruz.

---

## 4. Slither artık gerçek bir kapı

**Koşu #11'de geriye bulgu kalmadı** — annotations'ta Slither kaynaklı hiçbir
hata yok. Bunun üzerine `continue-on-error: true` satırı dedektör adımından
**kaldırıldı**.

Bu, "Slither'dan geçiyoruz" ifadesinin ilk kez bir dayanağı olduğu an. Yeni
bir bulgu çıkarsa CI **gerçekten kırılır**.

### İki koruma daha eklendi

**`set -o pipefail`** — dedektör adımı `slither . | tee slither-report.txt`
şeklinde çalışıyor. Boru hattında çıkış kodu **son** komuttan gelir; yani
`pipefail` olmadan `slither` düşse bile `tee` sıfır döndürür ve kapı sessizce
açılırdı. Bu, aynı oturumda üç kez düştüğümüz "yeşil ama boş" tuzağının
dördüncüsü olurdu.

**Sürüm sabitlendi** — `slither-analyzer==0.11.6`. Ana sürümler yeni
dedektörler ekliyor; sabitlenmezse bugün yeşil olan CI, biz hiçbir şey
değiştirmediğimiz bir gün kendiliğinden kırılır. Yükseltme bilinçli bir karar
olmalı: sürümü `ci.yml`'de artır, bulguları triyaj et, bu dosyayı güncelle.

### Özet tablosu neden hâlâ tavsiye niteliğinde

`--print human-summary` adımında `continue-on-error` **bilerek duruyor**. O
adım zafiyet aramaz, yalnızca istatistik basar; basmayı beceremezse bu CI'ı
kırmak için bir sebep değildir.

```bash
cd Q-Adaptive-Contracts
slither .                          # dedektörler
slither . --print human-summary    # özet tablo
```
