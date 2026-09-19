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

## 4. Kalan iş

`continue-on-error: true` hâlâ duruyor. Bir sonraki koşuda bu triyajdan
sonra kaç bulgu kaldığını görüp, sayı sıfırlanırsa o satır **kaldırılmalı** —
ancak o zaman "Slither'dan geçiyoruz" demek için dayanak olur.

```bash
cd Q-Adaptive-Contracts
slither .                          # dedektörler
slither . --print human-summary    # özet tablo
```
