# Q-ADAPTIVE (AI Guardian) Projesi Kapsamlı Akademik ve Teknik Kaynakça Rehberi

Bu belge, **CryptoTEK** takımı tarafından geliştirilen **Q-ADAPTIVE** projesinin akademik temellerini, yararlandığı yayınları, standartları ve teknik kaynakları içermektedir. Belgede yer alan her kaynak, [presentation_blueprint_guide.md](file:///home/yorulmazkagan/Masa%C3%BCst%C3%BC/Bloq/Proje/presentation_blueprint_guide.md) dosyasındaki ilgili slaytlara göre eşleştirilmiştir.

---

## 1. KUANTUM HESAPLAMA VE "HARVEST NOW, DECRYPT LATER" (HNDL) KRİZİ

1. **Shor, P. W. (1994). "Algorithms for quantum computation: discrete logarithms and factoring." *IEEE FOCS*.**
   - **Açıklama**: Shor'un kuantum Fourier dönüşümünü kullanarak çarpanlara ayırma ve ayrık logaritma problemlerini polinomsal zamanda çözen temel makalesi.
   - **İlişkili Slaytlar**: [Slayt 3](#slayt-3), [Slayt 4](#slayt-4), [Slayt 15](#slayt-15)

2. **Proos, J., & Zalka, C. (2003). "Shor's discrete logarithm quantum algorithm for elliptic curves." *Quantum Information & Computation*.**
   - **Açıklama**: Shor algoritmasının eliptik eğri ayrık logaritma problemi (ECDLP) üzerindeki pratik etkisini ve secp256k1 gibi eğrilerin kuantum bilgisayarlarca nasıl kırılacağını analiz eden yayın.
   - **İlişkili Slaytlar**: [Slayt 4](#slayt-4), [Slayt 15](#slayt-15)

3. **Mosca, M. (2018). "Cybersecurity in a Quantum World: Will We Be Ready?" *IEEE Security & Privacy*.**
   - **Açıklama**: Kuantum tehdidinin zaman çizelgesini ve "Şimdi Depola, Sonra Deşifre Et" (HNDL) risk faktörünü küresel siber güvenlik kapsamında inceleyen makale.
   - **İlişkili Slaytlar**: [Slayt 3](#slayt-3), [Slayt 15](#slayt-15)

4. **National Academies of Sciences, Engineering, and Medicine. (2019). "Quantum Computing: Progress and Prospects." *The National Academies Press*.**
   - **Açıklama**: Kriptografik olarak anlamlı kuantum bilgisayarların (CRQC) geliştirilme olasılığını ve donanımsal kübit gelişimini inceleyen kapsamlı rapor.
   - **İlişkili Slaytlar**: [Slayt 3](#slayt-3)

5. **Bernstein, D. J. (2009). "Introduction to post-quantum cryptography." *Post-Quantum Cryptography*.**
   - **Açıklama**: Kuantum sonrası kriptografi paradigmasının doğuşunu ve klasik şifreleme yöntemlerinden kafes tabanlı yapılara geçiş gereksinimini açıklayan çalışma.
   - **İlişkili Slaytlar**: [Slayt 3](#slayt-3), [Slayt 14](#slayt-14), [Slayt 23](#slayt-23)

---

## 2. NIST POST-KUANTUM KRİPTOGRAFİ (PQC) STANDARTLARI VE KAFES (LATTICE) MATEMATİĞİ

6. **NIST. (2024). "FIPS 204: Module-Lattice-Based Digital Signature Standard." *NIST*.**
   - **Açıklama**: ML-DSA (Dilithium) dijital imza şemasının resmi NIST standardı ve implementasyon kuralları.
   - **İlişkili Slaytlar**: [Slayt 14](#slayt-14), [Slayt 23](#slayt-23), [Slayt 68](#slayt-68)

7. **Ducas, L., Kiltz, E., Lepoint, T., Lyubashevsky, V., Schwabe, P., Seiler, G., & Stehlé, D. (2018). "CRYSTALS-Dilithium: A lattice-based digital signature scheme." *ACM CCS*.**
   - **Açıklama**: Dilithium imza algoritmasının matematiksel tasarımını, güvenlik ispatlarını ve k x l MLWE matris parametrelerini tanımlayan orijinal yayın.
   - **İlişkili Slaytlar**: [Slayt 6](#slayt-6), [Slayt 14](#slayt-14), [Slayt 22](#slayt-22)

8. **Lyubashevsky, V. (2012). "Lattice signatures without trapdoors." *Eurocrypt*.**
   - **Açıklama**: Reddetme örneklemesi (rejection sampling) tekniğiyle kafes yapılarında tuzak kapısız (trapdoor-free) güvenli imza üretimini açıklayan makale.
   - **İlişkili Slaytlar**: [Slayt 23](#slayt-23), [Slayt 42](#slayt-42), [Slayt 68](#slayt-68)

9. **Alkim, E., Ducas, L., Pöppelmann, T., & Schwabe, P. (2016). "Post-quantum key exchange - a new hope." *USENIX Security*.**
   - **Açıklama**: Ring-LWE tabanlı kuantum sonrası anahtar değişimi optimizasyonları ve donanımsal hızlandırma metotları.
   - **İlişkili Slaytlar**: [Slayt 14](#slayt-14), [Slayt 23](#slayt-23)

10. **Regev, O. (2009). "On lattices, learning with errors, random linear codes, and cryptography." *Journal of the ACM*.**
    - **Açıklama**: Kuantum sonrası kriptografinin temel taşı olan LWE (Learning With Errors) problemini tanımlayan ve en kısa vektör bulma problemiyle (SVP) olan ilişkisini ispatlayan makale.
    - **İlişkili Slaytlar**: [Slayt 34](#slayt-34), [Slayt 42](#slayt-42)

---

## 3. SIFIR BİLGİ İSPATLARI (ZK-STARK) VE POLİNOMLASAL TAAHHÜTLER

11. **Ben-Sasson, E., Bentov, I., Horesh, Y., & Riabzev, M. (2018). "Scalable, transparent, and post-quantum secure computational integrity." *Cryptology ePrint Archive*.**
    - **Açıklama**: Güvenilir kuruluma (trusted setup) ihtiyaç duymayan ve kuantum dirençli olan ZK-STARK ispat sistemini tanımlayan çekirdek yayın.
    - **İlişkili Slaytlar**: [Slayt 5](#slayt-5), [Slayt 34](#slayt-34), [Slayt 41](#slayt-41)

12. **Ben-Sasson, E., Bentov, I., Horesh, Y., & Riabzev, M. (2018). "Fast Reed-Solomon Interactive Oracle of Proximity." *ICALP*.**
    - **Açıklama**: ZK-STARK ispat boyutlarını logaritmik seviyeye sıkıştırmakta kullandığımız FRI katlama protokolünün matematiksel altyapısı.
    - **İlişkili Slaytlar**: [Slayt 5](#slayt-5), [Slayt 41](#slayt-41), [Slayt 65](#slayt-65)

13. **Bootle, J., Cerulli, A., Chaidos, P., Groth, J., & Petit, C. (2016). "Efficient zero-knowledge arguments for arithmetic circuits." *Eurocrypt*.**
    - **Açıklama**: Aritmetik devrelerde sıfır bilgi ispatı üretim sürelerinin ve polinom kısıt asserts süreçlerinin verimlilik analizleri.
    - **İlişkili Slaytlar**: [Slayt 34](#slayt-34), [Slayt 41](#slayt-41)

14. **Winterfell Github Repository & Documentation. "Winterfell: A STARK prover and verifier." *Facebook/Diem Association*.**
    - **Açıklama**: FastAPI geçidimizin subprocess olarak tetiklediği Rust tabanlı Winterfell STARK kanıt motoru implementasyon kılavuzu.
    - **İlişkili Slaytlar**: [Slayt 5](#slayt-5), [Slayt 24](#slayt-24), [Slayt 35](#slayt-35)

15. **Goldwasser, S., Micali, S., & Rackoff, C. (1989). "The knowledge complexity of interactive proof systems." *SIAM Journal on Computing*.**
    - **Açıklama**: Kriptografik doğrulama süreçlerinde veri gizliliğini korumayı sağlayan sıfır bilgi ispatlarının (Zero-Knowledge) temel kuramsal tanımı.
    - **İlişkili Slaytlar**: [Slayt 5](#slayt-5), [Slayt 34](#slayt-34)

---

## 4. HESAP SOYUTLAMA (ACCOUNT ABSTRACTION) VE ERC-4337 STANDARDI

16. **Buterin, V., Roth, K., Chen, D., Ansgar, D., & Temkin, I. (2021). "EIP-4337: Account Abstraction Using Alt Mempool." *Ethereum Improvement Proposals*.**
    - **Açıklama**: Akıllı sözleşme cüzdanlarının zincir üstü durum doğrulamalarını asıl cüzdan seviyesine taşıyan standardın ilk teklifi.
    - **İlişkili Slaytlar**: [Slayt 6](#slayt-6), [Slayt 16](#slayt-16), [Slayt 43](#slayt-43)

17. **Ethereum Foundation. (2023). "ERC-4337: Official Account Abstraction Specification." *ethereum.org*.**
    - **Açıklama**: EntryPoint kontratı etkileşimlerini, validateUserOp kurallarını ve UserOperation veri yapılarını tanımlayan resmi şartname.
    - **İlişkili Slaytlar**: [Slayt 6](#slayt-6), [Slayt 18](#slayt-18), [Slayt 52](#slayt-52), [Slayt 63](#slayt-63)

18. **Buterin, V. (2020). "Tradeoffs in Account Abstraction Proposals." *Ethereum Research*.**
    - **Açıklama**: Cüzdan seviyesinde imza doğrulama adımlarının esnekliği ile EVM yürütme gaz maliyetleri arasındaki teknolojik dengeleri inceleyen araştırma.
    - **İlişkili Slaytlar**: [Slayt 18](#slayt-18), [Slayt 44](#slayt-44)

19. **Wan, H., Zhang, Y., & Song, Y. (2023). "Security Analysis of ERC-4337 Smart Accounts." *IEEE Blockchain*.**
    - **Açıklama**: Akıllı hesaplarda karşılaşılan imza doğrulama, paymaster istismarı ve bundler gas manipülasyon risklerinin analizi.
    - **İlişkili Slaytlar**: [Slayt 16](#slayt-16), [Slayt 19](#slayt-19), [Slayt 43](#slayt-43), [Slayt 67](#slayt-67)

20. **Gnosis Safe Dev Team. (2022). "Safe Smart Contracts Core Architecture." *Gnosis Safe Github*.**
    - **Açıklama**: Multi-sig cüzdan mimarisinin kurallarını ve Q-ADAPTIVE matrisinde Safe ile yaptığımız gaz-güvenlik karşılaştırmalarının referans kontratları.
    - **İlişkili Slaytlar**: [Slayt 21](#slayt-21), [Slayt 66](#slayt-66)

---

## 5. YAPAY ZEKA VE ZAMAN SERİSİ ANOMALİ TESPİTİ

21. **Hyndman, R. J., & Athanasopoulos, G. (2018). "Forecasting: principles and practice." *OTexts*.**
    - **Açıklama**: Telemetri veri akışlarında gas trend değişimlerini ve istatistiksel kayma modellerini kurmakta yararlandığımız tahmin kılavuzu.
    - **İlişkili Slaytlar**: [Slayt 24](#slayt-24), [Slayt 33](#slayt-33)

22. **Chandola, V., Banerjee, A., & Kumar, V. (2009). "Anomaly detection: A survey." *ACM Computing Surveys*.**
    - **Açıklama**: Ağ verilerinde statik limitlerin yetersiz kaldığı durumlarda kayan varyans ve Z-Score temelli anomali tespiti tekniklerinin incelenmesi.
    - **İlişkili Slaytlar**: [Slayt 24](#slayt-24), [Slayt 33](#slayt-33), [Slayt 64](#slayt-64)

23. **Keogh, E., & Lin, J. (2005). "Clustering of time-series subsequences is meaningless." *Data Mining and Knowledge Discovery*.**
    - **Açıklama**: Zaman serilerinde kayan pencere (sliding window) boyutlarının istatistiksel tutarlılık üzerindeki etkilerini analiz eden makale.
    - **İlişkili Slaytlar**: [Slayt 24](#slayt-24), [Slayt 32](#slayt-32)

24. **ONNX Runtime Dev Team. (2020). "ONNX Runtime: Cross-platform, high-performance ML inferencing." *Microsoft*.**
    - **Açıklama**: model.py motorumuzun Python ve webassembly katmanlarında hızlı çıkarım (1.12ms) yapmasını sağlayan ONNX kütüphanesi belgeleri.
    - **İlişkili Slaytlar**: [Slayt 25](#slayt-25), [Slayt 26](#slayt-26)

25. **Pedregosa, F., Varoquaux, G., et al. (2011). "Scikit-learn: Machine learning in Python." *JMLR*.**
    - **Açıklama**: Anomali tespit modelimizin veri standardizasyonunda ve Z-Score normalleştirmesinde kullandığımız kütüphane altyapısı.
    - **İlişkili Slaytlar**: [Slayt 24](#slayt-24), [Slayt 25](#slayt-25)

---

## 6. SOLIDITY AKILLI SÖZLEŞME GÜVENLİĞİ VE YENİDEN GİRİŞ (REENTRANCY) ANALİZLERİ

26. **Solidity Documentation. "Security Considerations: Reentrancy and the Checks-Effects-Interactions Pattern." *Ethereum Foundation*.**
    - **Açıklama**: Akıllı sözleşme geliştirmede harici çağrılardan (interactions) önce durum değişikliklerinin (effects) yazılmasını zorunlu kılan CEI kuralı.
    - **İlişkili Slaytlar**: [Slayt 6](#slayt-6), [Slayt 16](#slayt-16), [Slayt 67](#slayt-67)

27. **ConsenSys Diligence. (2020). "Ethereum Smart Contract Best Practices." *ConsenSys*.**
    - **Açıklama**: validateUserOp doğrulamalarında reentrancy mutex kilitleri ve gas optimizasyonu için en iyi kodlama pratikleri kılavuzu.
    - **İlişkili Slaytlar**: [Slayt 16](#slayt-16), [Slayt 43](#slayt-43), [Slayt 67](#slayt-67)

28. **Albert, E., Gordillo, P., Albert, S., & Rubio, A. (2020). "Gas-aware smart contract development." *IEEE Transactions on Software Engineering*.**
    - **Açıklama**: Solidity kontratlarında durum değişkenleri (storage) ile geçici bellek (memory) kullanımı arasındaki gaz farklarını inceleyen araştırma.
    - **İlişkili Slaytlar**: [Slayt 16](#slayt-16), [Slayt 22](#slayt-22), [Slayt 66](#slayt-66)

29. **Tsankov, P., Dan, A., Drachsler-Cohen, D., Gervais, A., Bünzli, F., & Vechev, M. (2018). "Securify: Practical security analysis of smart contracts." *ACM CCS*.**
    - **Açıklama**: Akıllı sözleşmelerde kontrol akış analizleri ve statik güvenlik kuralları doğrulaması yapan Securify aracının mimari yayını.
    - **İlişkili Slaytlar**: [Slayt 16](#slayt-16), [Slayt 43](#slayt-43)

30. **Torres, C. F., Baden, M., & State, R. (2021). "AEGIS: A tool for detecting reentrancy vulnerabilities." *IEEE Blockchain*.**
    - **Açıklama**: Çalışma zamanında (runtime) akıllı sözleşme işlemlerini izleyerek yeniden giriş (reentrancy) ataklarını anlık saptayan dinamik koruma modeli.
    - **İlişkili Slaytlar**: [Slayt 16](#slayt-16), [Slayt 67](#slayt-67)

---

## 7. DOŞ (DENIAL OF SERVICE) KORUMASI VE ASENKRON AĞ GEÇİDİ

31. **Bernstein, D. J. (2005). "SYN cookies." *cr.yp.to*.**
    - **Açıklama**: Sunucu işlemci gücünü tüketmeye çalışan sahte TCP bağlantılarına karşı stateless doğrulama yapan SYN çerezlerinin çalışma mantığı.
    - **İlişkili Slaytlar**: [Slayt 17](#slayt-17), [Slayt 32](#slayt-32)

32. **FastAPI Documentation. "Asynchronous concurrency with FastAPI and asyncio." *encode*.**
    - **Açıklama**: FastAPI geçidimizin asenkron yapısını, event-loop mekanizmasını ve asyncio.Queue entegrasyon kurallarını açıklayan belgeler.
    - **İlişkili Slaytlar**: [Slayt 7](#slayt-7), [Slayt 28](#slayt-28), [Slayt 56](#slayt-56)

33. **Redis Labs. (2021). "Redis Rate Limiting Patterns using Token Bucket." *Redis*.**
    - **Açıklama**: Dağıtık API ağlarında belirli IP adreslerinden gelen aşırı istekleri token bucket (jeton kovası) algoritmasıyla sınırlandırma şeması.
    - **İlişkili Slaytlar**: [Slayt 32](#slayt-32), [Slayt 61](#slayt-61)

34. **Kurose, J. F., & Ross, K. W. (2017). "Computer Networking: A Top-Down Approach." *Pearson*.**
    - **Açıklama**: Dağıtık siber saldırıların (DDoS/DoS) ağ katmanlarındaki tıkanma (congestion control) davranışlarını açıklayan temel ağ ders kitabı.
    - **İlişkili Slaytlar**: [Slayt 17](#slayt-17), [Slayt 61](#slayt-61)

35. **Grigorik, I. (2013). "High-Performance Browser Networking." *O'Reilly*.**
    - **Açıklama**: API ağ geçitlerinde gecikmeyi düşürmek, WebSocket bağlantılarını yönetmek ve HTTP 429 gibi sunucu durum kodlarını optimize etmek için rehber.
    - **İlişkili Slaytlar**: [Slayt 17](#slayt-17), [Slayt 32](#slayt-32), [Slayt 62](#slayt-62)

---

## 8. NTT (NUMBER THEORETIC TRANSFORM) ARİTMETİĞİ VE KAFES YAPILARINDA HIZLANDIRMA

36. **Langlois, A., & Stehlé, D. (2015). "Worst-case to average-case reductions for module lattices." *Designs, Codes and Cryptography*.**
    - **Açıklama**: MLWE tabanlı Module-LWE problemlerinin en kötü durum karmaşıklığı ile ortalama durum zorluğu arasındaki matematiksel dönüşümler.
    - **İlişkili Slaytlar**: [Slayt 34](#slayt-34), [Slayt 42](#slayt-42)

37. **Harvey, D. (2014). "Faster arithmetic for number-theoretic transforms." *Journal of Symbolic Computation*.**
    - **Açıklama**: Katsayı halkalarında NTT polinomsal çarpım adımlarını (Kelebek algoritması - Butterfly algorithm) hızlandıran aritmetik optimizasyonlar.
    - **İlişkili Slaytlar**: [Slayt 4](#slayt-4), [Slayt 34](#slayt-34), [Slayt 42](#slayt-42)

38. **Alkim, E., Bilgin, A., & Schwabe, P. (2017). "A sub-millisecond NTT implementation for lattice cryptography." *IACR Cryptology*.**
    - **Açıklama**: ARM ve x86 mimarilerinde NTT katsayı çarpım adımlarını paralel SIMD yönergeleriyle hızlandıran çekirdek çalışma.
    - **İlişkili Slaytlar**: [Slayt 35](#slayt-35), [Slayt 42](#slayt-42), [Slayt 65](#slayt-65)

39. **Lyubashevsky, V., Peikert, C., & Regev, O. (2010). "On ideal lattices and learning with errors over rings." *Eurocrypt*.**
    - **Açıklama**: İdeal kafesler (ideal lattices) üzerinde halka-LWE (Ring-LWE) yapısını tanımlayarak matris çarpım boyutlarını küçülten matematiksel yayın.
    - **İlişkili Slaytlar**: [Slayt 34](#slayt-34), [Slayt 42](#slayt-42)

40. **Bos, J. W., Ducas, L., Kiltz, E., Lepoint, T., Lyubashevsky, V., Schwabe, P., Seiler, G., & Stehlé, D. (2018). "Crystals - Kyber: A symmetric key encapsulation mechanism." *IEEE Transactions on Computers*.**
    - **Açıklama**: NIST Kategori 5 standardı olan ML-KEM (Kyber) anahtar kapsama mekanizmasının parametrelerini ve Dilithium ile olan donanımsal uyumunu analiz eden makale.
    - **İlişkili Slaytlar**: [Slayt 14](#slayt-14), [Slayt 23](#slayt-23)
