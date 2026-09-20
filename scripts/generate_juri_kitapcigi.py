#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q-ADAPTIVE — Sunum Taktikleri ve Jüri Soru-Cevap Kitapçığı (PDF üreteci).

Bu kitapçık, deponun kökündeki eski `Q-ADAPTIVE_Juri_Sorulari_ve_Savunma_
Kitapcigi.pdf` dosyasının yerini alır. Eskisi düzeltilmiş sayıları
öğretiyordu (%97,98 · 96-bit · 12/12 test · 16 özellik) ve ekip ondan
çalışırsa sahnede ekrandaki güncel rakamlarla çelişirdi.

Buradaki her cevap, koddan doğrulanmış değerlere dayanır. Cevaplar üç
katmanlıdır:

    KISA     — 20-30 saniyede söylenecek olan
    DERİN    — jüri üstüne giderse açılacak olan
    TUZAK    — bu soruda düşülebilecek hata

Kullanım:
    python3 scripts/generate_juri_kitapcigi.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pdf_ortak import (
    ACIK,
    CIZGI,
    GRI,
    ICERIK_GENISLIGI,
    KOK,
    KREM,
    LACI,
    MAVI,
    S,
    Sayfa,
    h1,
    h2,
    h3,
    kod,
    mad,
    notk,
    p,
    tablo,
)

CIKTI = KOK / "Q_ADAPTIVE_Juri_Kitapcigi.pdf"
Sayfa.USTBILGI = "Q-ADAPTIVE — Jüri Kitapçığı · Sunum Taktikleri ve Soru-Cevap"

YESIL_K = colors.HexColor("#0f7a46")
KIRMIZI_K = colors.HexColor("#b91c1c")

# ── Soru-cevap bloğu için ek stiller ─────────────────────────────────────────
S["soru"] = ParagraphStyle(
    "soru", fontName="DV-B", fontSize=10.6, leading=14.5,
    textColor=colors.white, backColor=LACI, borderPadding=7,
    spaceBefore=2, spaceAfter=0)
S["kisa"] = ParagraphStyle(
    "kisa", fontName="DV", fontSize=9.5, leading=14, textColor=LACI,
    leftIndent=6, spaceBefore=0, spaceAfter=5)
S["etiket"] = ParagraphStyle(
    "etiket", fontName="DV-B", fontSize=8.2, leading=11, textColor=MAVI,
    leftIndent=6, spaceBefore=5, spaceAfter=1)
S["etiket_k"] = ParagraphStyle(
    "etiket_k", fontName="DV-B", fontSize=8.2, leading=11, textColor=KIRMIZI_K,
    leftIndent=6, spaceBefore=5, spaceAfter=1)
S["tuzak"] = ParagraphStyle(
    "tuzak", fontName="DV", fontSize=9.2, leading=13.4, textColor=LACI,
    leftIndent=6, spaceAfter=4)


def soru(no: str, metin: str, kisa: str, derin: str | None = None,
         tuzak: str | None = None):
    """Tek bir soru-cevap bloğu.

    Blok `KeepTogether` ile sarılır: bir sorunun cevabı sayfa ortasından
    bölünürse, sahnede o sayfayı çevirmek zorunda kalırsınız.
    """
    o = [Paragraph(f"{no}. {metin}", S["soru"]), Spacer(1, 5)]
    o += [Paragraph("KISA CEVAP", S["etiket"]), Paragraph(kisa, S["kisa"])]
    if derin:
        o += [Paragraph("DERİNLEŞİRSE", S["etiket"]), Paragraph(derin, S["kisa"])]
    if tuzak:
        o += [Paragraph("TUZAK", S["etiket_k"]), Paragraph(tuzak, S["tuzak"])]
    o += [Spacer(1, 11)]
    return [KeepTogether(o)]


def kapak():
    a = [Spacer(1, 44 * mm)]
    a += [Paragraph("JÜRİ KİTAPÇIĞI", S["kapak_b"])]
    a += [Spacer(1, 6 * mm)]
    a += [Paragraph("Sunum Taktikleri ve Soru-Cevap", S["kapak_a"])]
    a += [Spacer(1, 14 * mm)]
    a += [Table([[""]], colWidths=[70 * mm], rowHeights=[2],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), MAVI)]),
                hAlign="CENTER")]
    a += [Spacer(1, 14 * mm)]
    a += [Paragraph(
        "<b>Q-ADAPTIVE (AI Guardian)</b><br/>"
        "Yapay Zekâ Güdümlü, Kuantum Dirençli Akıllı Cüzdan",
        S["kapak_a"])]
    a += [Spacer(1, 26 * mm)]
    a += [Paragraph(
        "Takım: <b>CryptoTEK</b> &nbsp;·&nbsp; TAKIM ID <b>909630</b><br/>"
        "TEKNOFEST 2026 — Blokzincir Yarışması<br/>"
        "Final: 30 Eylül – 4 Ekim 2026, Şanlıurfa",
        S["kapak_a"])]
    a += [PageBreak()]
    return a


def nasil_kullanilir():
    a = h1("Bu kitapçık nasıl kullanılır")
    a += p("Her soru üç katmanlı cevaplanır. Sahnede <b>yalnızca KISA "
           "CEVAP'ı</b> söyleyin; jüri üstüne giderse DERİNLEŞİRSE katmanını "
           "açın. TUZAK satırı, o soruda düşülebilecek hatayı gösterir.")
    a += tablo(["Katman", "Ne zaman", "Süre"], [
        ["KISA CEVAP", "Her zaman. İlk cümle bu olmalı.", "20–30 saniye"],
        ["DERİNLEŞİRSE", "Jüri \"nasıl\", \"neden\", \"göster\" derse.",
         "1–2 dakika"],
        ["TUZAK", "Söylemeden önce okuyun. Sahnede değil, hazırlıkta.", "—"],
    ], [32 * mm, ICERIK_GENISLIGI - 60 * mm, 28 * mm])

    a += notk(
        "<b>Bu kitapçık eskisinin yerine geçer.</b> Depodaki eski savunma "
        "kitapçığı düzeltilmiş sayıları öğretiyordu: %97,98 · 96-bit · "
        "12/12 test · 16 özellik. Ondan çalışan bir ekip, sahnede ekrandaki "
        "güncel rakamlarla <b>çelişir</b>. Eski PDF'i kullanmayın.")

    a += h2("Ezberlenmesi gereken yedi sayı")
    a += p("Bunlar en sık sorulacak sayılardır. Yanlış söylemek, ekranda "
           "doğrusu yazdığı için anında yakalanır.")
    a += tablo(["Ne", "Doğru değer", "Yanlış söylenirse"], [
        ["ML-DSA imza boyutları", "2.420 / 3.309 / <b>4.627</b> bayt",
         "4.595 diye ezberlemeyin — o eski ve yanlış."],
        ["STARK güvenliği", "<b>80 bit</b> (varsayımsal)",
         "96-bit demeyin. Kodda 80 yazıyor ve bir test README'yi okuyor."],
        ["Alan", "<b>f128</b> (128-bit)",
         "Goldilocks demeyin — o başka bir alan, biz kullanmıyoruz."],
        ["AI özellik sayısı", "<b>3</b> (İşlem sıklığı, IP sapması, Gas sapması)",
         "16 demeyin. Jüri calibration_metadata.json'u açarsa üç sütun görür."],
        ["Otomatik test", "<b>244</b>",
         "12/12 demeyin. O sayı bir dönem ONNX katmanına aitti."],
        ["Calldata tasarrufu", "50'lik partide <b>%96,6–98,4</b>",
         "Tek bir yüzde vermeyin; kademeye göre değişir."],
        ["Dal kapsamı", "<b>%82,55</b> toplam",
         "\"%100 kapsam\" demeyin."],
    ], [38 * mm, 50 * mm, ICERIK_GENISLIGI - 88 * mm])
    a += [PageBreak()]
    return a


def bolum_taktik():
    a = h1("1. Sunum taktikleri")

    a += h2("1.1 Açılış — ilk 30 saniye")
    a += p("Jüri gün boyu sunum dinliyor. İlk cümlede <b>ne yaptığınızı</b> "
           "söyleyin; tarihçe, motivasyon ve teşekkür sonra gelir.")
    a += notk(
        "<b>Açılış cümlesi:</b> «Bugünkü cüzdanlar tek bir güvenlik seviyesine "
        "sabitlenmiştir. Biz, tehdit görüldüğünde <b>kendini otomatik olarak "
        "kuantum dirençli bir imzaya yükselten</b> bir cüzdan yaptık — ve bu "
        "yükselmenin gerçekten olduğunu matematiksel bir kanıtla "
        "gösteriyoruz.»")
    a += p("Ardından tek nefeste sınırı da söyleyin. Bu, güvenilirliği en hızlı "
           "kuran hamledir: «Baştan söyleyelim: ürettiğimiz kanıt imzanın "
           "kendisini ispatlamıyor, imzanın türetildiği kafes ilişkisini "
           "ispatlıyor. Farkı birazdan ekranda göstereceğim.»")

    a += h2("1.2 Üç dakikalık akış")
    a += tablo(["Dakika", "Ne yapılır", "Hangi ekran"], [
        ["0:00–0:30", "Açılış cümlesi + sınırın peşin söylenmesi", "Boş konsol"],
        ["0:30–1:00", "Standart senaryo koşturulur: risk düşük, kanıt yok",
         "Nedensellik kartları"],
        ["1:00–1:45", "Drainer senaryosu: zırh 87'ye çıkar, kanıt üretilir",
         "Kartlar + yürütme izi"],
        ["1:45–2:15", "Kafes büyümesi ve kurcalama rozetine işaret",
         "Kafes ızgarası"],
        ["2:15–2:40", "Sınırları SÖZLÜ anlat — ekranda panel yok", "Kafes / kartlar"],
        ["2:40–3:00", "Determinizm: aynı girdi aynı kanıt", "Tekrar koşu"],
    ], [24 * mm, ICERIK_GENISLIGI - 62 * mm, 38 * mm])

    a += h2("1.3 Demo koreografisi — altı adım")
    a += p("Arayüzde Sunum Modu <b>yoktur</b> — kaldırıldı, konsol tek bir "
           "çalışma ekranı. Aşağıdaki altı adımı <b>siz</b> yürütürsünüz: "
           "ilgili senaryo düğmesine basın, <b>Enter</b> ile koşturun, "
           "karşılık gelen itirazı anlatın. Tema için <b>T</b>.")
    a += notk(
        "<b>Sınırlar ekranda değil.</b> «İddia Etmediklerimiz» paneli de "
        "arayüzden kaldırıldı. Altıncı adımda işaret edeceğiniz bir panel "
        "yok; sınırları <b>sözlü</b> söylemeniz gerekiyor. Bu kitapçığın "
        "4. bölümü tam olarak bunun için var.")
    a += tablo(["Adım", "Gösterilen", "Cevapladığı itiraz"], [
        ["1", "Standart senaryo — kanıt üretilmiyor",
         "«Her işlemde ağır kripto mu çalışıyor?» Hayır."],
        ["2", "Drainer — kafes 16'dan 56 hücreye çıkıyor",
         "«Zırh değişimi gerçek mi, yoksa etiket mi?»"],
        ["3", "Kurcalama testi — doğrulama kırmızıya dönüyor",
         "«İmza gerçekten çalışıyor mu?»"],
        ["4", "Rotasyon — ρ' değişince tüm hücreler değişiyor",
         "«Hareketli hedef savunması somut mu?»"],
        ["5", "Taban kuralı — zırh düşürülemiyor",
         "«Saldırgan zırhı indirebilir mi?»"],
        ["6", "Determinizm — aynı girdi, aynı çıktı",
         "«Bu sayılar uydurma olabilir mi?»"],
        ["+", "Sınırları sözlü say (ekranda panel yok)",
         "«Neyi iddia etmiyorsunuz?»"],
    ], [14 * mm, 62 * mm, ICERIK_GENISLIGI - 76 * mm])

    a += h2("1.4 En güçlü üç hamle")
    a += mad([
        "<b>Kurcalama rozeti.</b> «İmzanız çalışıyor mu?» sorusuna bir teste "
        "atıfla değil, <b>ekranda o anda yanan bir rozetle</b> cevap verin. "
        "Her koşuda mesaj bozulur ve doğrulayıcının reddettiği görülür.",
        "<b>Determinizm.</b> Jüriden bir girdi isteyin, koşun, sonra aynı "
        "girdiyle tekrar koşun. ρ', anahtar ve imza birebir aynı çıkar. "
        "«İsterseniz siz de kendi makinenizde üretebilirsiniz» deyin.",
        "<b>Kendi aleyhinize olan ölçüm.</b> Kart 4'teki «ECDSA'yı yeniyor mu "
        "→ hayır» satırını <b>siz gösterin</b>. Ölçüm yaptığınızın en güçlü "
        "kanıtı, kendi aleyhinize çıkan sayıyı da ekranda tutmanızdır.",
    ])

    a += h2("1.5 Demo çökerse — Plan B")
    a += p("Sunucu 18 saniyede açılıyor; sahneye çıkmadan <b>önce</b> açık "
           "olsun. Yine de kötü bir şey olursa:")
    a += tablo(["Sorun", "Ne yapılır"], [
        ["Sunucu yanıt vermiyor",
         "Arayüz kırmızı bant gösterir ve tüm alanlar «—» olur. "
         "<b>Bunu bir kusur değil, tasarım olarak sunun:</b> «Ekranda "
         "gördüğünüz her sayı canlı bir koşudan gelir; sunucu yoksa hiçbir "
         "sayı göstermeyiz. Eski sürümümüz burada örnek veriye düşüyordu, "
         "denetimde bunu kapattık.»"],
        ["Kanıt üretimi uzun sürüyor",
         "Yürütme izi şeridini gösterin; aşamalar sırayla yanar. Bekleme "
         "sırasında AIR kısıtlarını anlatın."],
        ["Projeksiyon/internet yok",
         "Arayüz <b>sıfır CDN</b> ile yazıldı; internetsiz tam çalışır. "
         "Bunu söyleyin, puan getirir."],
        ["Ekran çok karanlık/aydınlık",
         "<b>T</b> tuşu temayı değiştirir. Koyu varsayılan, salon aydınlıksa "
         "açık temaya geçin."],
    ], [38 * mm, ICERIK_GENISLIGI - 38 * mm])

    a += [PageBreak()]

    a += h2("1.6 Zor soru geldiğinde — dört adım")
    a += tablo(["Adım", "Ne yapılır", "Örnek"], [
        ["1. Kabul et",
         "Sorunun haklı olduğunu kabul edin. Savunmaya geçmeyin.",
         "«Haklısınız, bu bizim en çok yanlış anlaşılan noktamız.»"],
        ["2. Net cevap ver",
         "Tek cümlede doğruyu söyleyin.",
         "«Kanıt imza doğrulamasını ispatlamıyor.»"],
        ["3. Ne yaptığını söyle",
         "Yapmadığınızı söyledikten sonra yaptığınızı söyleyin.",
         "«İmza ayrıca ve gerçekten atılıyor; boyutları ekranda.»"],
        ["4. Kanıtı göster",
         "Ekrana ya da bir teste işaret edin.",
         "«Şu rozet her koşuda kurcalanmış mesajı reddediyor.»"],
    ], [26 * mm, 58 * mm, ICERIK_GENISLIGI - 84 * mm])

    a += h2("1.7 «Bilmiyorum» nasıl söylenir")
    a += p("Bilmediğiniz bir şey sorulduğunda uydurmak, sahnede yapılabilecek "
           "<b>en pahalı</b> hatadır. Tek bir yakalanma, doğru söylediğiniz "
           "her şeyi de şüpheli hâle getirir.")
    a += notk(
        "<b>Kalıp:</b> «Bunu ölçmedik, dolayısıyla bir sayı veremem. "
        "Ölçtüğümüz şey şu: … Eğer isterseniz ölçüm yöntemini anlatabilirim.» "
        "<br/><br/>Bu cümle sizi zayıf göstermez; <b>neyi bilip neyi "
        "bilmediğini ayırt edebilen</b> bir ekip gösterir. Jüri gün boyu "
        "bunun tersini dinliyor.")

    a += h2("1.8 Sahnede kullanılmayacak cümleler")
    a += p("Bunlar <b>doğru değildir</b>. Ekranda ve belgelerde tersi yazılı "
           "olduğu için söylenirse anında çelişki doğar.")
    a += tablo(["Söylemeyin", "Bunun yerine"], [
        ["«STARK, ML-DSA doğrulamasını ispatlıyor»",
         "«STARK, imzanın türetildiği kafes ilişkisini ispatlıyor; imza "
         "doğrulaması devre içinde değil.»"],
        ["«Kanıt zincirde doğrulanıyor»",
         "«Zincir kanıtın uzunluğunu kontrol ediyor ve guardian'ın ECDSA "
         "imzasını doğruluyor. STARK doğrulaması zincir dışında.»"],
        ["«Mainnet'e / testnete konuşlandırdık»",
         "«Konuşlandırma betiği hazır ve yerelde anvil'e karşı uçtan uca "
         "koştu; genel bir ağa göndermedik.»"],
        ["«ECDSA'dan daha az calldata»",
         "«ML-DSA imzası taşımaya kıyasla %98 tasarruf. ECDSA'ya kıyasla "
         "değil — 50 ECDSA imzası bizden küçük.»"],
        ["«Bağımsız denetimden geçti»",
         "«Slither ve solhint CI'da koşuyor; insan denetimi yapılmadı.»"],
        ["«%100 test kapsamı»",
         "«Satır kapsamı %96,10, dal kapsamı %82,55. %100 demiyoruz.»"],
        ["«Sertifikalı metrikler»",
         "«Kendi ölçümlerimiz; hiçbir kurum sertifikalandırmadı.»"],
        ["«12/12 test geçiyor»",
         "«244 otomatik test geçiyor.»"],
    ], [58 * mm, ICERIK_GENISLIGI - 58 * mm])
    a += [PageBreak()]
    return a


def bolum_klise():
    a = h1("2. Klişe sorular")
    a += p("Bunlar neredeyse kesin sorulur. Kısa, net ve ezberlenmiş "
           "cevaplanmalı; burada takılmak kötü bir izlenim bırakır.")

    a += soru("2.1", "Bu proje kısaca ne yapıyor?",
        "Bir kripto cüzdanının güvenlik seviyesini tehdide göre <b>canlı "
        "olarak değiştiriyor</b>. Yapay zekâ işlem davranışında anomali "
        "görürse, cüzdan kendini kuantum dirençli daha güçlü bir imzaya "
        "yükseltiyor ve bu geçişi matematiksel bir kanıtla belgeliyor.",
        "Üç kademe var: ML-DSA-44, -65 ve -87. İmza sırasıyla 2.420, 3.309 ve "
        "4.627 bayt. Kademeyi seçen kural tek bir fonksiyonda ve hem Rust hem "
        "Python aynı kuralı uyguluyor; 13 sınır vektörüyle bir eşitlik testi "
        "ikisinin aynı kararı verdiğini doğruluyor.",
        "«Kuantum güvenli cüzdan yaptık» deyip kesmeyin. Asıl yenilik "
        "kuantum imzayı kullanmak değil, <b>ne zaman kullanacağına karar "
        "vermek</b>.")

    a += soru("2.2", "Ne işe yarıyor? Gerçek bir problemi mi çözüyor?",
        "İki gerçek problemi birden. Birincisi <b>drainer saldırıları</b>: "
        "özel anahtar çalınınca klasik cüzdanda hiçbir ara katman yok, "
        "saldırgan her şeyi tek işlemle boşaltıyor. İkincisi <b>kuantum "
        "tehdidi</b>: bugünkü ECDSA imzaları Shor algoritmasıyla kırılabilir.",
        "Kuantum tehdidinin bugün başladığını vurgulayın: saldırgan bugün "
        "zincirdeki açık anahtarları kaydedip, kuantum bilgisayar geldiğinde "
        "geçmişe dönük çözebilir. Blokzincir verisi kalıcı ve herkese açık "
        "olduğu için buna «şimdi topla, sonra çöz» deniyor. Geçişin kuantum "
        "bilgisayar gelmeden önce yapılması gerekiyor.",
        None)

    a += soru("2.3", "Bunu daha önce yapan var mı? Sizin farkınız ne?",
        "Parçaların her biri ayrı ayrı var: ERC-4337 akıllı cüzdanlar var, "
        "post-kuantum imza kütüphaneleri var, ZK kanıt sistemleri var. "
        "Bizim yaptığımız, <b>güvenlik seviyesini çalışma anında bir yapay "
        "zekâ kararına bağlamak</b> ve bu kararı zincire taşımak.",
        "Somutlaştırın: Safe (eski adıyla Gnosis Safe) çoklu imza sunar ama "
        "imza şeması sabittir. Argent sosyal kurtarma sunar, yine sabit "
        "şema. zkSync ZK kullanır ama ölçeklenme için, adaptif güvenlik için "
        "değil. Bizde <b>üç katman birbirine bağlı</b>: AI kararı → kripto "
        "kademesi → zincir uygulaması.",
        "«Dünyada bir ilk» demeyin. Kanıtlayamazsınız ve jüri bunu sorar. "
        "Bunun yerine <b>birleşimin</b> yeni olduğunu söyleyin.")

    a += soru("2.4", "Neden bu projeyi seçtiniz?",
        "Post-kuantum geçişi bir «ne zaman» sorusu, «olur mu» sorusu değil. "
        "NIST standartları 2024'te yayımlandı. Ama herkesin yarın ağır "
        "imzalara geçmesi pratik değil — maliyet çok yüksek. Bu aradaki "
        "geçiş problemini çözmek istedik.",
        None, None)

    a += soru("2.5", "Bu gerçekten çalışıyor mu, yoksa bir maket mi?",
        "Çalışıyor ve <b>şu anda çalıştırabiliriz</b>. Ekrandaki her sayı "
        "canlı bir koşudan geliyor; sunucuya ulaşılamazsa arayüz hiçbir sayı "
        "göstermiyor, tüm alanlar «—» oluyor.",
        "Bunu bilerek böyle yaptık. Önceki sürümümüz API'ye ulaşamayınca "
        "sessizce örnek veriye düşüyordu — sunucu çökse bile ekran dolu "
        "görünüyordu. Denetimde bunu bulduk ve kapattık. Şimdi bir test, "
        "arayüzdeki 38 bağlı alanın her birinin API şemasında gerçekten var "
        "olduğunu her CI koşusunda doğruluyor.",
        None)

    a += soru("2.6", "Kaç kişisiniz, ne kadar sürdü?",
        "Takım CryptoTEK. Süreyi ve rol dağılımını ekip olarak siz "
        "cevaplayın — bu kitapçık teknik cevapları içerir.",
        None,
        "Süreyi abartmayın; jüri kod tabanının boyutuyla karşılaştırır.")

    a += soru("2.7", "Hangi teknolojileri kullandınız ve neden?",
        "Dört katman, dört dil — her biri kendi işinde en iyisi olduğu için. "
        "<b>Python</b> yapay zekâ için (ONNX, scikit-learn). <b>Rust</b> "
        "kriptografi ve kanıt üretimi için (fips204, Winterfell) — bellek "
        "güvenliği ve başarım. <b>Solidity</b> zincir tarafı için, çünkü "
        "EVM'in tek dili. Arayüz <b>sıfır bağımlılıkla</b> saf HTML/JS.",
        "Arayüzün sıfır CDN olması bilinçli: sahnede internet olmayabilir. "
        "Eski sürüm Tailwind ve Chart.js'i internetten çekiyordu; internetsiz "
        "arayüz çıplak kalırdı. Bir test bu kuralı zorluyor.",
        None)

    a += soru("2.8", "Ticarileşebilir mi? İş modeli var mı?",
        "Teknik olarak bir cüzdan altyapısı; ERC-4337 uyumlu olduğu için "
        "mevcut ekosisteme takılabilir. Ama bu bir <b>prototip</b>; üretim "
        "için bağımsız güvenlik denetimi ve guardian anahtarının HSM'e "
        "taşınması gerekir.",
        None,
        "Gelir modeli uydurmayın. «Henüz ticarileştirmeyi çalışmadık, "
        "odağımız teknik doğruluktu» demek daha güvenli ve dürüst.")

    a += soru("2.9", "Kodu siz mi yazdınız? Yapay zekâ mı yazdı?",
        "Kodu biz yazdık ve <b>her satırının neden orada olduğunu "
        "açıklayabiliriz</b>. Kod tabanında 244 otomatik test var ve her "
        "testin hangi bulguyu koruduğu belgeli.",
        "Bunu kanıtlamanın en iyi yolu bir tasarım kararını anlatmaktır. "
        "Örnek: oracle bayatladığında ne raporlayacağımıza karar verirken "
        "iki yönü de elediğimizi anlatın — fail-open saldırıyı ödüllendirir, "
        "fail-closed cüzdanı kilitler; biz «azami risk, panik kapalı» "
        "seçtik. Bu tür bir gerekçeyi ancak kodu düşünen biri anlatabilir.",
        "Savunmaya geçmeyin. <b>Bir karar anlatın</b> — en güçlü cevap budur.")
    a += [PageBreak()]
    return a


def bolum_teknik():
    a = h1("3. Teknik sorular")

    a += soru("3.1", "Yapay zekâ nasıl karar veriyor?",
        "Üç özellikli bir davranış vektörü alıyor — işlem sıklığı, IP sapması "
        "ve gas sapması — ve bir <b>Isolation Forest</b> modeliyle anomali "
        "skoru üretiyor. Skor, dinamik bir eşikle karşılaştırılıyor.",
        "Isolation Forest etiketsiz anomali tespiti için tasarlanmış. Mantığı "
        "ters çalışır: veriyi rastgele bölmelerle ayırır ve bir noktanın tek "
        "başına kalması için kaç bölme gerektiğine bakar. Sıra dışı noktalar "
        "birkaç bölmede yalnız kalır. Bizde 300 ağaç, contamination 0,03.",
        "Özellik sayısını <b>3</b> söyleyin. Belgelerimiz bir dönem 16 "
        "diyordu; düzelttik. Jüri model dosyasını açarsa üç sütun görür.")

    a += soru("3.2", "Neden sabit bir eşik değil de dinamik eşik?",
        "Sabit eşik iki yönde de hatalı: ağ sakinken çok geç uyarır, ağ "
        "çalkantılıyken sürekli yanlış alarm verir. Bizim eşiğimiz son 50 "
        "gözlemin <b>varyansından</b> hesaplanıyor.",
        "Formül: τ(t) = 60,0 + 0,15·σ²(gas) + 0,08·σ²(frekans), sonuç "
        "[55,0 – 90,0] aralığına sıkıştırılıyor. Varyans Bessel düzeltmesiyle "
        "(ddof=1) hesaplanıyor çünkü pencere tüm nüfusun değil bir örneklemin "
        "özeti. Pencerede 5'ten az gözlem varsa soğuk başlangıç değeri 75,0 "
        "kullanılıyor. Sıkıştırma şart: eşik ne tespit edilemez ne de her "
        "şeyi anomali sayan bir değere saplanabilir.",
        None)

    a += soru("3.3", "ML-DSA nedir, neden onu seçtiniz?",
        "NIST'in post-kuantum imza standardı, <b>FIPS 204</b>. Yarışmadaki "
        "adı CRYSTALS-Dilithium. Kafes tabanlı, yani güvenliği MLWE "
        "probleminin zorluğuna dayanıyor — Shor algoritması bunu çözmüyor.",
        "Üç kademesini de kullanıyoruz ve kademe çalışma anında seçiliyor. "
        "Gerçek bir kütüphane kullanıyoruz (Rust `fips204`); bir test her "
        "koşuda üretilen anahtar ve imza uzunluklarını FIPS 204 tablosuyla "
        "karşılaştırıyor, uyuşmazsa yapı kırılıyor.",
        "«Dilithium yazdık» demeyin — <b>standart kütüphaneyi kullanıyoruz</b>, "
        "kendi kriptomuzu yazmadık. Bu bir güç, zayıflık değil: kendi "
        "kriptosunu yazmak kötü bir işarettir.")

    a += soru("3.4", "Neden üç kademe? İkisi ya da beşi olamaz mıydı?",
        "Üç kademe ML-DSA standardının kendi kademeleri — NIST kategori 2, 3 "
        "ve 5. Biz uydurmadık, standardı takip ettik.",
        "Kademeler arası geçiş eşiğin ne kadar aşıldığına bağlı: aşım ≥ 15 "
        "puan ise ML-DSA-87, ≥ 5 puan ise -65, aksi hâlde -44. Ayrıca "
        "seçilen kademe her zaman <b>tabandan büyük ya da eşit</b> olur — "
        "tek yönlü tırmanma.",
        None)

    a += soru("3.5", "Neden ZK-STARK? SNARK daha küçük kanıt üretmiyor mu?",
        "İki sebep. Birincisi STARK <b>şeffaf</b>: güvenilir kurulum töreni "
        "gerektirmiyor. SNARK'lar genelde gerektirir ve o kurulumdaki gizli "
        "veri sızarsa sahte kanıt üretilebilir. İkincisi STARK'ın güvenliği "
        "yalnızca <b>hash fonksiyonlarına</b> dayanıyor, eliptik eğrilere "
        "değil — yani kuantum bilgisayar STARK'ı kırmıyor.",
        "İkinci nokta bizim için belirleyici: post-kuantum bir sistemde, "
        "kanıt sisteminin kendisi kuantum kırılabilir olsaydı tüm mimari "
        "anlamsız olurdu. SNARK'ların çoğu eliptik eğri eşleşmelerine dayanır "
        "ve Shor altında kırılır.",
        "SNARK'ı kötülemeyin; kanıt boyutunda SNARK daha iyidir. Takas "
        "<b>şeffaflık ve post-kuantum güvenliği</b>.")

    a += soru("3.6", "ERC-4337 neden gerekli?",
        "Normal bir Ethereum cüzdanı programlanamaz; kuralları zincir "
        "belirler ve yalnızca ECDSA kabul edilir. ERC-4337 cüzdanı bir "
        "<b>akıllı sözleşmeye</b> çeviriyor, böylece doğrulama mantığını biz "
        "yazabiliyoruz. Uyarlanabilir zırh ancak böyle mümkün.",
        "EntryPoint v0.7 kullanıyoruz ve CREATE2 sayesinde tüm ağlarda aynı "
        "adreste. Fork testlerimiz gerçek mainnet baytkoduna karşı koşuyor — "
        "mock değil, o adreste gerçekten kod olduğunu doğruluyoruz.",
        None)

    a += soru("3.7", "Paymaster nasıl kötüye kullanılmaz?",
        "Dört bağımsız kapı var: gönderen kontrolü, işlem başına azami "
        "maliyet, hesap başına dönem kotası ve toplam dönem bütçesi. Dördü de "
        "geçilmezse sponsorluk yok.",
        "Bu, denetimde bulduğumuz <b>gerçek bir fon kaybı açığıydı</b>: "
        "paymaster gönderene hiç bakmıyordu, yani herhangi bir saldırgan "
        "sözleşmesi gazını bize ödettirebiliyordu. Şimdi sömürü senaryosunun "
        "kendisi bir test olarak duruyor ve paymaster'ın satır kapsamı %100.",
        None)

    a += soru("3.8", "Zincirde gaz maliyeti ne kadar?",
        "<code>validateUserOp</code> için <b>26.449 – 147.510 gaz</b>, medyan "
        "74.155. Bu <code>forge test --gas-report</code> ile ölçüldü.",
        "Aralığın geniş olmasının sebebi, farklı kod yollarının farklı "
        "maliyeti olması: normal modda guardian imzası doğrulanmayabilir, "
        "panik modunda kanıt uzunluğu kontrolü ve ecrecover devreye girer.",
        "Zincir üstü ML-DSA doğrulaması için gaz sayısı <b>vermeyin</b>. "
        "Öyle bir doğrulayıcı yazmadık; tahmini bir sayı söylemek "
        "yapmadığımız bir işi ölçmüş gibi göstermek olur.")

    a += soru("3.9", "ρ' rotasyonu tam olarak ne sağlıyor?",
        "Her rotasyonda yeni bir 32 baytlık tohum türetiliyor ve kafes "
        "matrisinin <b>tamamı</b> yeniden genişliyor. ρ''nün tek bir biti "
        "değişirse 56 hücrenin hepsi değişiyor — bir test bunu 56/56 olarak "
        "doğruluyor.",
        "Buna Hareketli Hedef Savunması deniyor: saldırganın keşif yaptığı "
        "yüzey sürekli değişirse, sabit bir hedefi inceleme avantajı kaybolur.",
        "«Rotasyon kafes problemini zorlaştırıyor» <b>demeyin</b>. MLWE'nin "
        "zorluğu parametrelerden gelir, tohumdan değil. Rotasyonun sağladığı "
        "şey <b>ileri güvenliktir</b> — eski tohuma dair toplanan bilgi "
        "geçersiz olur. Bu ayrım arayüzdeki sınırlar panelinde de yazılı.")

    a += soru("3.10", "Kanıt üretimi ne kadar sürüyor?",
        "Kademeye ve makineye göre <b>0,4 – 21 ms</b> arasında. Her koşuda "
        "yeniden ölçülüp yanıta yazılıyor, ekranda canlı görünüyor.",
        "Yürütme izi şeridinde 11 aşamanın her birinin süresi ayrı ölçülüyor: "
        "ONNX çıkarımı, zırh kararı, ρ' türetimi, kafes genişletme, ML-DSA "
        "keygen/imzalama/doğrulama, kurcalama testi, iz tablosu, STARK "
        "prover, yerel doğrulama.",
        "Sabit bir sayı vermeyin. Belgelerimiz bir dönem «18.52 ms» diyordu; "
        "o tek bir makinedeki tek bir koşuydu ve sabitlenmişti.")
    a += [PageBreak()]
    return a


def bolum_zor():
    a = h1("4. Zor ve tuzak sorular")
    a += p("Bu bölümdeki sorular, ZK ya da kriptografi bilen bir jüri "
           "üyesinden gelir. Hepsinin ortak özelliği şudur: <b>cevabı "
           "biliyorsanız güçlü, bilmiyorsanız yıkıcıdır</b>. Hazırlığın "
           "ağırlığı buraya verilmeli.")

    a += soru("4.1", "STARK tam olarak neyi kanıtlıyor? İmza doğrulamasını mı?",
        "<b>Hayır, imza doğrulamasını devre içinde ispatlamıyoruz</b> ve bunu "
        "açıkça söylüyoruz. AIR üç kısıt uyguluyor: s1 ve s2'nin ilerleyişi "
        "ve <b>t = A·s1 + s2</b> MLWE ilişkisi. Bu, imzanın türetildiği kafes "
        "ilişkisi — imza doğrulama devresi değil.",
        "İmzalama ayrıca ve gerçekten yapılıyor: aynı ρ' tohumundan türetilen "
        "ξ ile <code>keygen_from_seed(ξ)</code> çağrılıyor, gerçek bir FIPS "
        "204 imzası üretiliyor ve doğrulanıyor. STARK ile imza arasındaki bağ "
        "<b>ortak tohum</b>. Tam ML-DSA doğrulamasını bir STARK devresine "
        "kodlamak aylar süren, araştırma düzeyinde bir iş — bunu yapmadığımızı "
        "söylemek, yapmış gibi görünmekten iyidir.",
        "Bu soruda en ufak bir belirsizlik bırakmayın. Kaçamak bir cevap "
        "verirseniz jüri geri kalan her şeyi sorgular. <b>Peşin söyleyin</b>, "
        "hatta sunumun açılışında söyleyin.")

    a += soru("4.2", "Burada «sıfır bilgi» olan ne? ρ' zaten ekranda.",
        "Haklısınız. Buradaki sıfır bilgi <b>nominaldir</b>. ρ' arayüzde "
        "yayınlanıyor, dolayısıyla s1, s2 ve A matrisi herkes tarafından "
        "yeniden hesaplanabilir. Kanıt <b>özlüdür</b> — doğrulaması tablonun "
        "tamamını görmekten ucuz — ama <b>hiçbir sır gizlemez</b>.",
        "Bu bilinçli bir takas: gizlilik yerine <b>tekrarlanabilirliği</b> "
        "seçtik. Jürinin aynı girdiyle aynı kanıtı kendi makinesinde "
        "üretebilmesi, bizim için gizlilikten daha değerliydi. ρ''yü gizleseydik "
        "determinizmi ve bağımsız doğrulanabilirliği kaybederdik.",
        "Bu maddeyi arayüzdeki sınırlar paneli <b>zaten yazıyor</b>. "
        "Panelde yazanla çelişen bir şey söylerseniz, arkanızdaki ekranla "
        "çelişirsiniz.")

    a += soru("4.3", "Kanıtı zincirde doğruluyor musunuz?",
        "<b>Hayır.</b> Sözleşme kanıtın <b>uzunluğunu</b> kontrol ediyor "
        "(en az 3.000 bayt) ve guardian'ın <b>ECDSA attestation imzasını</b> "
        "<code>ecrecover</code> ile doğruluyor. STARK doğrulaması zincir "
        "dışında.",
        "Bu bir eksiklik değil, mimarinin amacı: Solidity'de bir STARK "
        "doğrulayıcı çalıştırmak devasa gaz maliyeti demek — zaten kaçındığımız "
        "şey bu. Zincire giden şey 65 baytlık bir ECDSA imzası.",
        "«Zincir kanıtı doğruluyor» demeyin. Jüri sözleşmeyi açarsa "
        "<code>MIN_STARK_PROOF_BYTES = 3000</code> satırını görür ve bunun "
        "bir uzunluk kontrolü olduğunu anlar.")

    a += soru("4.4", "Testnete konuşlandırdınız mı? Canlı adres var mı?",
        "<b>Hayır, hiçbir ağa konuşlandırmadık.</b> Konuşlandırma betiği "
        "hazır, testlerle korunuyor ve yerelde <code>anvil</code>'e karşı "
        "uçtan uca koştu — ama genel bir ağa göndermedik.",
        "Betik adres basmakla yetinmiyor: konuşlandırmadan önce EntryPoint "
        "adresinde gerçekten baytkod olduğunu doğruluyor, sonra bağlantıları "
        "zincirden geri okuyor. Bu kontrol olmasa yanlış ağa konuşlandırma "
        "«başarılı» görünürdü — üç sözleşme iner, hiçbiri çalışmaz. "
        "Ayrıca fork testlerimiz gerçek mainnet EntryPoint baytkoduna karşı "
        "4/4 geçti.",
        "«Fork testi geçti» ile «testnette canlı» <b>aynı şey değil</b>. "
        "İkincisini söylemeyin.")

    a += soru("4.5", "Yapay zekâ yanılırsa ne olur?",
        "İki yönde de düşünüldü. <b>Yanlış pozitifte</b> (gereksiz alarm) "
        "kullanıcı daha ağır bir imza kullanır — yavaşlar ama güvendedir. "
        "<b>Yanlış negatifte</b> (kaçırılan saldırı) taban kademe devrede "
        "kalır; taban hiçbir zaman sıfır değildir.",
        "Kritik nokta: yanlış negatif <b>korumayı sıfırlamaz</b>. Sistem "
        "her zaman en az taban kademede çalışır ve zincir üstünde tek yönlü "
        "tırmanma var — bir kez yükselmiş zırh düşürülemez. Ayrıca dinamik "
        "eşik yanlış pozitif oranını düşürmek için var: ağ çalkantılıyken "
        "eşik otomatik yükseliyor.",
        "«AI hiç yanılmaz» demeyin. Yanılma senaryosunu <b>siz anlatın</b>.")

    a += soru("4.6", "Guardian anahtarı ele geçirilirse ne olur?",
        "Saldırgan sahte attestation üretebilir. Bu <b>bilinen bir sınır</b>: "
        "anahtar şu an süreç belleğinde tutuluyor ve sabit-zamanlı değil. "
        "Üretim için HSM ya da KMS'e taşınması gerekir.",
        "Hasarı sınırlayan iki şey var. Birincisi, zincir üstünde risk skoru "
        "<b>oracle ile guardian'ın büyüğü</b> alınıyor — guardian tek başına "
        "riski düşüremiyor. İkincisi tek yönlü tırmanma: ele geçirilen bir "
        "guardian zırhı <b>indiremez</b>. Ayrıca guardian anahtarı "
        "döndürülebilir ve rotasyon olayı indeksli, yani zincirden "
        "filtrelenebilir.",
        "Bu soruyu savuşturmaya çalışmayın. «Bu bir prototip sınırı, üretim "
        "için HSM şart» demek doğru cevaptır.")

    a += soru("4.7", "Oracle susarsa? Yani zincir dışı sistem çökerse?",
        "Oracle <b>bayat</b> sayılır ve azami risk raporlar — ama panik "
        "modunu <b>açmaz</b>. Yani zırh en güçlü kademeye çıkar, cüzdan "
        "kullanılabilir kalır.",
        "Bu, sözleşmenin tek gerçek tasarım kararı ve iki yönü de eledik. "
        "<b>Fail-open</b> (bayatken risk=0) olsaydı, updater'ı susturabilen "
        "saldırgan zırhı en zayıf kademeye düşürürdü — saldırıyı ödüllendirirdi. "
        "<b>Fail-closed</b> (bayatken panik=true) olsaydı her işlem kanıt "
        "isterdi; zincir dışı yığın çöktüğü için bayatlamıştır, o kanıtı kimse "
        "üretemez ve <b>cüzdan kilitlenirdi</b>. Üçüncü yolu seçtik. "
        "Ayrıca yeni konuşlandırılan oracle <b>bilerek bayat başlar</b>: "
        "henüz hiçbir şey ölçmemiştir, risk 0 raporlamak en tehlikeli yönde "
        "yalan olurdu.",
        None)

    a += soru("4.8", "Eğitim veriniz gerçek zincir verisi mi?",
        "<b>Hayır, kontrollü sentetik veri.</b> Canlı zincirden toplanmadı ve "
        "bunu gizlemiyoruz — README'de, belgelerde ve arayüzdeki sınırlar "
        "panelinde yazılı.",
        "Gerçek veriyle eğitim ayrı bir iş: etiketli saldırı verisi toplamak "
        "günler sürer ve yarışma kapsamını aşar. Ama mimari buna bağlı değil — "
        "model ONNX formatında, değiştirilmesi tek dosya değişikliği.",
        "Sentetik olduğunu <b>siz söyleyin</b>. Jüri sorup öğrenirse çok "
        "daha kötü.")

    a += [PageBreak()]

    a += soru("4.9", "%98 tasarruf neye göre? Bu sayı nereden geliyor?",
        "50 işlemlik bir partide, <b>işlem başına ML-DSA imzası taşımaya "
        "kıyasla</b>. 50 × 4.627 = 231.350 bayt yerine tek bir kanıt, "
        "yaklaşık 4.000 bayt.",
        "Formül ve tüm girdileri her koşuda <code>proof_payload.json</code> "
        "içindeki <code>calldata</code> alanına yazılıyor — yani sayıyı bizim "
        "sunumumuza güvenmeden doğrulayabilirsiniz. Kademeye göre oran "
        "%96,6 ile %98,4 arasında değişiyor.",
        "«ECDSA'dan %98 tasarruf» <b>demeyin</b>. Taban ML-DSA imzasıdır.")

    a += soru("4.10", "ECDSA'dan daha mı verimlisiniz?",
        "<b>Hayır, calldata boyutunda ECDSA bizi yeniyor.</b> 50 ECDSA imzası "
        "3.250 bayt — tek bir STARK kanıtımızdan küçük. Arayüzde "
        "<code>beats_ecdsa → hayır</code> diye yazıyor ve bunu gizlemiyoruz.",
        "Takas edilen şey boyut değil, <b>post-kuantum güvenliği</b>. "
        "ECDSA'nın Shor algoritması altında sağlayamadığı tek şey bu. "
        "Bizim iddiamız «daha ucuz» değil, «kuantum sonrasında da geçerli».",
        "Bu soruyu bir zayıflık gibi karşılamayın. <b>Kendi aleyhinize olan "
        "ölçümü ekranda tutmanız</b>, ölçüm yaptığınızın en güçlü kanıtı.")

    a += soru("4.11", "Kuantum bilgisayar daha yok. Bu erken değil mi?",
        "Tehdit gelecekte, ama <b>hazırlık bugün</b> yapılmalı. Saldırgan "
        "bugün zincirdeki açık anahtarları kaydedip, kuantum bilgisayar "
        "geldiğinde geçmişe dönük çözebilir.",
        "Buna «şimdi topla, sonra çöz» deniyor ve blokzincir için özellikle "
        "geçerli, çünkü zincir verisi <b>kalıcı ve herkese açık</b>. "
        "Bir bankada eski trafiği kaydetmek zordur; blokzincirde ücretsizdir. "
        "NIST standartları 2024'te yayımlandı; geçiş penceresi şimdi açık.",
        None)

    a += soru("4.12", "Madem ML-DSA-87 var, neden hep onu kullanmıyorsunuz?",
        "Maliyet. ML-DSA-87 imzası 4.627 bayt — ECDSA'nın ~71 katı. "
        "Blokzincirde her bayt para. İşlem başına bunu taşımak cüzdanı "
        "pratikte kullanılamaz hâle getirir.",
        "Projenin bütün fikri bu zaten: <b>her zaman değil, gerektiğinde</b>. "
        "Kullanıcıların çoğu, çoğu zaman saldırı altında değil. Tehdit "
        "görüldüğünde ağır kademeye çıkıyoruz ve bir kez çıkınca "
        "düşmüyoruz — tek yönlü tırmanma.",
        None)

    a += soru("4.13", "80 bit güvenlik yeterli mi? Standart 128 değil mi?",
        "<b>Haklısınız, 80 bit üretim için düşüktür.</b> Bu bir prototip "
        "ayarı ve bilerek temkinli tutuldu; artırmak tek bir sabiti "
        "değiştirmek demek.",
        "Sayı tek bir yerden geliyor: <code>air.rs::STARK_SECURITY_BITS</code>. "
        "FRI sorgu sayısıyla (28) birlikte ayarlanması gerekiyor — ikisi "
        "bağımsız değil. Kanıt boyutu ve üretim süresi artar. "
        "Ayrıca <b>README'yi okuyan bir test</b>, belgedeki sayı ile koddaki "
        "sabitin ayrışmasını engelliyor.",
        "«96 bit» <b>demeyin</b>. Belgelerimiz bir dönem öyle diyordu, kod 80 "
        "diyordu; bu tutarsızlığı denetimde bulduk ve düzelttik.")

    a += soru("4.14", "Testlerinizi çalıştırabilir miyim?",
        "<b>Evet, buyurun.</b> Komutlar belgede yazılı ve hepsi tek satır.",
        "Rust için <code>cargo test</code> (61 test), Solidity için "
        "<code>forge test</code> (146 test, 4'ü fork). Python tarafında üç "
        "takım: katman eşitliği (9), attestation kriptosu (18), API-arayüz "
        "sözleşmesi (9). Toplam <b>244</b>. Katman eşitliği testi özellikle "
        "ilginç: gerçek Rust ikilisini çalıştırıp Python'un kararıyla "
        "karşılaştırıyor.",
        "Bu soruya <b>«isterseniz gösterelim»</b> deyip geçiştirmeyin; "
        "gerçekten çalıştırın. Çalıştıramayacağınız bir iddiayı hiç "
        "yapmayın.")

    a += soru("4.15", "Kendi kodunuzda hata buldunuz mu?",
        "Evet, <b>21 bulgu</b> ve sonradan çıkan yedi hata daha. Üçü canlı "
        "ağda sistemi tamamen çalışmaz hâle getirecek cinstendi.",
        "En çarpıcısı: ön-fonlama <code>gas: 2300</code> ile yapılıyordu. "
        "Gerçek EntryPoint'in <code>receive()</code>'ı depolamaya yazar "
        "(~20.000+ gaz); 2.300 gaz yetmez, yani çağrı <b>her zaman</b> "
        "başarısız olur ve <code>require</code> yüzünden <b>her işlem revert "
        "ederdi</b>. Cüzdan canlı ağda hiçbir işlemi tamamlayamazdı. "
        "Bir diğeri: arayüzde gösterilen iz, STARK'ın kanıtladığı iz değildi. "
        "Hepsi için geri gelmeyi engelleyen testler yazdık.",
        "Bu soruya <b>bol bol</b> cevap verin. Hata bulduğunu anlatabilen "
        "ekip, hiç hata bulmamış olduğunu iddia edenden çok daha güvenilir "
        "görünür.")
    a += [PageBreak()]
    return a


def bolum_rakip():
    a = h1("5. Rakip karşılaştırma ve konumlandırma")
    a += p("«Farkınız ne?» sorusunun teknik hâli. Rakipleri küçümsemeyin; "
           "her biri <b>farklı bir problemi</b> çözüyor.")
    a += tablo(["Çözüm", "Ne yapıyor", "Bizden farkı"], [
        ["Safe (Gnosis Safe)",
         "Çoklu imza cüzdanı. Birden fazla onay gerektirir.",
         "İmza şeması <b>sabit</b> ve ECDSA. Kuantum dirençli değil, "
         "uyarlanabilir değil."],
        ["Argent",
         "Sosyal kurtarma: anahtar kaybolursa güvenilir kişiler kurtarır.",
         "Kurtarma <b>sonrası</b> çözüm. Biz saldırıyı <b>anında</b> "
         "yavaşlatmaya çalışıyoruz. İmza şeması yine sabit."],
        ["zkSync / StarkNet",
         "ZK kanıtları <b>ölçeklenme</b> için kullanıyor.",
         "Aynı teknoloji, farklı amaç. Bizde ZK güvenlik kademesini "
         "belgelemek için."],
        ["Donanım cüzdanlar",
         "Özel anahtarı fiziksel olarak izole eder.",
         "Anahtar çalınmasına karşı güçlü, ama <b>kuantuma karşı çaresiz</b> "
         "— yine ECDSA imzalıyor."],
        ["PQ kütüphaneleri (liboqs vb.)",
         "Post-kuantum imza şemalarını sağlar.",
         "Biz de böyle bir kütüphane kullanıyoruz (fips204). Katkımız "
         "kütüphane değil, <b>ne zaman hangi kademenin kullanılacağına karar "
         "veren katman</b>."],
    ], [32 * mm, 56 * mm, ICERIK_GENISLIGI - 88 * mm])

    a += notk(
        "<b>Konumlandırma cümlesi:</b> «Kimsenin yapmadığı bir kripto "
        "yazmadık — NIST'in standardını kullanıyoruz. Bizim kattığımız şey, "
        "<b>güvenlik seviyesini çalışma anında bir tehdit değerlendirmesine "
        "bağlamak</b> ve bu bağı zincire taşımak.»")

    a += h2("5.1 Rakip sorusu tuzağı")
    a += p("Jüri bazen «X şirketi bunu zaten yapıyor» der. Panik yapmayın; "
           "üç adımda cevaplayın:")
    a += mad([
        "<b>Sorun:</b> «Tam olarak hangi kısmını yapıyorlar?» — çoğu zaman "
        "parçalardan birini yapıyordur, birleşimi değil.",
        "<b>Kabul edin:</b> ortak yanı varsa söyleyin. «Evet, o katmanda "
        "benzer.»",
        "<b>Farkı söyleyin:</b> «Bizim eklediğimiz, kademenin çalışma anında "
        "seçilmesi ve bunun kanıtlanması.»",
    ])
    a += [PageBreak()]
    return a


def bolum_surec():
    a = h1("6. Süreç ve ekip soruları")

    a += soru("6.1", "En çok nerede zorlandınız?",
        "Katmanların <b>birbirini tutmasında</b>. Dört ayrı dil var ve "
        "başlangıçta aynı kararı farklı veriyorlardı — Rust sabit bir eşik "
        "kullanıyordu, Python dinamik eşik. İkisi farklı kademe seçebiliyordu.",
        "Çözüm tek bir kuralı iki dilde uygulamak ve bunu bir <b>eşitlik "
        "testiyle</b> sabitlemek oldu: test gerçek Rust ikilisini çalıştırıp "
        "Python'un kararıyla 13 sınır vektöründe karşılaştırıyor.",
        None)

    a += soru("6.2", "Neyi farklı yapardınız?",
        "Testleri <b>daha erken</b> yazardık. Solidity tarafında bir dönem "
        "hiç test yoktu ve orada gerçek bir fon kaybı açığı duruyordu — "
        "paymaster gönderene bakmıyordu.",
        "Bir de belgeleri koddan üretirdik. Belgelerimiz kaynak kodu "
        "alıntılıyordu ama alıntılar donmuştu; bir fonksiyon değişince belge "
        "sessizce yanlış oluyordu. Şimdi 23 kod bloğu kaynaktan üretiliyor ve "
        "bir CI kapısı sapmayı yakalıyor.",
        None)

    a += soru("6.3", "Projede en çok neyle gurur duyuyorsunuz?",
        "Ekranda <b>kendi aleyhimize olan ölçümün</b> durması. "
        "«ECDSA'yı yeniyor mu → hayır» satırını silebilirdik; bırakmayı "
        "seçtik. Aynı şekilde sınırlarımız README'de bir tablo hâlinde duruyor "
        "ve bir test, maddelerden biri silinirse yapıyı kırıyor.",
        "Teknik olarak ise kurcalama testinin <b>canlı hatta</b> koşması. "
        "«İmzamız çalışıyor» iddiası bir teste atıf değil, her koşuda ekranda "
        "yanan bir rozet.",
        None)

    a += soru("6.4", "Bu projeyi sürdürecek misiniz?",
        "Yarışma sonrası yol haritası net: testnete konuşlandırma, guardian "
        "anahtarının HSM'e taşınması, bağımsız güvenlik denetimi ve dal "
        "kapsamının yükseltilmesi.",
        None,
        "Süre ve kaynak taahhüdü vermeyin.")

    a += soru("6.5", "Kodunuz açık mı?",
        "Evet, Apache 2.0 lisansıyla GitHub'da. CI hattı da açık — altı iş, "
        "her koşu görülebilir.",
        None, None)
    a += [PageBreak()]
    return a


def hizli_kart():
    a = h1("7. Hızlı referans kartı")
    a += p("Bu sayfa sahnede önünüzde dursun. Tek bakışta gereken her sayı "
           "burada.")

    a += h2("Sayılar")
    a += tablo(["Ne", "Değer"], [
        ["ML-DSA imza", "2.420 / 3.309 / <b>4.627</b> bayt"],
        ["ML-DSA açık anahtar", "1.312 / 1.952 / 2.592 bayt"],
        ["Kafes (k×ℓ)", "4×4=16 / 6×5=30 / <b>8×7=56</b> hücre"],
        ["STARK güvenliği", "<b>80 bit</b> varsayımsal · f128 alan · 28 FRI sorgusu"],
        ["Kanıt boyutu", "3.617 – 4.321 bayt (ölçülür)"],
        ["Prover süresi", "0,4 – 21 ms (ölçülür)"],
        ["ONNX çıkarımı", "8,8 – 10,1 ms (5 koşu ortalaması)"],
        ["Boru hattı", "<b>11 aşama</b>, her süre ölçülmüş"],
        ["AI modeli", "Isolation Forest · 300 ağaç · contamination 0,03 · <b>3 özellik</b>"],
        ["Dinamik eşik", "τ = 60 + 0,15σ²(gas) + 0,08σ²(frekans), [55–90]"],
        ["Kademe eşikleri", "aşım ≥15 → 87 · ≥5 → 65 · aksi → 44"],
        ["validateUserOp gazı", "26.449 – 147.510 (medyan 74.155)"],
        ["Calldata tasarrufu", "50'lik partide %96,6 – 98,4 (ML-DSA tabanına göre)"],
        ["50 ECDSA imzası", "3.250 bayt — <b>bizden küçük</b>"],
        ["Testler", "Rust 61 · Solidity 146 · Python 37 = <b>244</b>"],
        ["Kapsam", "satır %96,10 · dal <b>%82,55</b> · fonksiyon %95,31"],
        ["CI", "6 iş"],
        ["EntryPoint", "v0.7 · 0x0000000071727De22E5E9d8BAf0edAc6f37da032"],
    ], [42 * mm, ICERIK_GENISLIGI - 42 * mm])

    a += h2("Üç cümlelik savunma")
    a += notk(
        "<b>1.</b> «Kanıtımız imza doğrulamasını devre içinde ispatlamıyor; "
        "imzanın türetildiği kafes ilişkisini ispatlıyor. İmza ayrıca ve "
        "gerçekten atılıyor.»<br/><br/>"
        "<b>2.</b> «Buradaki sıfır bilgi nominal — ρ' yayınlanıyor, sır "
        "gizlemiyoruz. Gizlilik yerine tekrarlanabilirliği seçtik.»<br/><br/>"
        "<b>3.</b> «Hiçbir ağa konuşlandırmadık. Betik hazır ve yerelde uçtan "
        "uca koştu; 'canlı' demiyoruz.»")

    a += h2("Asla söylenmeyecek yedi cümle")
    a += mad([
        "«STARK, ML-DSA doğrulamasını ispatlıyor»",
        "«Kanıt zincirde doğrulanıyor»",
        "«Testnete/mainnete konuşlandırdık»",
        "«ECDSA'dan daha az calldata»",
        "«Bağımsız denetimden geçti»",
        "«%100 test kapsamı» / «12/12 test»",
        "«Sertifikalı metrikler» / «96-bit güvenlik» / «16 özellik»",
    ])
    return a


def main():
    hikaye = []
    hikaye += kapak()
    hikaye += nasil_kullanilir()
    hikaye += bolum_taktik()
    hikaye += bolum_klise()
    hikaye += bolum_teknik()
    hikaye += bolum_zor()
    hikaye += bolum_rakip()
    hikaye += bolum_surec()
    hikaye += hizli_kart()

    belge = SimpleDocTemplate(
        str(CIKTI),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title="Q-ADAPTIVE — Jüri Kitapçığı: Sunum Taktikleri ve Soru-Cevap",
        author="CryptoTEK · TAKIM ID 909630",
        subject="TEKNOFEST 2026 Blokzincir Yarışması",
    )
    belge.build(hikaye, canvasmaker=Sayfa)
    print(f"  ✓ {CIKTI.name} — {CIKTI.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
