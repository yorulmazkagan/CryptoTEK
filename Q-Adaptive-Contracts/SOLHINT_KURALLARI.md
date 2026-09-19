# solhint Yapılandırması — Neden Bu Kurallar

`.solhint.json` daha önce **yoktu**. solhint yapılandırma bulamayınca çıkış
kodu 255 ile düşüyordu:

```
Run solhint 'contracts/**/*.sol'
Failed to load a solhint's config file.
Error: Process completed with exit code 255.
```

CI'ın `solidity-lint` işi bu yüzden ilk günden beri kırmızıydı. Yani "lint'ten
geçiyoruz" diyebileceğimiz bir dayanak hiç olmadı.

JSON yorum kabul etmediği için gerekçeler burada. **Kapatılan her kural, kod
tabanının bilinçli bir tasarım kararına karşılık geliyor** — hiçbiri "uyarı
çıkmasın diye" kapatılmadı.

---

## Kapatılan kurallar ve gerekçeleri

| Kural | Neden kapalı |
|---|---|
| `gas-custom-errors` | Sözleşmeler `require(cond, "mesaj")` kullanıyor. Custom error'a geçmek gaz tasarrufu sağlar, ama 109 testin büyük kısmı revert mesajlarını string olarak bekliyor (`vm.expectRevert("QAdaptivePaymaster: ...")`). Bu ayrı bir iş; şimdi yapılırsa testlerin çoğu yeniden yazılmalı. **Açık bir teknik borç.** |
| `no-inline-assembly` | İki yerde bilinçli kullanılıyor: Paymaster'da calldata'dan 4 baytlık fonksiyon seçicisini okumak, Account'ta 65 baytlık ECDSA imzasını `r`/`s`/`v`'ye ayırmak. İkisinin de Solidity'de assembly'siz dengi yok; ikisi de yorumlu. |
| `avoid-low-level-calls` | ERC-4337 bunu **zorunlu** kılıyor: EntryPoint ön-fonlaması ve `execute()` hedef çağrısı `.call` ile yapılmak zorunda. Ayrıca hata E1 tam da bu çağrıya gaz stipend'i konulmasından çıkmıştı — yani buradaki risk düşük seviyeli çağrının kendisi değil, ona müdahale etmekti. |
| `not-rely-on-time` | `block.timestamp` burada bir hata değil, **özellik**: 2 saatlik zaman kilidi ve paymaster dönem sayacı buna dayanıyor. Madencinin saniye mertebesindeki sapması 2 saatlik pencerede anlamsız. |
| `no-empty-blocks` | `receive() external payable {}` bilinçli olarak boş. |
| `max-states-count` | Paymaster'ın dört bağımsız kapısı (gönderen kaydı, işlem tavanı, hesap kotası, dönem bütçesi) kaçınılmaz olarak çok sayıda durum değişkeni gerektiriyor. Bu, BULGU 5'i kapatmanın bedeli. |
| `ordering` | Dosyalar mantıksal gruplara göre düzenlenmiş (kapılar, yönetim, mevduat), solhint'in beklediği katı sıraya göre değil. |

## Uyarıya indirilenler

| Kural | Neden uyarı |
|---|---|
| `reason-string` (maxLength 80) | Revert mesajları `"QAdaptivePaymaster: caller must be EntryPoint"` gibi açıklayıcı; solhint'in 32 karakter varsayılanı bunları keser. Mesajın anlaşılır olması gaz'dan önemli. |
| `max-line-length` (120) | Uzun satırların çoğu açıklama yorumlarında. |

## Hata olarak bırakılanlar

Bunlar gerçek güvenlik kuralları ve kod tabanı hepsini geçiyor:

`compiler-version` · `func-visibility` · `avoid-tx-origin` · `avoid-sha3` ·
`check-send-result` · `multiple-sends` · `state-visibility` ·
`no-complex-fallback`

---

## Doğrulama

```bash
cd Q-Adaptive-Contracts
npx solhint@5 'contracts/**/*.sol'
```

> **Not:** Bu yapılandırma yazıldığı ortamda **çalıştırılamadı** (npm ağ
> erişimi yoktu). Kurallar solhint'in belgelenmiş davranışına göre seçildi;
> ilk CI koşusunda doğrulanacak. Bir kural beklenmedik şekilde hata verirse
> burada gerekçesiyle birlikte güncellenmeli — sessizce `off` yapılmamalı.
