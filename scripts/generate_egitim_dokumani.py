#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q-ADAPTIVE — Sıfırdan Öğretici Belge (PDF üreteci).

Bu belge, projeyi hiç bilmeyen birine baştan sona anlatmak için yazıldı.
Blokzincirin ne olduğundan başlayıp sistemin en ince ayrıntısına kadar
gidiyor; her kavram kullanılmadan ÖNCE tanımlanıyor.

Belgedeki her sayı koddan okunmuştur. Ölçülen değerler "ölçüldü" diye,
ölçülmeyenler "ölçülmedi" diye yazılır — projenin denetiminde çıkan en
büyük sorun tam olarak bu ayrımın yapılmamasıydı.

Kullanım:
    python3 scripts/generate_egitim_dokumani.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus import Paragraph

from pdf_ortak import (
    ICERIK_GENISLIGI, KOK, MAVI, S, Sayfa,
    bosluk, gorsel, h1, h2, h3, kod, mad, notk, p, tablo,
)

CIKTI = KOK / "Q_ADAPTIVE_Ogretici_Belge.pdf"
Sayfa.USTBILGI = "Q-ADAPTIVE (AI Guardian) — Sıfırdan Öğretici Belge"

# ═════════════════════════════════════════════════════════════════════════════
# İÇERİK
# ═════════════════════════════════════════════════════════════════════════════

def kapak():
    a = []
    a += [Spacer(1, 42 * mm)]
    a += [Paragraph("Q-ADAPTIVE", S["kapak_b"])]
    a += [Paragraph("AI Guardian", S["kapak_b"])]
    a += [Spacer(1, 8 * mm)]
    a += [Paragraph(
        "Yapay Zekâ Güdümlü, Kuantum Dirençli<br/>Uyarlanabilir Akıllı Cüzdan",
        S["kapak_a"])]
    a += [Spacer(1, 16 * mm)]
    a += [Table([[""]], colWidths=[70 * mm], rowHeights=[2],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), MAVI)]),
                hAlign="CENTER")]
    a += [Spacer(1, 16 * mm)]
    a += [Paragraph(
        "<b>SIFIRDAN ÖĞRETİCİ BELGE</b><br/>"
        "Hiç bilmeyen bir okuyucu için, kavram kavram, adım adım",
        S["kapak_a"])]
    a += [Spacer(1, 30 * mm)]
    a += [Paragraph(
        "Takım: <b>CryptoTEK</b> &nbsp;·&nbsp; TAKIM ID <b>909630</b><br/>"
        "Başvuru ID 2603893<br/><br/>"
        "TEKNOFEST 2026 — Blokzincir Yarışması<br/>"
        "Final: 30 Eylül – 4 Ekim 2026, Şanlıurfa",
        S["kapak_a"])]
    a += [PageBreak()]
    return a


def icindekiler():
    a = h1("İçindekiler")
    a += p("Belge, hiçbir ön bilgi varsaymayan bir sırayla ilerler. Her kavram, "
           "kullanılmadan önce tanımlanır. Bir bölümü atlarsanız sonraki bölüm "
           "eksik kalabilir.")
    a += tablo(
        ["#", "Bölüm", "Ne öğreneceksiniz"],
        [
            ["0", "Bu belge nedir",
             "Belgenin amacı, kimin için yazıldığı ve sayıların nasıl doğrulandığı"],
            ["1", "Proje nedir, neden var",
             "Hangi yarışma, hangi problem, tek cümlelik değer önermesi"],
            ["2", "Çözülen problem",
             "Kuantum tehdidi ve cüzdan güvenliğinin bugünkü açıkları"],
            ["3", "Temel kavramlar",
             "Blokzincirden ZK-STARK'a kadar 11 kavram, sıfırdan"],
            ["4", "Mimari: dört katman",
             "Parçaların birbirine nasıl bağlandığı"],
            ["5", "Katmanlar ayrıntılı",
             "AI, ZK, sözleşme ve arayüz katmanlarının iç işleyişi"],
            ["6", "Uçtan uca bir koşu",
             "Bir işlemin 11 aşamadan nasıl geçtiği, ölçülen sürelerle"],
            ["7", "Arayüz",
             "Ekran görüntüleriyle, her bölümün ne gösterdiği"],
            ["8", "Neler yapabiliyor",
             "Kanıtlanmış yetenekler ve bunları koruyan testler"],
            ["9", "Neler yapamıyor",
             "Eksikler, mimari sınırlar ve her birinin sebebi"],
            ["10", "Test ve doğrulama",
             "244 otomatik test, kapsam ölçümleri, CI hattı"],
            ["11", "Denetim hikâyesi",
             "Ne bulundu, nasıl düzeltildi, hangi ders çıktı"],
            ["12", "Çalıştırma kılavuzu",
             "Sıfırdan kurulum ve doğrulama komutları"],
            ["13", "Sözlük",
             "Belgede geçen tüm terimlerin kısa tanımları"],
        ],
        [14 * mm, 52 * mm, ICERIK_GENISLIGI - 66 * mm])
    a += [PageBreak()]
    return a


def bolum0():
    a = h1("0. Bu belge nedir")
    a += p("Bu belge, Q-ADAPTIVE adlı projeyi <b>hiç bilmeyen</b> birine baştan "
           "sona anlatmak için yazıldı. Blokzincirin ne olduğunu bilmiyorsanız "
           "bile takip edebilirsiniz: her kavram, ilk kullanıldığı yerde "
           "tanımlanır ve neden gerektiği açıklanır.")

    a += h2("Kimin için")
    a += mad([
        "<b>Jüri üyeleri</b> — sistemin ne yaptığını ve neyi yapmadığını "
        "tek kaynaktan görmek isteyenler.",
        "<b>Ekip üyeleri</b> — kendi katmanı dışındaki parçaları anlamak "
        "isteyenler.",
        "<b>Projeyi devralacak kişiler</b> — kodun neden böyle yazıldığını "
        "merak edenler.",
        "<b>Meraklı okuyucular</b> — post-kuantum kriptografi ve sıfır bilgi "
        "kanıtlarının pratikte nasıl birleştiğini görmek isteyenler.",
    ])

    a += h2("Belgedeki sayılar nasıl doğrulandı")
    a += p("Bu projenin denetiminde çıkan <b>en büyük sorun</b> şuydu: belgeler "
           "\"ML-DSA kullanıyoruz\" diyordu ama kodda tek satır ML-DSA yoktu. "
           "Aynı hataya düşmemek için bu belgede üç kural uygulanır:")
    a += mad([
        "Her sayı <b>koddan okunmuştur</b> ya da bir komut çalıştırılarak "
        "<b>ölçülmüştür</b>. Tahmin yok.",
        "Ölçülmemiş bir şey <b>\"ölçülmedi\"</b> diye yazılır. Makul bir tahmin "
        "yazmak, ölçmüş gibi görünmek demektir.",
        "Yapılmamış bir şey <b>\"yapılmadı\"</b> diye yazılır. \"İleride "
        "yapılacak\" ifadesi, mevcut durumun yerine değil, ardına konur.",
    ])
    a += notk(
        "<b>Donanıma bağlı değerler.</b> Süreler (çıkarım, kanıt üretimi) ve "
        "kuyruk kapasitesi gibi değerler çalıştığınız makineye göre değişir. "
        "Bu belgede aralık verilir ve hangi makinede ölçüldüğü söylenir. "
        "Sabit bir sayı görürseniz, o sayı gerçekten sabittir (örneğin bir "
        "imzanın bayt uzunluğu).")
    a += [PageBreak()]
    return a


def bolum1():
    a = h1("1. Proje nedir, neden var")

    a += h2("Tek cümlelik özet")
    a += notk(
        "<b>Q-ADAPTIVE</b>, bir kripto cüzdanının güvenlik seviyesini "
        "<b>tehdide göre canlı olarak değiştiren</b> bir sistemdir: yapay zekâ "
        "işlem davranışında anomali görürse, cüzdan kendini otomatik olarak "
        "daha güçlü, <b>kuantum bilgisayarlara dirençli</b> bir imza şemasına "
        "yükseltir ve bu geçişin gerçekten olduğunu matematiksel bir kanıtla "
        "belgeler.")

    a += h2("Hangi yarışma")
    a += tablo(["Alan", "Değer"], [
        ["Yarışma", "TEKNOFEST 2026 — Blokzincir Yarışması"],
        ["Takım", "CryptoTEK"],
        ["Takım ID", "909630"],
        ["Başvuru ID", "2603893"],
        ["Final", "30 Eylül – 4 Ekim 2026, Şanlıurfa"],
        ["Proje adı", "Q-ADAPTIVE (AI Guardian)"],
        ["Lisans", "Apache 2.0"],
    ], [40 * mm, ICERIK_GENISLIGI - 40 * mm])

    a += h2("Neden \"uyarlanabilir\"")
    a += p("Bugünkü cüzdanlar <b>statiktir</b>. Bir cüzdan hangi imza şemasını "
           "kullanıyorsa, ömrü boyunca onu kullanır. Tehdit ortamı değişse de "
           "cüzdan değişmez. Bu, güvenliği tek bir noktada dondurur.")
    a += p("Q-ADAPTIVE bunun yerine <b>üç kademeli</b> bir zırh kullanır ve "
           "kademeyi çalışma anında seçer. Tehdit yoksa en hafif kademe, tehdit "
           "varsa en ağır kademe. Bu yaklaşımın literatürdeki adı "
           "<b>Hareketli Hedef Savunması</b>dır (Moving Target Defense) ve "
           "3. bölümde ayrıntılı anlatılacaktır.")

    a += h2("Projenin üç iddiası")
    a += tablo(["İddia", "Nasıl karşılanıyor"], [
        ["Tehdidi görebilir",
         "Zincir dışı bir yapay zekâ modeli işlem davranışını puanlar ve "
         "dinamik bir eşikle karşılaştırır."],
        ["Kendini güçlendirebilir",
         "Puan eşiği aşarsa imza şeması NIST FIPS 204 ML-DSA'nın daha yüksek "
         "kademesine çıkar; imza 2.420 → 3.309 → 4.627 bayta büyür."],
        ["Bunu kanıtlayabilir",
         "Geçişe eşlik eden kafes ilişkisi için bir ZK-STARK kanıtı üretilir "
         "ve zincire bir guardian imzasıyla çapalanır."],
    ], [45 * mm, ICERIK_GENISLIGI - 45 * mm])

    a += notk(
        "<b>Üçüncü iddianın sınırı şimdiden söylensin:</b> üretilen kanıt, "
        "ML-DSA imzasının geçerliliğini <b>kanıtlamaz</b>. Neyi kanıtladığı "
        "3.8 ve 9. bölümlerde tam olarak açıklanır. Bu ayrım projenin en çok "
        "yanlış anlaşılan noktasıdır ve bilerek en başta belirtilmektedir.")
    a += [PageBreak()]
    return a


def bolum2():
    a = h1("2. Çözülmeye çalışılan problem")

    a += h2("2.1 Bugünkü cüzdanların iki açığı")
    a += p("Bir kripto cüzdanı, özünde bir <b>anahtar çiftidir</b>. Özel anahtar "
           "sizde durur ve işlemleri imzalar; açık anahtardan türetilen adres "
           "herkese açıktır. Bu yapının iki temel zayıflığı var:")

    a += h3("Açık 1 — Tek noktadan kırılma")
    a += p("Özel anahtar çalınırsa <b>her şey biter</b>. Saldırgan cüzdandaki "
           "tüm varlıkları tek bir işlemle boşaltabilir. Buna sektörde "
           "<b>\"drainer\" saldırısı</b> denir. Klasik cüzdanda bunu durduracak "
           "bir ara katman yoktur: imza geçerliyse işlem geçerlidir.")

    a += h3("Açık 2 — Kuantum tehdidi")
    a += p("Bugün neredeyse tüm blokzincirler <b>ECDSA</b> adlı imza şemasını "
           "kullanır. ECDSA'nın güvenliği, eliptik eğri üzerinde ayrık logaritma "
           "probleminin zorluğuna dayanır. Yeterince büyük bir kuantum "
           "bilgisayar, <b>Shor algoritması</b> ile bu problemi verimli biçimde "
           "çözer — yani açık anahtardan özel anahtarı hesaplayabilir.")
    a += notk(
        "<b>\"Şimdi topla, sonra çöz\" saldırısı.</b> Tehdit gelecekte değil, "
        "bugün başlıyor. Bir saldırgan bugün zincirdeki açık anahtarları "
        "kaydedebilir ve kuantum bilgisayar geldiğinde geçmişe dönük olarak "
        "özel anahtarları çözebilir. Blokzincir verisi kalıcı ve herkese açık "
        "olduğu için, bugün yapılan bir işlem gelecekte kırılabilir. "
        "Bu yüzden geçişin kuantum bilgisayar gelmeden <b>önce</b> yapılması "
        "gerekir.")

    a += h2("2.2 Neden basitçe \"hep en güçlü imzayı kullan\" demiyoruz")
    a += p("Akla gelen ilk çözüm şudur: kuantum dirençli imzayı her zaman "
           "kullan. Sorun maliyettir.")
    a += tablo(["İmza şeması", "İmza boyutu", "Anlamı"], [
        ["ECDSA (secp256k1)", "65 bayt", "Bugünkü standart, kuantuma karşı kırık"],
        ["ML-DSA-44", "2.420 bayt", "ECDSA'nın ~37 katı"],
        ["ML-DSA-65", "3.309 bayt", "ECDSA'nın ~51 katı"],
        ["ML-DSA-87", "4.627 bayt", "ECDSA'nın ~71 katı"],
    ], [42 * mm, 30 * mm, ICERIK_GENISLIGI - 72 * mm])
    a += p("Blokzincirde <b>her bayt para demektir</b> (bu maliyete \"gaz\" "
           "denir; 3.1'de anlatılacak). İşlem başına 4.627 bayt taşımak, "
           "cüzdanı pratikte kullanılamaz hâle getirir. Üstelik kullanıcıların "
           "büyük çoğunluğu, çoğu zaman saldırı altında değildir.")

    a += h2("2.3 Q-ADAPTIVE'in cevabı")
    a += p("Fikir şu: <b>her zaman değil, gerektiğinde</b>. Sistem normal "
           "koşullarda hafif kademede çalışır; davranışsal bir anomali "
           "görüldüğünde ağır kademeye yükselir. Ve bu yükselmenin gerçekten "
           "olduğunu bağımsız olarak doğrulanabilir bir kanıtla belgeler.")
    a += p("Bunu yapabilmek için dört şey gerekir ve projenin dört katmanı "
           "tam olarak bunlara karşılık gelir:")
    a += mad([
        "Tehdidi <b>görecek</b> bir şey → yapay zekâ katmanı",
        "Zırhı <b>değiştirecek</b> bir şey → post-kuantum kripto katmanı",
        "Değişimi <b>kanıtlayacak</b> bir şey → ZK-STARK katmanı",
        "Kararı <b>uygulayacak</b> bir şey → akıllı sözleşme katmanı",
    ])
    a += [PageBreak()]
    return a


def bolum3():
    a = h1("3. Temel kavramlar — sıfırdan")
    a += p("Bu bölüm, sistemin anlaşılması için gereken <b>her</b> kavramı "
           "tanımlar. Bir kavramı biliyorsanız o başlığı atlayabilirsiniz; "
           "bilmiyorsanız sonraki bölümler anlamsız gelecektir.")

    # ── 3.1
    a += h2("3.1 Blokzincir, işlem ve gaz")
    a += p("<b>Blokzincir</b>, binlerce bilgisayarın aynı kaydın kopyasını "
           "tuttuğu, merkezî bir otoritesi olmayan bir veritabanıdır. Kayıt "
           "yalnızca eklenebilir; geçmiş değiştirilemez.")
    a += p("<b>İşlem (transaction)</b>, bu kayda yazılan bir komuttur: "
           "\"şu adresten bu adrese şu kadar gönder\" gibi. Her işlem, "
           "gönderenin özel anahtarıyla <b>imzalanır</b>; ağdaki herkes "
           "imzayı açık anahtarla doğrulayabilir.")
    a += p("<b>EVM (Ethereum Sanal Makinesi)</b>, zincir üstünde program "
           "çalıştıran sanal bilgisayardır. Bu programlara <b>akıllı sözleşme</b> "
           "denir ve genelde <b>Solidity</b> dilinde yazılır.")
    a += p("<b>Gaz (gas)</b>, EVM'de yapılan her işin ücretidir. Toplama gibi "
           "basit bir işlem ucuz, veri depolamak pahalıdır. Kullanıcı bu ücreti "
           "ağın yerel parasıyla (Ethereum'da ETH) öder. Zincire yazılan veriye "
           "<b>calldata</b> denir ve <b>bayt başına ücretlendirilir</b> — bu "
           "yüzden imza boyutu doğrudan maliyettir.")

    # ── 3.2
    a += h2("3.2 Dijital imza ve ECDSA")
    a += p("Dijital imza üç işlemden oluşur:")
    a += mad([
        "<b>Anahtar üretimi:</b> bir özel anahtar ve ona karşılık gelen bir "
        "açık anahtar üretilir.",
        "<b>İmzalama:</b> özel anahtar + mesaj → imza.",
        "<b>Doğrulama:</b> açık anahtar + mesaj + imza → doğru/yanlış.",
    ])
    a += p("<b>ECDSA</b>, eliptik eğri matematiğine dayanan yaygın bir imza "
           "şemasıdır. Ethereum'da <code>ecrecover</code> adlı yerleşik bir "
           "fonksiyon, imzadan imzalayanın adresini geri çıkarır ve bu çok "
           "ucuzdur (~3.000 gaz). Projede guardian imzaları hâlâ ECDSA ile "
           "doğrulanır — nedeni 5.3'te açıklanacaktır.")

    # ── 3.3
    a += h2("3.3 Kuantum tehdidi ve Shor algoritması")
    a += p("Klasik bir bilgisayar, eliptik eğri ayrık logaritma problemini "
           "çözmek için astronomik sürelere ihtiyaç duyar. <b>Shor "
           "algoritması</b> ise yeterince büyük bir kuantum bilgisayarda bu "
           "problemi <b>polinom zamanda</b> çözer. Pratik sonucu: ECDSA'nın "
           "açık anahtarından özel anahtar hesaplanabilir hâle gelir.")
    a += notk(
        "<b>Yaygın bir karışıklık.</b> Kuantum bilgisayarlar her şeyi kırmaz. "
        "Hash fonksiyonlarına (SHA-256, BLAKE3) karşı yalnızca <b>Grover "
        "algoritması</b> vardır ve o da güvenliği yarıya indirir — 256 bit "
        "hash, kuantum karşısında 128 bit gibi davranır ki bu hâlâ güvenlidir. "
        "Asıl kırılan, ECDSA ve RSA gibi <b>açık anahtarlı</b> şemalardır.")

    # ── 3.4
    a += h2("3.4 Post-kuantum kriptografi ve kafesler")
    a += p("<b>Post-kuantum kriptografi</b>, kuantum bilgisayarların da "
           "çözemediği matematiksel problemlere dayanan şemaların genel adıdır. "
           "En olgun aile <b>kafes tabanlı</b> (lattice-based) olanlardır.")
    a += p("<b>Kafes nedir:</b> Bir kafes, uzayda düzenli aralıklarla dizilmiş "
           "noktalar kümesidir — sonsuza uzanan üç boyutlu bir ızgara gibi "
           "düşünün, ama boyut sayısı yüzlerce. Bu yapıda \"verilen bir "
           "noktaya en yakın kafes noktasını bul\" gibi problemler, boyut "
           "arttıkça hem klasik hem kuantum bilgisayarlar için çok zorlaşır.")
    a += p("<b>MLWE (Module Learning With Errors):</b> Projenin dayandığı "
           "problem budur. Sezgisi şöyledir: bir A matrisi ve küçük katsayılı "
           "gizli bir s1 vektörü alın, çarpın, üstüne küçük bir <b>hata</b> "
           "vektörü s2 ekleyin:")
    a += kod("t = A · s1 + s2   (mod q)")
    a += p("A ve t herkese açıktır; s1 ve s2 gizlidir. Hata terimi olmasaydı "
           "s1'i lineer cebirle bulmak kolay olurdu. Hata, problemi kafeste "
           "\"en yakın noktayı bulma\" problemine çevirir ve bilinen hiçbir "
           "kuantum algoritması bunu verimli çözmez.")
    a += p("Projede <b>q = 8.380.417</b> kullanılır; bu, ML-DSA standardının "
           "kendi asal modülüdür.")

    # ── 3.5
    a += h2("3.5 ML-DSA (FIPS 204) — kullanılan post-kuantum imza")
    a += p("<b>NIST</b> (ABD Ulusal Standartlar ve Teknoloji Enstitüsü) yıllar "
           "süren bir yarışma sonunda post-kuantum standartlarını seçti. "
           "İmza standardı <b>FIPS 204</b> olarak yayımlandı ve şemanın adı "
           "<b>ML-DSA</b>'dır (Module-Lattice-Based Digital Signature "
           "Algorithm). Yarışmadaki adı <b>CRYSTALS-Dilithium</b> olduğu için "
           "iki isim birlikte kullanılır.")
    a += p("ML-DSA'nın üç güvenlik kademesi vardır. Projede üçü de kullanılır "
           "ve kademe çalışma anında seçilir:")
    a += tablo(
        ["Kademe", "NIST kategorisi", "Kafes (k×ℓ)", "İmza", "Açık anahtar", "Gizli anahtar"],
        [
            ["ML-DSA-44", "2", "4×4 = 16 hücre", "2.420 B", "1.312 B", "2.560 B"],
            ["ML-DSA-65", "3", "6×5 = 30 hücre", "3.309 B", "1.952 B", "4.032 B"],
            ["ML-DSA-87", "5 (en yüksek)", "8×7 = 56 hücre", "4.627 B", "2.592 B", "4.896 B"],
        ])
    a += notk(
        "Bu boyutlar <b>tahmin değildir</b>. Proje `fips204` adlı Rust "
        "kütüphanesini kullanır ve bir test her koşuda üretilen anahtar ve "
        "imzaların uzunluklarını FIPS 204 tablosuyla karşılaştırır. "
        "Uyuşmazsa yapı kırılır.")

    a += [PageBreak()]
    return a


def bolum3b():
    a = h2("3.6 Hash fonksiyonları, BLAKE3, SHAKE-128 ve reddetme örneklemesi")
    a += p("<b>Hash fonksiyonu</b>, herhangi uzunlukta bir girdiyi sabit "
           "uzunlukta bir çıktıya çeviren tek yönlü bir fonksiyondur. İyi bir "
           "hash üç özelliği sağlar: çıktıdan girdiye dönülemez, aynı çıktıyı "
           "veren iki girdi bulunamaz ve girdinin <b>tek bir biti</b> değişince "
           "çıktı tamamen değişir (çığ etkisi).")
    a += p("<b>BLAKE3</b>, projede genel amaçlı hash olarak kullanılır: ρ' "
           "tohumunun türetilmesi ve kısa tohumların üretilmesi.")
    a += p("<b>SHAKE-128</b> bir <b>XOF</b>'tur (extendable-output function): "
           "sabit uzunlukta değil, <b>istediğiniz kadar</b> bayt üretebilen bir "
           "hash. Kafes matrisini doldurmak için tam olarak bu gerekir, çünkü "
           "56 hücrenin her biri için taze rastgelelik lazımdır.")

    a += h3("Reddetme örneklemesi — neden gerekli")
    a += p("Matrisin her hücresi <b>[0, q)</b> aralığında olmalı, yani "
           "0 ile 8.380.416 arasında. SHAKE'den 3 baytlık (24 bit) bloklar "
           "okunur; 24 bitin aralığı [0, 16.777.216)'dır.")
    a += p("Ham değeri basitçe <code>% q</code> ile daraltmak <b>yanlış</b> "
           "olurdu. 16.777.216, 8.380.417'nin tam katı değildir; artan kısım "
           "yüzünden küçük değerler diğerlerinin <b>iki katı</b> olasılıkla "
           "çıkardı. Bu, matrisin dağılımını bozar ve güvenliği zayıflatır.")
    a += p("Çözüm <b>reddetme örneklemesi</b>dir: okunan değer q'dan küçükse "
           "kabul edilir, değilse <b>atılır</b> ve bir sonraki blok okunur. "
           "Kabul olasılığı q / 2²⁴ ≈ <b>%49,9</b>'dur. FIPS 204 §7.3 "
           "(ExpandA) tam olarak bu yöntemi kullanır.")
    a += notk(
        "<b>Denetimde çıkan bulgu.</b> Bu kod eskiden Rust'ın "
        "<code>DefaultHasher</code>'ını (SipHash) kullanıyordu. İki sorun "
        "vardı: SipHash <b>kriptografik değildir</b>, ve çıktısının Rust "
        "sürümleri arasında aynı kalacağı <b>garanti edilmez</b> — yani aynı "
        "girdi başka bir derlemede başka bir matris üretebilirdi. Kanıtlar "
        "yeniden üretilebilir olmazdı. Şimdi SHAKE-128 + reddetme kullanılıyor.")

    # ── 3.7
    a += h2("3.7 Sıfır bilgi kanıtları ve ZK-STARK")
    a += p("<b>Sıfır bilgi kanıtı</b>, bir iddianın doğru olduğunu, iddianın "
           "kendisi dışında <b>hiçbir bilgi sızdırmadan</b> kanıtlama "
           "yöntemidir. Klasik örnek: bir labirentin içinden geçtiğinizi, "
           "hangi yoldan geçtiğinizi söylemeden kanıtlamak.")
    a += p("<b>STARK</b> (Scalable Transparent ARgument of Knowledge) bir "
           "kanıt sistemidir. İki özelliği önemlidir:")
    a += mad([
        "<b>Şeffaf:</b> güvenilir bir kurulum töreni gerektirmez. (SNARK'lar "
        "genelde gerektirir; o kurulumdaki gizli veri sızarsa sahte kanıt "
        "üretilebilir.)",
        "<b>Post-kuantum varsayımlara dayanır:</b> güvenliği yalnızca hash "
        "fonksiyonlarına dayanır; eliptik eğrilere değil. Yani kuantum "
        "bilgisayar STARK'ı kırmaz.",
    ])

    a += h3("STARK nasıl çalışır — üç adım")
    a += p("<b>1) İz tablosu (execution trace).</b> Kanıtlanacak hesaplama bir "
           "tabloya yazılır: her satır bir adım, her sütun bir değişken. "
           "Projede tablo <b>8 satır × 4 sütun</b>'dur; sütunlar "
           "A_commit, s1, s2 ve t'dir.")
    a += p("<b>2) AIR (Algebraic Intermediate Representation).</b> Tablonun "
           "\"doğru\" sayılması için sağlaması gereken kurallar cebirsel "
           "denklemler olarak yazılır. Projede üç kısıt vardır:")
    a += kod(
        "result[0] = next[1] - (current[1] + 2)        # s1 her adımda +2\n"
        "result[1] = next[2] - (current[2] + 3)        # s2 her adımda +3\n"
        "result[2] = next[3] - (next[0] * next[1] + next[2])\n"
        "                                              # t = A·s1 + s2 (MLWE)")
    a += p("Her üç ifade de <b>sıfır</b> olmalıdır. Kanıtlayıcı, tablonun bu "
           "denklemleri her satırda sağladığını kanıtlar.")
    a += p("<b>3) FRI (Fast Reed-Solomon IOP of Proximity).</b> Tablo "
           "polinomlara çevrilir ve FRI, bu polinomların gerçekten düşük "
           "dereceli olduğunu — yani tablonun uydurulmadığını — rastgele "
           "noktalarda örnekleyerek doğrular. Doğrulayıcı tablonun tamamını "
           "görmez; birkaç noktaya bakarak ikna olur. Kanıtın <b>özlü</b> "
           "olmasının sebebi budur.")

    a += h3("Projenin STARK parametreleri")
    a += tablo(["Parametre", "Değer", "Anlamı"], [
        ["Alan", "f128", "128-bit asal alan (Winterfell kütüphanesi)"],
        ["Güvenlik", "80 bit (varsayımsal)",
         "Sahte kanıt üretmek ~2⁸⁰ iş gerektirir. \"Varsayımsal\" (conjectured), "
         "kanıtlanmış değil tahmin edilen sınır demektir."],
        ["FRI sorgu sayısı", "28", "Doğrulayıcının baktığı rastgele nokta sayısı"],
        ["Şişirme çarpanı", "8", "Polinomun kaç kat fazla noktada değerlendirildiği"],
        ["Öğütme çarpanı", "16", "Kanıtlayıcıya eklenen ek iş yükü (grinding)"],
        ["İz uzunluğu", "8 satır", "2'nin kuvveti olmak zorunda"],
    ], [32 * mm, 30 * mm, ICERIK_GENISLIGI - 62 * mm])
    a += notk(
        "<b>80 bit, 96 değil.</b> Belgeler bir dönem \"96-bit\" diyordu; kodda "
        "80 yazıyordu. Artık tek bir sabitten (<code>air.rs::STARK_SECURITY_BITS</code>) "
        "okunuyor ve <b>README'yi okuyan bir test</b> ikisinin aynı kaldığını "
        "her koşuda doğruluyor.")

    a += [PageBreak()]

    # ── 3.8
    a += h2("3.8 Bu projede STARK tam olarak neyi kanıtlıyor")
    a += p("Bu, projenin <b>en kritik</b> ve en çok yanlış anlaşılan noktası. "
           "Açıkça yazalım.")
    a += tablo(["Kanıtlanan", "Kanıtlanmayan"], [
        ["ρ' tohumundan türetilmiş bir A matrisi ve s1, s2 dizileri için "
         "<b>t = A·s1 + s2</b> MLWE ilişkisinin 8 adım boyunca sağlandığı.",
         "<b>ML-DSA imzasının geçerli olduğu.</b> İmza doğrulaması devre "
         "içinde ispatlanmıyor."],
        ["s1 ve s2'nin tanımlı artış kuralına (+2, +3) uyduğu.",
         "Gizli bir anahtarın bilindiği. Ortada gizlenen bir sır yok."],
    ])
    a += p("İmzalama <b>ayrıca ve gerçekten</b> yapılır: aynı ρ' tohumundan "
           "türetilen ξ ile <code>ML-DSA::keygen_from_seed(ξ)</code> çağrılır, "
           "gerçek bir imza üretilir ve doğrulanır. Ama STARK ile imza "
           "arasındaki bağ <b>ortak tohumdur</b>, devre içi bir ispat değil.")
    a += notk(
        "<b>\"Sıfır bilgi\" burada nominaldir.</b> ρ' tohumu arayüzde ve "
        "payload'da <b>yayınlanır</b>. ρ' bilinince s1, s2 ve A matrisi "
        "herkes tarafından yeniden hesaplanabilir. Yani kanıt <b>özlüdür</b> "
        "(succinct — doğrulaması tablonun tamamını görmekten ucuz) ama "
        "<b>hiçbir sır gizlemez</b>. Bu bilinçli bir takastır: gizlilik "
        "yerine <b>tekrarlanabilirlik</b> seçildi, çünkü jürinin aynı girdiyle "
        "aynı kanıtı kendi makinesinde üretebilmesi daha değerli görüldü.")

    a += [PageBreak()]
    return a


def bolum3c():
    a = h2("3.9 ERC-4337 — hesap soyutlama")
    a += p("Normal bir Ethereum cüzdanı (EOA, Externally Owned Account) "
           "<b>programlanamaz</b>: kuralları zincirin kendisi belirler ve "
           "yalnızca ECDSA imzası kabul edilir. Farklı bir imza şeması ya da "
           "\"şu koşulda işlemi beklet\" gibi bir kural ekleyemezsiniz.")
    a += p("<b>ERC-4337</b> bu kısıtı kaldırır: cüzdanı bir <b>akıllı sözleşme</b> "
           "yapar. Böylece doğrulama mantığını siz yazarsınız. Projenin var "
           "olabilmesinin sebebi budur — uyarlanabilir zırh ancak "
           "programlanabilir bir cüzdanda mümkündür.")

    a += h3("Bileşenler")
    a += tablo(["Terim", "Ne demek"], [
        ["UserOperation",
         "Kullanıcının niyetini taşıyan yapı. Normal bir işlem değil; "
         "ayrı bir havuzda (mempool) dolaşır."],
        ["EntryPoint",
         "Tüm ERC-4337 akışını yöneten tekil, denetlenmiş sözleşme. "
         "v0.7 sürümü CREATE2 ile <b>tüm ağlarda aynı adrestedir</b>: "
         "0x0000000071727De22E5E9d8BAf0edAc6f37da032"],
        ["Bundler",
         "UserOperation'ları toplayıp EntryPoint'e gönderen aktör. "
         "Karşılığında ücret alır."],
        ["validateUserOp",
         "Cüzdan sözleşmesinin doğrulama fonksiyonu. EntryPoint burayı çağırır; "
         "sonuç başarılıysa işlem yürütülür."],
        ["Paymaster",
         "İşlemin gazını kullanıcı yerine ödeyen sözleşme. Kullanıcının hiç "
         "ETH'i olmadan işlem yapabilmesini sağlar."],
        ["ERC-7562",
         "Doğrulama sırasında nelerin yasak olduğunu belirleyen kural seti. "
         "En önemlisi: doğrulama sırasında depolamaya yazmak yasaktır."],
    ], [35 * mm, ICERIK_GENISLIGI - 35 * mm])

    a += h2("3.10 Yapay zekâ katmanı — Isolation Forest ve ONNX")
    a += p("<b>Anomali tespiti</b>, \"normalden sapan\" örnekleri bulma "
           "işidir. Burada zorluk şudur: elinizde etiketli saldırı verisi "
           "yoktur. Yeni bir drainer saldırısının nasıl görüneceğini önceden "
           "bilemezsiniz.")
    a += p("<b>Isolation Forest</b> tam bu durum için tasarlanmıştır. Mantığı "
           "ters yönden çalışır: veriyi rastgele bölmelerle parçalara ayırır ve "
           "bir noktanın <b>tek başına kalması için kaç bölme gerektiğine</b> "
           "bakar. Sıra dışı noktalar birkaç bölmede yalnız kalır; sıradan "
           "noktalar kalabalığın içinde gizlenir ve ayrılmaları uzun sürer.")
    a += tablo(["Parametre", "Değer"], [
        ["Ağaç sayısı", "300"],
        ["Contamination", "0,03 (eğitim verisinin %3'ü anomali varsayılır)"],
        ["Özellik sayısı", "<b>3</b> — Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi"],
        ["Çalışma zamanı", "ONNX Runtime (CPU)"],
        ["Ölçülen çıkarım süresi", "8,8–10,1 ms (5 koşu ortalaması, tek makine)"],
    ], [50 * mm, ICERIK_GENISLIGI - 50 * mm])
    a += notk(
        "<b>Üç özellik, on altı değil.</b> Belgeler bir dönem \"16 özellikli "
        "vektör\" diyordu; kodda üç sütun var. Düzeltildi. Eğitim verisi de "
        "<b>kontrollü sentetiktir</b> — canlı zincirden toplanmamıştır. Bu "
        "gizlenmiyor, kapsam sınırı olarak yazılıyor.")

    a += h3("ONNX neden var")
    a += p("<b>ONNX</b> (Open Neural Network Exchange), eğitilmiş bir modeli "
           "eğitildiği kütüphaneden bağımsız, taşınabilir bir biçimde saklama "
           "standardıdır. Model scikit-learn ile eğitilir, ONNX'e dışa "
           "aktarılır ve çalışma anında ONNX Runtime ile koşturulur. Bir test, "
           "ONNX çıktısının orijinal scikit-learn çıktısıyla aynı kaldığını "
           "doğrular — dönüşümde bir şey bozulursa yakalanır.")

    a += h3("Dinamik eşik τ(t) — sabit eşik neden yetmez")
    a += p("Sabit bir eşik (\"skor 90'ı geçerse alarm\") iki yönde de hatalıdır: "
           "ağ sakinken çok geç uyarır, ağ çalkantılıyken sürekli yanlış alarm "
           "verir. Projede eşik <b>kayan pencere varyansından</b> hesaplanır:")
    a += kod("τ(t) = 60,0 + 0,15 · σ²(gas_sapması) + 0,08 · σ²(işlem_sıklığı)\n"
             "τ(t) = clamp(τ(t), 55,0, 90,0)")
    a += mad([
        "Pencere son <b>50</b> gözlemi tutar.",
        "Varyans <b>Bessel düzeltmesiyle</b> (ddof=1) hesaplanır — pencere, "
        "tüm nüfusun değil bir örneklemin özetidir.",
        "Pencerede <b>5</b>'ten az gözlem varsa soğuk başlangıç değeri "
        "<b>75,0</b> kullanılır.",
        "Sonuç <b>[55,0 – 90,0]</b> aralığına sıkıştırılır; eşik ne tespit "
        "edilemez ne de her şeyi anomali sayan bir değere saplanır.",
    ])

    a += h2("3.11 Hareketli Hedef Savunması (MTD)")
    a += p("<b>Moving Target Defense</b>, saldırganın keşif yaptığı yüzeyi "
           "sürekli değiştirme fikridir. Sabit bir hedefi incelemek için zamanı "
           "olan saldırgan avantajlıdır; hedef değişirse bu avantaj kaybolur.")
    a += p("Projede bu, <b>ρ' rotasyonu</b> ile yapılır. Her rotasyonda yeni "
           "bir ρ' tohumu türetilir ve A matrisinin <b>tamamı</b> yeniden "
           "genişletilir. ρ''nün tek bir biti değişirse 56 hücrenin tamamı "
           "değişir — bir test bunu 56/56 olarak doğrular.")
    a += notk(
        "<b>Rotasyon kafes probleminin zorluğunu artırmaz.</b> MLWE'nin "
        "zorluğu parametrelerden gelir, tohumdan değil. Rotasyonun sağladığı "
        "şey <b>ileri güvenliktir</b> (forward secrecy): saldırganın eski "
        "tohuma dair topladığı bilgi geçersiz olur. Bu ayrım arayüzdeki "
        "sınırlar panelinde de yazılıdır.")

    a += [PageBreak()]
    return a


def bolum4():
    a = h1("4. Mimari — dört katman")
    a += p("Sistem dört katmandan oluşur. Her katman ayrı bir dilde yazılmıştır "
           "ve bu tesadüf değildir: her dil, kendi katmanının gerektirdiği işte "
           "en iyisidir.")
    a += tablo(
        ["Katman", "Dil / Teknoloji", "Sorumluluğu", "Neden bu dil"],
        [
            ["1. Yapay zekâ", "Python · ONNX · FastAPI",
             "Davranışı puanlar, dinamik eşiği hesaplar, kararı verir",
             "Makine öğrenmesi ekosisteminin tamamı burada"],
            ["2. Kriptografi", "Rust · fips204",
             "Gerçek ML-DSA anahtar üretimi, imzalama, doğrulama",
             "Bellek güvenliği + yüksek başarım; kripto için standart"],
            ["3. Kanıt", "Rust · Winterfell",
             "İz tablosu, AIR kısıtları, STARK kanıtı",
             "Winterfell olgun bir Rust STARK kütüphanesi"],
            ["4. Zincir", "Solidity · ERC-4337",
             "Kararı uygular, guardian imzasını doğrular, gazı sponsorlar",
             "EVM'in tek dili"],
        ],
        [26 * mm, 32 * mm, ICERIK_GENISLIGI - 58 - 38 * mm, 38 * mm])

    a += h2("4.1 Veri akışı")
    a += kod(
        "  Kullanıcı / senaryo\n"
        "        │  3 özellik: İşlem sıklığı, IP sapması, Gas sapması\n"
        "        ▼\n"
        "  [1] Python API  ──── ONNX Isolation Forest ──► risk skoru\n"
        "        │                dinamik eşik τ(t) ile karşılaştırılır\n"
        "        │  risk < τ  →  NORMAL: kanıt üretilmez, taban kademe\n"
        "        │  risk ≥ τ  →  PANİK: aşıma göre kademe seçilir\n"
        "        ▼  (6 argüman: risk, tau, taban, userOpHash, epoch, run-id)\n"
        "  [2] Rust ikilisi\n"
        "        ├─ hashing::derive_rho_prime   → ρ' (32 bayt, BLAKE3)\n"
        "        ├─ trace::from_rho_prime       → kafes + kısa tohumlar\n"
        "        ├─ pqc::sign_and_verify        → GERÇEK ML-DSA imzası\n"
        "        └─ [3] Winterfell              → STARK kanıtı\n"
        "        ▼  proof_payload.json\n"
        "  [1] Python API  ──── ölçümleri yanıta taşır ──► arayüz\n"
        "        ▼  guardian ECDSA attestation imzası\n"
        "  [4] Akıllı sözleşme (ERC-4337)\n"
        "        ├─ kanıt uzunluğu kontrolü (≥ 3000 bayt)\n"
        "        ├─ guardian imzası ecrecover ile doğrulanır\n"
        "        └─ zırh kademesi güncellenir (yalnızca YUKARI)")

    a += h2("4.2 Kararı veren tek kural")
    a += p("Zırh kademesini seçen mantık <b>tek bir fonksiyondadır</b> ve hem "
           "Rust hem Python aynı kuralı uygular:")
    a += kod(
        "risk < τ            → taban kademe, kanıt YOK, durum = NORMAL\n"
        "risk ≥ τ            → aşım = risk − τ\n"
        "     aşım ≥ 15.0    → ML-DSA-87\n"
        "     aşım ≥  5.0    → ML-DSA-65\n"
        "     aksi           → ML-DSA-44\n"
        "risk veya τ = NaN   → ML-DSA-87 + panik (sessizce normale düşmez)\n"
        "\n"
        "her durumda: seçilen = max(seçilen, taban)   ← tek yönlü tırmanma")
    a += notk(
        "<b>Neden iki dilde aynı kural var.</b> Eskiden Rust sabit bir 90,0 "
        "eşiği kullanıyordu, Python ise dinamik τ(t). İkisi farklı karar "
        "verebiliyordu. Şimdi tek kural var ve <b>13 sınır vektörüyle</b> bir "
        "eşitlik testi, Python'un kararıyla gerçek Rust ikilisinin kararının "
        "aynı olduğunu doğruluyor.")

    a += h2("4.3 Tek yönlü tırmanma")
    a += p("Zırh kademesi <b>asla düşürülemez</b> — ne zincir dışında ne de "
           "zincir üstünde. Bir saldırgan EntryPoint üzerinden çağrı yapıp "
           "kademeyi ML-DSA-87'den 44'e indirmeye çalışırsa reddedilir.")
    a += p("Bu, iki <b>fuzz testiyle</b> korunur: rastgele üretilmiş binlerce "
           "girdi dizisi için kademenin monoton arttığı ve asla tabanın "
           "altına inmediği sınanır.")
    a += [PageBreak()]
    return a


def bolum5():
    a = h1("5. Katmanlar ayrıntılı")

    a += h2("5.1 Yapay zekâ katmanı (Python)")
    a += h3("Sorumlulukları")
    a += mad([
        "3 özellikli vektörü alıp ONNX modeliyle ham anomali skoru üretmek.",
        "Skoru Platt ölçekleme ile [0, 100] aralığına kalibre etmek.",
        "Kayan pencere varyansından τ(t) hesaplamak.",
        "Karar panikse Rust ikilisini <b>altı argümanla</b> çağırmak.",
        "Üretilen payload'ı okuyup arayüze taşımak.",
        "Guardian attestation imzasını üretmek.",
    ])
    a += h3("DoS koruması — kuyruk kapasitesi")
    a += p("STARK kanıtı üretmek CPU yoğun bir iştir. Saldırgan arka arkaya "
           "yüksek riskli istek göndererek sunucuyu kilitleyebilir. Bu yüzden "
           "kanıt üretimi sınırlı bir <code>asyncio.Queue</code>'ya alınır; "
           "kuyruk dolarsa HTTP 429 döner.")
    a += notk(
        "<b>Kapasite sabit değildir ve bu önemlidir.</b> Eski sürüm "
        "<code>maxsize=50</code> yazıyordu ve bu sayının hiçbir dayanağı yoktu. "
        "Daha kötüsü: 2 çekirdekli bir makinede 50 eşzamanlı kanıt açmak "
        "korumayı <b>işlevsiz</b> kılar — kuyruk hiç dolmaz ama makine çöker. "
        "Koruduğunu iddia ettiği senaryoda devreye girmeyen bir savunma, "
        "savunma değildir. Kapasite artık çekirdek sayısı ve boş bellekten "
        "türetilir; gerekçe <code>/api/health</code> üzerinden metin olarak "
        "yayınlanır.")

    a += h2("5.2 Kriptografi ve kanıt katmanı (Rust)")
    a += h3("ρ' tohumu nasıl türetilir")
    a += kod("ρ' = BLAKE3( ALAN_ETİKETİ ‖ risk_bitleri ‖ epoch_ns ‖\n"
             "            len(userOpHash) ‖ userOpHash ‖ entropi_bayrağı )")
    a += mad([
        "<b>Alan etiketi</b>, aynı hash'in başka amaçlarla üretilen "
        "özetleriyle çakışmayı önler.",
        "<b>Uzunluk ön-eki</b> şart: (\"ab\" ‖ \"\") ile (\"a\" ‖ \"b\") aynı "
        "özete gitmemeli.",
        "<b>Entropi bayrağı</b> 0 ise koşu deterministiktir. Taze entropi "
        "isteyen <code>--fresh-entropy</code> ile açıkça verir ve bu payload'da "
        "işaretlenir.",
    ])
    a += notk(
        "<b>Determinizm neden bilinçli.</b> Eski uygulama <code>process::id()</code> "
        "karıştırıyordu; her koşuda farklı olduğu için kanıt <b>yeniden "
        "üretilebilir değildi</b> — jüri aynı sonucu alamazdı. Kaldırıldı.")

    a += h3("ρ' nereye gidiyor")
    a += tablo(["Hedef", "Nasıl"], [
        ["Gerçek ML-DSA anahtarı",
         "ξ = BLAKE3(alan ‖ ρ') → <code>KG::keygen_from_seed(ξ)</code>. "
         "Bu <b>gerçek</b> bir FIPS 204 anahtar üretimidir, benzetim değil."],
        ["STARK iz tablosu",
         "Kafes matrisi SHAKE-128 + reddetme örneklemesiyle genişletilir "
         "(FIPS 204 §7.3 ExpandA ile aynı yordam)."],
    ], [45 * mm, ICERIK_GENISLIGI - 45 * mm])

    a += h3("Gösterilen iz = kanıtlanan iz")
    a += p("Bir dönem arayüzde gösterilen tablo ile STARK'ın kanıtladığı tablo "
           "<b>farklıydı</b>: biri u128 aritmetiği, diğeri alan aritmetiği "
           "kullanıyordu. Sahnede jüriye gösterilen şey kanıtlanan şey değildi. "
           "Artık Winterfell tablosu, gösterilen tablodan <b>kopyalanır</b> — "
           "yeniden hesaplanmaz — ve bir test ikisinin aynı olduğunu doğrular.")

    a += h2("5.3 Zincir katmanı (Solidity)")
    a += tablo(["Sözleşme", "Görevi"], [
        ["QAdaptiveAccount",
         "ERC-4337 akıllı cüzdan. Zırh kademesini tutar, guardian imzasını "
         "doğrular, yüksek değerli transferlerde zaman kilidi uygular."],
        ["QAdaptivePaymaster",
         "Gaz sponsorluğu. Dört bağımsız kapıdan geçmeyen işlem sponsorlanmaz."],
        ["QAdaptiveAICore",
         "Zincir üstü risk oracle'ı. Zincir dışı guardian buraya risk yazar; "
         "cüzdan buradan okur."],
    ], [45 * mm, ICERIK_GENISLIGI - 45 * mm])

    a += h3("Zincirde ne oluyor, ne olmuyor")
    a += p("Sözleşme STARK kanıtını <b>doğrulamaz</b>. Yaptığı iki şey vardır:")
    a += mad([
        "Kanıtın <b>uzunluğunu</b> kontrol eder "
        "(<code>MIN_STARK_PROOF_BYTES = 3000</code>). Panik modunda kanıt "
        "zorunludur ve bu uzunluğu sağlamalıdır.",
        "Guardian'ın <b>ECDSA attestation imzasını</b> <code>ecrecover</code> "
        "ile doğrular. Bu imza, zincir dışı sistemin kararını zincire taşıyan "
        "bağdır.",
    ])
    a += p("Ölçülen maliyet: <code>validateUserOp</code> için "
           "<b>26.449 – 147.510 gaz</b> (medyan 74.155), "
           "<code>forge test --gas-report</code> ile ölçüldü.")

    a += h3("Oracle bayatlarsa ne olur — tasarımın kalbi")
    a += p("Bir oracle'ın susması, hiç konuşlandırılmamış olmasından daha "
           "tehlikelidir: cüzdan son değere güvenmeye devam eder. İki yön de "
           "kötüdür:")
    a += tablo(["Yaklaşım", "Sonuç"], [
        ["<b>fail-open</b> — bayatken risk = 0 raporla",
         "Updater'ı susturabilen saldırgan zırhı en zayıf kademeye düşürür. "
         "Saldırıyı ödüllendirir."],
        ["<b>fail-closed</b> — bayatken panik = true raporla",
         "Her işlem ≥3.000 baytlık kanıt ister. Zincir dışı yığın çöktüğü için "
         "bayatlamıştır; o kanıtı kimse üretemez ve <b>cüzdan kilitlenir</b>."],
        ["<b>seçilen</b> — azami risk, panik KAPALI",
         "Zırh en güçlü kademeye çıkar (savunmacı, kullanıcıya zincirde ek "
         "maliyeti yok) ama cüzdan kullanılabilir kalır."],
    ], [58 * mm, ICERIK_GENISLIGI - 58 * mm])
    a += p("Yeni konuşlandırılan oracle <b>bilerek bayat başlar</b>: henüz "
           "hiçbir şey ölçmemiştir, risk 0 raporlamak en tehlikeli yönde yalan "
           "olurdu. <code>isStale()</code> herkese açıktır, böylece arayüz "
           "bozulmuş durumu gizlemek yerine gösterebilir.")
    a += [PageBreak()]
    return a


def bolum6():
    a = h1("6. Uçtan uca bir koşu")
    a += p("Bu bölüm, yüksek riskli bir işlemin sistemden nasıl geçtiğini "
           "<b>adım adım</b> izler. Aşağıdaki süreler gerçek bir koşudan "
           "alınmıştır; makinenize göre değişir.")

    a += h2("6.1 Senaryo")
    a += kod("İşlem sıklığı : 2.0   tx/s\n"
             "IP sapması    : 0.95\n"
             "Gas sapması   : 15.5\n"
             "\n"
             "Bu profil bir «drainer» saldırısına benzer: alışılmadık IP\n"
             "coğrafyası + aşırı yüksek gas kullanımı.")

    a += h2("6.2 On bir aşama")
    a += p("Boru hattının her aşaması <b>ayrı ayrı ölçülür</b>. Arayüzdeki "
           "şeritte gördüğünüz süreler bunlardır:")
    a += tablo(
        ["#", "Aşama", "Ne yapar", "Örnek süre"],
        [
            ["1", "ONNX çıkarım",
             "3 özellik → Isolation Forest → kalibre risk skoru", "13,13 ms"],
            ["2", "zırh kararı",
             "risk ile τ(t) karşılaştırılır, kademe seçilir", "0,01 ms"],
            ["3", "ρ' türetimi",
             "BLAKE3 ile 32 baytlık tohum", "0,01 ms"],
            ["4", "kafes genişletme",
             "SHAKE-128 + reddetme → 8×7 = 56 hücre", "0,12 ms"],
            ["5", "ML-DSA keygen",
             "ξ'den gerçek anahtar çifti (pk 2592 B, sk 4896 B)", "0,58 ms"],
            ["6", "imzalama",
             "Gerçek ML-DSA imzası (4.627 B)", "0,55 ms"],
            ["7", "doğrulama",
             "İmza geçerli mi — evet", "0,35 ms"],
            ["8", "kurcalama testi",
             "Mesaj bozulursa imza reddediliyor mu — evet", "0,35 ms"],
            ["9", "iz tablosu",
             "8 satır × 4 sütun MLWE izi", "0,05 ms"],
            ["10", "STARK prover",
             "Winterfell kanıtı üretir (~4.009 bayt)", "6,81 ms"],
            ["11", "yerel doğrulama",
             "Kanıt yerelde doğrulanır, 80 bit konjektürel", "0,15 ms"],
        ],
        [8 * mm, 30 * mm, ICERIK_GENISLIGI - 60 * mm, 22 * mm])

    a += notk(
        "<b>Neden 11, 12 değil.</b> Listede bir dönem <code>payload_yazma</code> "
        "adlı 12. bir aşama vardı ve her zaman <b>0,00 ms</b> gösteriyordu: "
        "prover kendi dosya yazımını ölçemez. Şeridin başlığı «HER SÜRE "
        "ÖLÇÜLDÜ» iken orada ölçülmemiş bir sıfır durmasına izin verilemezdi. "
        "Hem Rust hem Python tarafından kaldırıldı ve iki ayrı test geri "
        "gelmesini engelliyor.")

    a += h2("6.3 Kurcalama testi neden canlı hatta koşuyor")
    a += p("8. aşama dikkat çekicidir. \"Kurcalanmış mesaj reddediliyor\" "
           "iddiası eskiden yalnızca bir birim testindeydi. Artık <b>her "
           "koşuda</b>, sahnenin ortasında çalışır: imzalanan mesaj bozulur ve "
           "doğrulayıcının onu reddettiği görülür. Reddetmezse koşu durur.")
    a += p("Bunun anlamı şudur: jüri \"imzanız gerçekten çalışıyor mu?\" diye "
           "sorduğunda, cevap bir teste atıf değil — <b>ekranda o anda yanan "
           "bir rozettir</b>.")

    a += h2("6.4 Calldata tasarrufu — dikkatli okunması gereken sayı")
    a += p("Sistem 50 işlemlik bir parti için tek bir kanıt üretir. "
           "Karşılaştırma şöyledir:")
    a += kod("İşlem başına ML-DSA-87 imzası : 50 × 4.627 B = 231.350 B\n"
             "Tek ZK-STARK kanıtı           :                  ~4.009 B\n"
             "                              → yaklaşık %98,3 tasarruf\n"
             "\n"
             "Karşılaştırma: 50 ECDSA imzası : 50 × 65 B   =   3.250 B\n"
             "                              → ECDSA DAHA KÜÇÜK")
    a += notk(
        "<b>Taban ML-DSA imzasıdır, ECDSA değil.</b> 50 ECDSA imzası tek bir "
        "STARK kanıtından küçüktür; yani ECDSA calldata boyutunda bizi yener. "
        "<code>calldata.beats_ecdsa</code> alanı bu yüzden <b>false</b> döner "
        "ve arayüz bunu gizlemez. Takas edilen şey boyut değil, "
        "<b>post-kuantum güvenliğidir</b> — ECDSA'nın Shor algoritması "
        "altında sağlayamadığı tek şey.")
    a += [PageBreak()]
    return a


def bolum7():
    a = h1("7. Arayüz")
    a += p("Arayüz tek bir HTML dosyasıdır ve <b>hiçbir dış kaynak "
           "kullanmaz</b> — ne Tailwind, ne Chart.js, ne Google Fonts. "
           "Sebebi pratiktir: sahnede internet olmayabilir. Gömülü CSS, "
           "vanilla JavaScript, satır içi SVG ve sistem yazı tipleriyle "
           "yazılmıştır. Bir test bu kuralı zorlar.")

    a += h2("7.1 İki temel kural")
    a += tablo(["Kural", "Nasıl uygulanıyor"], [
        ["Hiçbir sayı uydurulmaz",
         "Her bağlı alan <code>data-bind=\"yol.alan\"</code> ile işaretli. "
         "Bir test bu yolların API şemasında <b>gerçekten var olduğunu</b> "
         "doğruluyor — 38 alan. Arayüz var olmayan bir alana bağlanırsa CI kırılır."],
        ["Sunucu yoksa hiçbir şey gösterilmez",
         "Bağlantı koparsa kırmızı bant çıkar ve <b>38 alanın 38'i</b> "
         "<code>—</code> olur. Eski arayüz sessizce örnek veriye düşüyordu; "
         "bu, denetimde kapatılan «bayat kanıt geri dönüşü» bulgusunun arayüz hâliydi."],
    ], [45 * mm, ICERIK_GENISLIGI - 45 * mm])

    a += h2("7.2 Tema")
    a += p("Varsayılan tema <b>koyudur</b>: sunum karartılmış bir salonda "
           "projeksiyonla yapılacak. Aydınlık odada incelemek ve ekran "
           "görüntüsü almak için <b>açık tema</b> vardır; üst şeritteki "
           "☾/☀ düğmesi veya <b>T</b> tuşuyla geçilir ve tercih saklanır.")
    a += [PageBreak()]

    a += h2("7.3 Tam ekran")
    a += gorsel("00_tam_ekran.png",
                "<b>Görüntü 1 — Konsolun tamamı (koyu tema).</b> Ekran soldan "
                "sağa, yukarıdan aşağıya bir <b>nedensellik sırası</b> izler: "
                "işlem → sezgi → zırh → kanıt, ardından yürütme izi, sonra "
                "kafes ve karar gerekçesi. Sekme yoktur; bir koşunun tüm "
                "parçaları aynı ekranda ve neden-sonuç sırasındadır.")
    a += [PageBreak()]

    a += gorsel("00_tam_ekran_acik.png",
                "<b>Görüntü 2 — Aynı konsol, açık tema.</b> Vurgu renkleri "
                "beyaz zeminde WCAG AA kontrastını sağlayacak biçimde ayrı "
                "seçilmiştir; koyu tema için ayarlanmış tonlar doğrudan "
                "kullanılsaydı okunabilirlik düşerdi.")
    a += [PageBreak()]

    a += h2("7.4 Üst şerit")
    a += gorsel("01_ust_serit.png",
                "<b>Görüntü 3 — Durum şeridi.</b> Soldan sağa: bağlantı "
                "durumu, koşu kimliği (run_id), dinamik eşik τ(t), seçilen "
                "zırh kademesi, koşunun deterministik olup olmadığı ve kuyruk "
                "derinliği. Bağlantı koparsa bu şerit kırmızıya döner ve "
                "ekrandaki tüm alanlar temizlenir.")

    a += h2("7.5 Nedensellik: işlem → sezgi → zırh → kanıt")
    a += gorsel("02_nedensellik.png",
                "<b>Görüntü 4 — Dört kart, tek satırda projenin tüm savı.</b> "
                "<b>Kart 1</b> üç girdi özelliğini ve senaryo düğmelerini "
                "tutar. <b>Kart 2</b> Isolation Forest skorunu τ(t) ile "
                "karşılaştırır ve ölçülen ONNX süresini gösterir. <b>Kart 3</b> "
                "bu karşılaştırmanın seçtiği zırh kademesini, gerçek FIPS 204 "
                "anahtar/imza boyutlarını ve canlı kurcalama kontrolünü "
                "gösterir. <b>Kart 4</b> STARK sonucunu taşır: kanıt boyutu, "
                "prover süresi, güvenlik biti ve calldata tasarrufu.")
    a += notk(
        "Kart 4'ün son satırına dikkat: <b>«ECDSA'yı yeniyor mu → hayır "
        "(ECDSA daha küçük)»</b>. Bu satır bilerek oradadır. Sistem kendi "
        "aleyhine olan ölçümü de gösterir; gizlemez.")
    a += [PageBreak()]

    a += h2("7.6 Yürütme izi")
    a += gorsel("03_yurutme_izi.png",
                "<b>Görüntü 5 — On bir aşama, her birinin süresi ayrı "
                "ölçülmüş.</b> ONNX çıkarımından ρ' türetimine, kafes "
                "genişletmeden ML-DSA anahtar üretimi/imzalama/doğrulamaya, "
                "canlı kurcalama testinden iz tablosuna, STARK prover'dan "
                "yerel doğrulamaya. Her kutuda üstte aşama adı, ortada "
                "ölçülen süre, altta o aşamanın ne yaptığına dair tek satır "
                "kanıt (örneğin «pk 2592 B · sk 4896 B» ya da «kurcalanmış "
                "mesaj reddedildi»).")

    a += h2("7.7 Kafes büyümesi ve karar gerekçesi")
    a += gorsel("04_kafes_ve_karar.png",
                "<b>Görüntü 6 — Üç sütun.</b> <b>Solda</b> ρ''den SHAKE-128 ve "
                "reddetme örneklemesiyle genişletilmiş <b>gerçek</b> kafes "
                "matrisi; ML-DSA-87 kademesinde 8×7 = 56 hücre, hücre rengi "
                "değerin büyüklüğünü gösterir. ρ''nün tek bir biti değişirse "
                "56 hücrenin tamamı değişir. <b>Ortada</b> üç ML-DSA imza "
                "uzunluğunun ECDSA referans çubuğuyla karşılaştırması — "
                "değerler FIPS tablosundan değil, o koşuda ölçülmüş "
                "kütüphane çıktısından gelir. <b>Sağda</b> bu koşunun neden "
                "böyle bittiğinin, kodun değerlendirdiği sırayla yazılmış "
                "gerekçesi.")
    a += [PageBreak()]

    a += h2("7.8 Arayüzde olmayan şey: sınırlar paneli")
    a += p("Konsolda bir dönem <b>«İddia Etmediklerimiz»</b> paneli ve altı "
           "adımlık bir <b>Sunum Modu</b> vardı. İkisi de kaldırıldı; arayüz "
           "tek bir çalışma ekranı olarak sadeleştirildi.")
    a += p("Sınırlar ortadan kalkmadı, <b>yer değiştirdi</b>. Bu belgenin "
           "9. bölümü ve jüri kitapçığının 4. bölümü onları ayrıntılı olarak "
           "sayıyor. README'de de bir tablo hâlinde duruyor ve bir test, "
           "maddelerden biri silinirse yapıyı kırıyor.")
    a += notk(
        "<b>Bunun sunuma etkisi:</b> sınırlar artık ekranda kendiliğinden "
        "görünmüyor, yani <b>sözlü olarak söylenmeleri gerekiyor</b>. "
        "Jüri «burada sıfır bilgi olan ne?» diye sorduğunda işaret edilecek "
        "bir panel yok; cevabın hazır olması şart. Jüri kitapçığı tam olarak "
        "bunun için var.")
    a += p("Arayüzde kalan tek klavye kısayolu <b>T</b> (tema) ve "
           "<b>Enter</b> (koşuyu tetikle).")

    a += [PageBreak()]
    return a


def bolum8():
    a = h1("8. Neler yapabiliyor")
    a += p("Aşağıdaki her satır <b>çalıştırılarak doğrulanmıştır</b> ve "
           "yanında onu koruyan test vardır.")
    a += tablo(
        ["Yetenek", "Kanıtı", "Koruyan test"],
        [
            ["Gerçek ML-DSA anahtarı üretip imza atıyor ve doğruluyor",
             "fips204 kütüphanesi; boyutlar FIPS 204 tablosuyla karşılaştırılıyor",
             "pqc::tests::gercek_imza_ve_dogrulama, standart_boyutlari_uyusuyor"],
            ["Kurcalanmış mesajı reddediyor",
             "Canlı hatta her koşuda sınanıyor, sonuç ekranda rozet",
             "pqc::tests::kurcalanan_mesaj_reddediliyor"],
            ["Zırh risk ile birlikte gerçekten büyüyor",
             "İmza 2.420 → 3.309 → 4.627 bayta çıkıyor",
             "pqc::tests::imza_zirhla_birlikte_buyuyor"],
            ["AI kararı kripto katmanına geçiyor",
             "Altı argüman ikiliye aktarılıyor; kafes 16 → 30 → 56 hücre",
             "pipeline::tests::otonomi_koprusu_riski_kripto_katmanina_tasiyor"],
            ["Rust ve Python aynı eşik kuralını uyguluyor",
             "13 sınır vektörü, gerçek ikili çalıştırılarak",
             "ArmorPolicyParityTest"],
            ["Aynı girdi aynı kanıtı veriyor (determinizm)",
             "ρ', anahtar ve imza birebir aynı",
             "hashing::tests::rho_prime_tam_deterministik, DeterminismParityTest"],
            ["Gösterilen iz = kanıtlanan iz",
             "Winterfell tablosu kopyalanıyor, yeniden hesaplanmıyor",
             "pipeline::tests::gosterilen_iz_kanitlanan_izle_ayni"],
            ["Python imzası gerçek sözleşmede doğrulanıyor",
             "Saf Python Keccak-256 + secp256k1 → Solidity ecrecover",
             "GuardianAttestationTest"],
            ["Paymaster boşaltılamıyor",
             "Dört bağımsız kapı; sömürü senaryosunun kendisi bir test",
             "test_BULGU5_saldirgan_sozlesmesi_sponsorluk_alamiyor"],
            ["Risk skoru kullanıcıdan okunamıyor",
             "Oracle ya da guardian imzası; gönderenin yazdığı alan karara girmiyor",
             "test_BULGU6_iddia_edilen_sifir_risk_ai_kapisini_gecemiyor"],
            ["Zırh asla düşürülemiyor",
             "Zincir üstünde tek yönlü tırmanma",
             "testFuzz_E4_zirh_monoton_artiyor"],
            ["Gerçek EntryPoint v0.7 ile çalışıyor",
             "Ethereum mainnet fork'una karşı 4/4 test",
             "EntryPointFork.t.sol"],
            ["Oracle susarsa zırh düşmüyor",
             "Bayat oracle azami risk + panik kapalı raporluyor",
             "test_updateri_susturmak_zirhi_dusurmuyor"],
        ],
        [44 * mm, 52 * mm, ICERIK_GENISLIGI - 96 * mm])
    a += [PageBreak()]
    return a


def bolum9():
    a = h1("9. Neler yapamıyor ve neden")
    a += p("Bu bölüm bilinçli olarak ayrıntılıdır. Bir sınırı gizlemek onu "
           "ortadan kaldırmaz; yalnızca başkasının bulmasını bekler.")

    a += h2("9.1 Mimari sınırlar — tasarım gereği")
    a += tablo(
        ["Sınır", "Sebep", "Düzeltilebilir mi"],
        [
            ["STARK, ML-DSA doğrulamasını devre içinde ispatlamıyor",
             "AIR üç kısıt uygular: s1 ve s2'nin ilerleyişi ve t = A·s1 + s2. "
             "Bu, ML-DSA imza doğrulama devresi değil, ondan esinlenmiş bir "
             "MLWE ilişkisidir.",
             "<b>Pratikte hayır.</b> Tam ML-DSA doğrulamasını bir STARK "
             "devresine kodlamak aylar süren, araştırma düzeyinde bir iştir."],
            ["Kanıt zincirde doğrulanmıyor",
             "Sözleşme yalnızca uzunluk kontrolü + ECDSA attestation yapar.",
             "<b>Hayır.</b> Solidity'de STARK doğrulayıcı yazmak devasa bir "
             "iştir ve mimarinin amacı zaten bundan kaçınmaktır."],
            ["«Sıfır bilgi» nominal — gizlenen sır yok",
             "ρ' yayınlanıyor; s1, s2 ve A ondan yeniden hesaplanabilir.",
             "<b>Teknik olarak evet, ama istenmez.</b> ρ''yü gizlemek "
             "determinizmi ve jürinin kanıtı yeniden üretebilmesini bozardı."],
            ["AI kuantum saldırısı tespit etmiyor",
             "Model davranışsal anomali görür; kuantum saldırısının zincirde "
             "bıraktığı bir iz yoktur.",
             "<b>Hayır.</b> Bu, modelin değil problemin doğası."],
            ["Rotasyon kafes problemini zorlaştırmıyor",
             "MLWE'nin zorluğu parametrelerden gelir, tohumdan değil.",
             "<b>Uygulanamaz.</b> Rotasyonun amacı ileri güvenlik."],
        ],
        [42 * mm, 58 * mm, ICERIK_GENISLIGI - 100 * mm])

    a += h2("9.2 Eksikler — yapılabilir ama yapılmadı")
    a += tablo(
        ["Eksik", "Bugünkü durum", "Değerlendirme"],
        [
            ["Hiçbir ağa konuşlandırılmadı",
             "Konuşlandırma betiği yazıldı, testlerle korunuyor ve yerelde "
             "anvil'e karşı uçtan uca koştu. Genel bir ağa gönderilmedi.",
             "<b>Yapılmalı.</b> Fonlu bir anahtar ve RPC ile birkaç saat. "
             "«Fork testi geçti» ile «testnette canlı» arasında büyük fark var."],
            ["Bağımsız güvenlik denetimi yok",
             "Slither ve solhint CI'da koşuyor; insan denetimi yapılmadı.",
             "<b>Yarışma için gerekli değil.</b> Üretim için şart."],
            ["Guardian anahtarı bellekte",
             "attestation.py anahtarı süreç belleğinde tutuyor ve "
             "sabit-zamanlı değil.",
             "<b>Üretim şartı, prototip şartı değil.</b> HSM/KMS'e taşınmalı."],
            ["Account dal kapsamı %80,28",
             "Kapsanmayan dallar guardian imza kurtarma savunma kolları "
             "(bozuk v, sonsuzdaki nokta).",
             "<b>Yapılabilir</b>, 1–2 saat. Orta değerli."],
            ["Eğitim verisi sentetik",
             "Kontrollü üretilmiş veri; canlı zincirden toplanmadı.",
             "<b>Gizlenmiyor.</b> Gerçek veriyle eğitim günler alır ve "
             "yarışma kapsamını aşar."],
            ["Yüzdelik gecikmeler ölçülmedi",
             "Ortalama ölçülüyor; p50/p95/p99 toplanmıyor.",
             "<b>Kolay</b> ama düşük değerli. Belgeler artık «ölçülmedi» diyor."],
        ],
        [40 * mm, 58 * mm, ICERIK_GENISLIGI - 98 * mm])

    a += h2("9.3 Söylenemeyecek cümleler")
    a += p("Bunlar sahnede <b>kullanılmamalıdır</b>, çünkü doğru değildirler:")
    a += mad([
        "«STARK, ML-DSA doğrulamasını ispatlıyor» → ispatlamıyor.",
        "«Kanıt zincirde doğrulanıyor» → doğrulanmıyor, uzunluğu kontrol ediliyor.",
        "«Mainnet'e konuşlandırıldı» → hiçbir ağa konuşlandırılmadı.",
        "«ECDSA'dan daha az calldata» → 50 ECDSA imzası bizden küçük.",
        "«Bağımsız denetimden geçti» → geçmedi.",
        "«%100 test kapsamı» → dal kapsamı %82,55.",
        "«Sertifikalı metrikler» → hiçbir kurum sertifikalandırmadı; kendi ölçümlerimiz.",
    ])
    a += [PageBreak()]
    return a


def bolum10():
    a = h1("10. Test ve doğrulama")
    a += p("Projenin işleyiş kuralı şudur:")
    a += notk(
        "Bir bulgu, ancak geri gelmesini engelleyen ve <b>gerçekten "
        "çalıştırılmış</b> bir testi varsa kapalıdır. Yorumda «düzeltildi» "
        "yazmak kapatmaz.")

    a += h2("10.1 Sayılar")
    a += tablo(["Katman", "Komut", "Sonuç"], [
        ["Rust (ZK + PQC)", "cargo test", "<b>61</b> geçti"],
        ["Solidity", "forge test", "<b>142</b> geçti, 4 atlandı (fork)"],
        ["Katman eşitliği", "python3 test_layer_parity.py", "<b>9</b> geçti"],
        ["Attestation kriptosu", "python3 test_attestation.py", "<b>18</b> geçti"],
        ["API ↔ arayüz sözleşmesi", "python3 test_api_contract.py", "<b>9</b> geçti"],
        ["<b>Toplam</b>", "", "<b>244 otomatik test</b>"],
    ], [42 * mm, 58 * mm, ICERIK_GENISLIGI - 100 * mm])
    a += p("Solidity testlerinin <b>12'si</b> fuzz/değişmez testidir; her biri "
           "512 rastgele koşu yapar.")

    a += h2("10.2 Ölçülen kapsam")
    a += tablo(["Sözleşme", "Satır", "Dal", "Fonksiyon"], [
        ["QAdaptiveAICore", "%100,00 (46/46)", "%95,24 (20/21)", "%100,00 (11/11)"],
        ["QAdaptivePaymaster", "%100,00 (104/104)", "%97,14 (34/35)", "%100,00 (17/17)"],
        ["QAdaptiveAccount", "%94,15 (177/188)", "%80,28 (57/71)", "%96,00 (24/25)"],
        ["<b>Toplam</b>", "<b>%96,10</b>", "<b>%82,55</b>", "<b>%95,31</b>"],
    ])
    a += p("<b>Dal kapsamı %100 değildir ve öyle olduğu iddia edilmez.</b>")

    a += h2("10.3 CI hattı — altı iş")
    a += tablo(["İş", "Ne yapar"], [
        ["Python · ONNX & API", "ONNX parity, attestation, sözleşme testleri"],
        ["Rust · STARK & Clippy", "cargo test, clippy -D warnings, fmt --check"],
        ["Solidity · Foundry", "forge test, coverage, gas report, deploy build"],
        ["Regresyon Koruması", "Kapatılan bulgular grep ile geri gelmesin"],
        ["Solidity · Lint & Slither", "solhint + Slither zafiyet dedektörleri"],
        ["Repo · Hijyen", "TruffleHog sır taraması, dosya hijyeni"],
    ], [50 * mm, ICERIK_GENISLIGI - 50 * mm])

    a += h2("10.4 Alışılmadık korumalar")
    a += tablo(["Koruma", "Neyi engelliyor"], [
        ["README'yi okuyan test",
         "Belgedeki güvenlik biti ile koddaki sabitin ayrışması"],
        ["Arayüzü okuyan test",
         "Arayüzün API'de var olmayan bir alana bağlanması (38 alan)"],
        ["Sınırlar panelini okuyan test",
         "Bir sınırın panelden sessizce silinmesi"],
        ["Belge kod bloklarını üreten kapı",
         "docs/ içindeki kod alıntılarının kaynaktan sapması (23 blok)"],
        ["Grep tabanlı regresyon kapıları",
         "DefaultHasher, sabit 90,0 eşiği, uydurma 4608 tabanı, "
         "process::id(), gas: 2300 stipend'i"],
    ], [52 * mm, ICERIK_GENISLIGI - 52 * mm])
    a += [PageBreak()]
    return a


def bolum11():
    a = h1("11. Denetim hikâyesi — çıkarılan dersler")
    a += p("Bu bölüm projenin teknik değil <b>yöntemsel</b> kısmıdır ve belki "
           "de en öğreticisidir. Proje bir denetimden geçti; 21 bulgu çıktı ve "
           "hepsi kapatıldı. Ama asıl değerli olan, bulguların ortak "
           "<b>deseni</b>ydi.")

    a += h2("11.1 Kurucu bulgu")
    a += notk(
        "Belgeler «ML-DSA kullanıyoruz» diyordu. Kodda <b>tek satır</b> ML-DSA "
        "yoktu — depoda hiçbir post-kuantum bağımlılığı bile bulunmuyordu.")
    a += p("Bu, tek bir hata değil bir <b>hata sınıfıydı</b>: anlatının koddan "
           "kopması. Aynı desen sonra dört ayrı yerde daha bulundu.")

    a += h2("11.2 Aynı hatanın dört görünümü")
    a += tablo(["Nerede", "Ne oluyordu"], [
        ["Kodda",
         "Belgeler ML-DSA diyordu, kod yoktu. Zırh geçişi JSON'a yazılan bir "
         "metinden ibaretti."],
        ["Arayüzde",
         "API'ye ulaşılamazsa sessizce örnek veriye düşüyordu "
         "(proof_size_kb: 3.85, risk_score: 98.52). Sunucu çökse bile ekran "
         "dolu görünüyordu."],
        ["CI'da",
         "Dört ayrı «yeşil ama hiçbir şey yapmayan» kontrol: geçersiz YAML, "
         "hiçbir şey taramayan TruffleHog, sessizce çöken Slither, "
         "pipefail'siz boru hattı."],
        ["Belgelerde",
         "docs/ altındaki «Kod İncelemesi» bölümleri kaynak dosyaların "
         "tamamını alıntılıyordu, ama alıntılar donmuştu: DefaultHasher "
         "koddan silindikten sonra belgede <b>21 yerde</b> duruyordu."],
    ], [30 * mm, ICERIK_GENISLIGI - 30 * mm])

    a += h2("11.3 En tehlikeli desen: yeşil ama boş kontrol")
    a += p("Bu oturumda <b>dört kez</b> aynı tuzağa düşüldü ve her seferinde "
           "ders aynıydı:")
    a += notk(
        "<b>Koştuğu iddia edilen ama hiçbir şey yapmayan bir kontrol, "
        "hiç kontrol olmamasından daha tehlikelidir</b> — çünkü sahte bir "
        "güvence verir. \"CI yeşil\" demek, CI'ın bir şey kontrol ettiği "
        "anlamına gelmez.")
    a += mad([
        "CI geçersiz YAML yüzünden hiç koşmuyordu.",
        "TruffleHog <code>base == head</code> olduğu için sıfır dosya "
        "tarıyordu — <b>iş yeşildi</b>.",
        "Slither <code>forge</code> bulunamadığı için anında çöküyordu; "
        "<code>continue-on-error</code> bunu gizliyordu.",
        "<code>slither . | tee rapor.txt</code> — <code>pipefail</code> "
        "olmadan çıkış kodu <code>tee</code>'den gelir; Slither düşse bile "
        "kapı açık kalırdı.",
    ])

    a += h2("11.4 Alınan yapısal önlemler")
    a += p("Bulguları tek tek düzeltmek yetmezdi; aynı sınıfın <b>geri "
           "gelmesini</b> engelleyecek mekanizmalar kuruldu:")
    a += tablo(["Önlem", "Mantığı"], [
        ["Belge kod blokları kaynaktan üretiliyor",
         "Elle güncellenen bir alıntı eninde sonunda kayar. 23 blok artık "
         "<code>docs/kod_bloklari_senkron.py</code> ile üretiliyor ve "
         "<code>--check</code> CI kapısı sapmayı yakalıyor."],
        ["Arayüz alanları şemaya karşı doğrulanıyor",
         "Arayüz var olmayan bir alana bağlanamaz; 38 alan her koşuda "
         "kontrol ediliyor."],
        ["Sınırlar paneli testle korunuyor",
         "Bir sınırı silmek yapıyı kırar. Panel gizlendikten sonra, onu "
         "<b>açan</b> bağlantının varlığı da test ediliyor."],
        ["Negatif kontrol alışkanlığı",
         "Yeni bir koruma yazıldığında, korumanın gerçekten kırıldığı "
         "görülmeden kabul edilmiyor. Bu oturumda birkaç kez bir testin "
         "aslında hiçbir şeyi yakalamadığı böyle bulundu."],
    ], [52 * mm, ICERIK_GENISLIGI - 52 * mm])

    a += h2("11.5 Sonradan bulunan üç kritik hata")
    a += p("Denetim listesinde olmayan ama <b>canlı ağda sistemi tamamen "
           "çalışmaz hâle getirecek</b> üç hata sonradan bulundu:")
    a += tablo(["Hata", "Sonucu"], [
        ["Ön-fonlama <code>gas: 2300</code> ile yapılıyordu",
         "Gerçek EntryPoint'in <code>receive()</code>'ı mevduat muhasebesi "
         "için depolamaya yazar (~20.000+ gaz). 2.300 gaz bir SSTORE'a "
         "yetmez ⇒ çağrı <b>her zaman</b> başarısız ⇒ <b>her işlem revert "
         "eder</b>. Hesap canlı ağda hiçbir işlemi tamamlayamazdı."],
        ["<code>validateUserOp</code> doğrulama sırasında depolamaya yazıyordu",
         "ERC-7562 ihlali. Birçok bundler böyle bir işlemi mempool'a hiç "
         "almaz; ayrıca ucuz bir depolama şişirme (DoS) vektörü."],
        ["Gösterilen iz, kanıtlanan iz değildi",
         "Sahnede jüriye gösterilen tablo STARK'ın kanıtladığı tablo "
         "değildi — biri u128, diğeri alan aritmetiği kullanıyordu."],
    ], [56 * mm, ICERIK_GENISLIGI - 56 * mm])
    a += [PageBreak()]
    return a


def bolum12():
    a = h1("12. Çalıştırma kılavuzu")

    a += h2("12.1 Gereksinimler")
    a += mad([
        "<b>Rust</b> (rustup ile) — ZK prover'ı derlemek için",
        "<b>Python 3.10+</b> — AI katmanı ve API",
        "<b>Foundry</b> (isteğe bağlı) — sözleşme testleri için",
    ])

    a += h2("12.2 Sıfırdan kurulum")
    a += kod(
        "git clone --depth 1 https://github.com/yorulmazkagan/CryptoTEK.git\n"
        "cd CryptoTEK\n"
        "\n"
        "# 1) Rust prover — ZORUNLU, API bu ikiliyi çağırıyor\n"
        "cd Q-Adaptive-ZK && cargo build --release && cd ..\n"
        "\n"
        "# 2) Python ortamı\n"
        "cd Q-Adaptive-AI\n"
        "python3 -m venv .venv && source .venv/bin/activate\n"
        "pip install -r requirements.txt\n"
        "\n"
        "# 3) Sunucu\n"
        "python3 run_server.py")
    a += p("Arayüz: <b>http://127.0.0.1:8000/ui/</b> — başlangıç yaklaşık "
           "<b>18 saniye</b> sürer (ONNX yükleniyor). "
           "«✅ Sunucu isteklere hazır.» satırını görmeden tarayıcıyı açarsanız "
           "«SUNUCUYA BAĞLANILAMADI» bandını görürsünüz.")
    a += notk(
        "<code>--depth 1</code> bilinçli: deponun geçmişi büyük sunum "
        "dosyaları yüzünden 177 MB'a çıkmış durumda ve tam klonlama ağ "
        "kesintilerinde düşebiliyor.")

    a += h2("12.3 Her iddiayı doğrulama")
    a += kod(
        "# Rust: 61 test\n"
        "cd Q-Adaptive-ZK && cargo test && cargo clippy --all-targets -- -D warnings\n"
        "\n"
        "# Solidity: 146 test (4'ü fork — sır yoksa atlanır)\n"
        "cd Q-Adaptive-Contracts && forge test -vv\n"
        "forge coverage --report summary\n"
        "\n"
        "# Katmanlar arası eşitlik — gerçek Rust ikilisini çalıştırır\n"
        "python3 Q-Adaptive-AI/test_layer_parity.py\n"
        "\n"
        "# Attestation kriptosu: bilinen Keccak-256 / ECDSA vektörleri\n"
        "python3 Q-Adaptive-AI/test_attestation.py\n"
        "\n"
        "# API <-> arayüz sözleşmesi\n"
        "python3 Q-Adaptive-AI/test_api_contract.py\n"
        "\n"
        "# Belge kod blokları kaynakla eşleşiyor mu\n"
        "python3 docs/kod_bloklari_senkron.py --check\n"
        "\n"
        "# Tek koşu: ölçümleri elle görün\n"
        "./Q-Adaptive-ZK/target/release/q-adaptive-zk \\\n"
        "    --risk-score 92.4 --tau 75.0 --baseline 44 \\\n"
        "    --user-op-hash 0xdeadbeefcafebabe \\\n"
        "    --epoch-ns 1700000000000000000 --run-id demo")
    a += p("Herhangi bir komut kırılırsa, bu belgedeki ilgili iddia "
           "geçersizdir. Kasıtlı olarak böyledir: iddialar testlere bağlıdır, "
           "yorumlara değil.")

    a += h2("12.4 Konuşlandırma (yapılmadı, ama hazır)")
    a += kod(
        "cd Q-Adaptive-Contracts\n"
        "cp .env.example .env && $EDITOR .env && source .env\n"
        "\n"
        "# Kuru koşu — hiçbir işlem yayınlanmaz\n"
        "forge script script/Deploy.s.sol:Deploy --rpc-url \"$RPC_URL\"\n"
        "\n"
        "# Gerçek konuşlandırma\n"
        "forge script script/Deploy.s.sol:Deploy --rpc-url \"$RPC_URL\" --broadcast")
    a += p("Betik, konuşlandırmadan <b>önce</b> EntryPoint adresinde gerçekten "
           "baytkod olduğunu doğrular ve <b>sonra</b> bağlantıları zincirden "
           "geri okur. Bu kontrol olmasaydı yanlış ağa konuşlandırma "
           "«başarılı» görünürdü: üç sözleşme iner, hiçbiri çalışmaz.")
    a += [PageBreak()]
    return a


def bolum13():
    a = h1("13. Sözlük")
    a += tablo(["Terim", "Tanım"], [
        ["AIR", "Algebraic Intermediate Representation. STARK izinin sağlaması "
                "gereken cebirsel kısıtlar."],
        ["BLAKE3", "Hızlı kriptografik hash fonksiyonu. Projede ρ' ve kısa "
                   "tohum türetiminde kullanılır."],
        ["Bundler", "ERC-4337'de UserOperation'ları toplayıp EntryPoint'e "
                    "gönderen aktör."],
        ["Calldata", "Zincire yazılan işlem verisi. Bayt başına ücretlendirilir."],
        ["Dilithium", "ML-DSA'nın NIST yarışmasındaki adı (CRYSTALS-Dilithium)."],
        ["Drainer", "Özel anahtarı ele geçirip cüzdanı boşaltan saldırı türü."],
        ["ECDSA", "Eliptik eğri tabanlı imza şeması. Kuantum karşısında kırık."],
        ["EntryPoint", "ERC-4337 akışını yöneten tekil sözleşme. v0.7 tüm "
                       "ağlarda aynı adreste."],
        ["ERC-4337", "Hesap soyutlama standardı. Cüzdanı akıllı sözleşme yapar."],
        ["ERC-7562", "Doğrulama sırasında nelerin yasak olduğunu belirleyen kural seti."],
        ["EVM", "Ethereum Sanal Makinesi. Zincir üstünde program çalıştırır."],
        ["f128", "Winterfell'in 128-bit asal alanı. STARK aritmetiği burada yapılır."],
        ["FIPS 204", "ML-DSA'nın NIST standardı."],
        ["FRI", "Fast Reed-Solomon IOP of Proximity. STARK'ın düşük derece "
                "testi bileşeni."],
        ["Fuzz test", "Rastgele üretilmiş girdilerle çalıştırılan test."],
        ["Gaz", "EVM'de yapılan işin ücreti."],
        ["Grover algoritması", "Kuantum arama algoritması. Hash güvenliğini "
                               "yarıya indirir, kırmaz."],
        ["Guardian", "Zincir dışı kararı imzalayıp zincire taşıyan aktör."],
        ["Isolation Forest", "Etiketsiz anomali tespiti algoritması."],
        ["Kafes (lattice)", "Uzayda düzenli dizilmiş nokta kümesi. Post-kuantum "
                            "kriptografinin temeli."],
        ["ML-DSA", "Module-Lattice-Based Digital Signature Algorithm. "
                   "Post-kuantum imza standardı."],
        ["MLWE", "Module Learning With Errors. ML-DSA'nın dayandığı zor problem."],
        ["MTD", "Moving Target Defense. Saldırganın keşif yüzeyini sürekli "
                "değiştirme stratejisi."],
        ["ONNX", "Eğitilmiş modelleri taşınabilir biçimde saklama standardı."],
        ["Paymaster", "Kullanıcının gazını ödeyen ERC-4337 sözleşmesi."],
        ["Platt ölçekleme", "Ham model skorunu olasılığa kalibre etme yöntemi."],
        ["Post-kuantum", "Kuantum bilgisayarların çözemediği problemlere dayanan "
                         "kriptografi."],
        ["Reddetme örneklemesi", "Yanlı olmayan rastgele değer üretmek için "
                                 "aralık dışı örnekleri atma yöntemi."],
        ["ρ' (rho-prime)", "32 baytlık rotasyon tohumu. Hem ML-DSA anahtarını "
                           "hem kafes izini besler."],
        ["SHAKE-128", "İstenilen uzunlukta çıktı veren hash (XOF)."],
        ["Shor algoritması", "Kuantum algoritması. ECDSA ve RSA'yı kırar."],
        ["Slither", "Solidity için statik zafiyet analiz aracı."],
        ["STARK", "Scalable Transparent ARgument of Knowledge. Şeffaf, "
                  "post-kuantum varsayımlı kanıt sistemi."],
        ["τ(t) (tau)", "Dinamik anomali eşiği. Kayan pencere varyansından "
                       "hesaplanır."],
        ["UserOperation", "ERC-4337'de kullanıcının niyetini taşıyan yapı."],
        ["Winterfell", "Rust için STARK kanıt kütüphanesi."],
        ["XOF", "Extendable-output function. İstenilen uzunlukta çıktı veren hash."],
        ["ZK (sıfır bilgi)", "Bir iddiayı, iddia dışında bilgi sızdırmadan "
                             "kanıtlama."],
    ], [38 * mm, ICERIK_GENISLIGI - 38 * mm])
    return a


def main():
    hikaye = []
    hikaye += kapak()
    hikaye += icindekiler()
    hikaye += bolum0()
    hikaye += bolum1()
    hikaye += bolum2()
    hikaye += bolum3()
    hikaye += bolum3b()
    hikaye += bolum3c()
    hikaye += bolum4()
    hikaye += bolum5()
    hikaye += bolum6()
    hikaye += bolum7()
    hikaye += bolum8()
    hikaye += bolum9()
    hikaye += bolum10()
    hikaye += bolum11()
    hikaye += bolum12()
    hikaye += bolum13()

    belge = SimpleDocTemplate(
        str(CIKTI),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title="Q-ADAPTIVE (AI Guardian) — Sıfırdan Öğretici Belge",
        author="CryptoTEK · TAKIM ID 909630",
        subject="TEKNOFEST 2026 Blokzincir Yarışması",
    )
    belge.build(hikaye, canvasmaker=Sayfa)
    boyut = CIKTI.stat().st_size / 1024
    print(f"  ✓ {CIKTI.name} — {boyut:.0f} KB")


if __name__ == "__main__":
    main()
