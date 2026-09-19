// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/QAdaptiveAccount.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "./mocks/Mocks.sol";

/**
 * @title QAdaptiveAccountTest
 * @notice BULGU 6 ve hatalar E1, E3, E4, E7 için regresyon testleri.
 */
contract QAdaptiveAccountTest is Test {
    QAdaptiveAccount account;
    MockAICore       aiCore;
    MockEntryPoint   entryPoint;
    GasBurner        burner;

    address owner = address(0xA11CE);

    uint256 guardianKey = 0xA11CE5EC4E7;
    address guardian;

    bytes32 constant INITIAL_KEY = bytes32(uint256(0xDEAD));

    function setUp() public {
        guardian   = vm.addr(guardianKey);
        aiCore     = new MockAICore();
        entryPoint = new MockEntryPoint();
        burner     = new GasBurner();

        account = new QAdaptiveAccount(
            address(entryPoint),
            address(aiCore),
            INITIAL_KEY,
            owner,
            guardian
        );

        vm.deal(address(account), 10 ether);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Yardımcılar
    // ─────────────────────────────────────────────────────────────────────────

    function _emptyMetadata() internal pure returns (QAdaptiveAccount.AirVerificationMetadata memory m) {
        // Tüm alanlar sıfır; panik modu kapalıyken AIR kontrolü çalışmaz.
    }

    function _attestation(uint256 score, uint256 validUntil, bytes memory sig)
        internal
        pure
        returns (QAdaptiveAccount.GuardianAttestation memory)
    {
        return QAdaptiveAccount.GuardianAttestation({
            riskScore : score,
            validUntil: validUntil,
            signature : sig
        });
    }

    /// @dev Boş (imzasız) attestation — ORACLE modunda yeterli.
    function _noAttestation()
        internal
        pure
        returns (QAdaptiveAccount.GuardianAttestation memory)
    {
        return _attestation(0, 0, "");
    }

    function _signature(
        uint256 claimedScore,
        QAdaptiveAccount.GuardianAttestation memory att
    ) internal pure returns (bytes memory) {
        return abi.encode(new bytes(0), _emptyMetadata(), claimedScore, att);
    }

    function _op(bytes memory signature) internal view returns (UserOperation memory op) {
        op.sender    = address(account);
        op.signature = signature;
    }

    function _validate(bytes memory signature, uint256 missingFunds)
        internal
        returns (uint256)
    {
        vm.prank(address(entryPoint));
        return account.validateUserOp(_op(signature), bytes32(uint256(0xABC)), missingFunds);
    }

    /// @dev Guardian'ın imzaladığı attestation üretir.
    function _guardianAttestation(uint256 score, uint256 validUntil)
        internal
        view
        returns (QAdaptiveAccount.GuardianAttestation memory)
    {
        bytes32 digest = account.attestationDigest(bytes32(uint256(0xABC)), score, validUntil);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(guardianKey, digest);
        return _attestation(score, validUntil, abi.encodePacked(r, s, v));
    }

    // ═════════════════════════════════════════════════════════════════════════
    // BULGU 6 — Risk skoru gönderenin imza alanından okunuyordu
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice SÖMÜRÜ SENARYOSUNUN KENDİSİ.
     *
     * Oracle riski 9000 (=%90) diyor, yani eşiğin (7500) üstünde.
     * Gönderen imza alanına 0 yazıyor. Eski kod bu 0'ı okuyup kapıdan
     * geçiriyordu. Artık iddia yok sayılıyor ve işlem reddediliyor.
     */
    function test_BULGU6_iddia_edilen_sifir_risk_ai_kapisini_gecemiyor() public {
        aiCore.setStatus(9000, false);

        uint256 result = _validate(_signature(0, _noAttestation()), 0);

        assertEq(
            result, account.SIG_VALIDATION_FAILED(),
            "Iddia edilen sifir risk kapiyi gecti - BULGU 6 geri geldi"
        );
    }

    /// @notice Oracle düşük risk derse işlem geçmeli (yanlış pozitif kontrolü).
    function test_oracle_dusuk_risk_derse_islem_geciyor() public {
        aiCore.setStatus(1000, false);

        uint256 result = _validate(_signature(1000, _noAttestation()), 0);
        assertEq(result, account.SIG_VALIDATION_SUCCESS(), "Dusuk riskte islem reddedildi");
    }

    /**
     * @notice Gönderenin iddiası ile gerçek skor ayrışınca olay zincire yazılıyor.
     */
    function test_BULGU6_sapma_olayi_zincire_yaziliyor() public {
        aiCore.setStatus(1000, false);

        vm.expectEmit(true, false, false, true);
        emit QAdaptiveAccount.RiskScoreClaimMismatch(bytes32(uint256(0xABC)), 0, 1000);

        _validate(_signature(0, _noAttestation()), 0);
    }

    /**
     * @notice Guardian imzası gerçekten doğrulanıyor.
     */
    function test_BULGU6_gecerli_guardian_imzasi_kabul_ediliyor() public {
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);

        aiCore.setStatus(9999, false); // oracle yüksek der ama kaynak guardian

        QAdaptiveAccount.GuardianAttestation memory att =
            _guardianAttestation(1000, block.timestamp + 1 hours);

        uint256 result = _validate(_signature(1000, att), 0);
        assertEq(result, account.SIG_VALIDATION_SUCCESS(), "Gecerli guardian imzasi reddedildi");
    }

    /**
     * @notice Sahte guardian imzası reddediliyor.
     */
    function test_BULGU6_sahte_guardian_imzasi_reddediliyor() public {
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);

        uint256 sahteKey = 0xBADBAD;
        bytes32 digest = account.attestationDigest(
            bytes32(uint256(0xABC)), 0, block.timestamp + 1 hours
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sahteKey, digest);

        QAdaptiveAccount.GuardianAttestation memory att =
            _attestation(0, block.timestamp + 1 hours, abi.encodePacked(r, s, v));

        uint256 result = _validate(_signature(0, att), 0);
        assertEq(
            result, account.SIG_VALIDATION_FAILED(),
            "Sahte guardian imzasi kabul edildi"
        );
    }

    /// @notice Süresi geçmiş attestation reddediliyor.
    function test_BULGU6_suresi_gecmis_attestation_reddediliyor() public {
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);

        vm.warp(1000);
        QAdaptiveAccount.GuardianAttestation memory att = _guardianAttestation(0, 999);

        uint256 result = _validate(_signature(0, att), 0);
        assertEq(result, account.SIG_VALIDATION_FAILED(), "Suresi gecmis attestation kabul edildi");
    }

    /**
     * @notice HIGHEST_OF_BOTH — hiçbir kaynak riski DÜŞÜREMEZ.
     *
     * Guardian düşük (1000), oracle yüksek (9000) derse büyüğü alınmalı,
     * yani işlem reddedilmeli.
     */
    function test_BULGU6_ikisinin_buyugu_riski_dusurmeye_izin_vermiyor() public {
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.HIGHEST_OF_BOTH);

        aiCore.setStatus(9000, false);
        QAdaptiveAccount.GuardianAttestation memory att =
            _guardianAttestation(1000, block.timestamp + 1 hours);

        uint256 result = _validate(_signature(1000, att), 0);
        assertEq(
            result, account.SIG_VALIDATION_FAILED(),
            "Dusuk guardian skoru yuksek oracle skorunu bastirdi"
        );
    }

    /**
     * @notice DEĞİŞMEZ: gönderenin iddia ettiği skor kararı ETKİLEMEZ.
     *
     * Oracle sabit yüksek; iddia ne olursa olsun sonuç değişmemeli.
     */
    function testFuzz_BULGU6_iddia_edilen_skor_karari_etkilemiyor(uint256 iddia) public {
        aiCore.setStatus(9000, false);

        uint256 result = _validate(_signature(iddia, _noAttestation()), 0);
        assertEq(
            result, account.SIG_VALIDATION_FAILED(),
            "Iddia edilen skor karari etkiledi"
        );
    }

    /// @notice DEĞİŞMEZ: oracle düşükken iddia yüksek olsa da işlem geçer.
    function testFuzz_BULGU6_yuksek_iddia_dusuk_oracle_karari_etkilemiyor(uint256 iddia) public {
        aiCore.setStatus(100, false);

        uint256 result = _validate(_signature(iddia, _noAttestation()), 0);
        assertEq(
            result, account.SIG_VALIDATION_SUCCESS(),
            "Iddia edilen skor karari etkiledi"
        );
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HATA E1 — Ön-fonlama 2300 gaz stipend'i ile yapılıyordu
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice Ön-fonlama GERÇEK bir EntryPoint'e ulaşıyor.
     *
     * MockEntryPoint'in `receive()`'ı kasıtlı olarak İKİ SSTORE yapar —
     * gerçek EntryPoint'in mevduat muhasebesi gibi. 2300 gaz stipend'i bunların
     * ilkine bile yetmez, dolayısıyla eski kod burada `require(success)` ile
     * revert ederdi. Yani eski hesap canlı ağda hiçbir işlemi tamamlayamazdı.
     */
    function test_E1_on_fonlama_gercek_entrypointe_ulasiyor() public {
        aiCore.setStatus(1000, false);

        uint256 prefund = 0.1 ether;
        uint256 result  = _validate(_signature(1000, _noAttestation()), prefund);

        assertEq(result, account.SIG_VALIDATION_SUCCESS(), "On-fonlamali islem revert etti");
        assertEq(entryPoint.fundingCount(), 1, "EntryPoint receive() calismadi");
        assertEq(entryPoint.lastPrefund(), prefund, "On-fonlama miktari ulasmadi");
        assertEq(address(entryPoint).balance, prefund, "EntryPoint bakiyesi artmadi");
    }

    /// @notice Ön-fonlama sıfırsa çağrı hiç yapılmamalı.
    function test_E1_sifir_on_fonlamada_cagri_yapilmiyor() public {
        aiCore.setStatus(1000, false);
        _validate(_signature(1000, _noAttestation()), 0);
        assertEq(entryPoint.fundingCount(), 0, "Sifir on-fonlamada cagri yapildi");
    }

    /// @notice DEĞİŞMEZ: her makul ön-fonlama miktarı EntryPoint'e tam ulaşır.
    function testFuzz_E1_on_fonlama_tam_ulasiyor(uint96 miktar) public {
        uint256 prefund = bound(uint256(miktar), 1, 5 ether);
        aiCore.setStatus(1000, false);

        uint256 result = _validate(_signature(1000, _noAttestation()), prefund);

        assertEq(result, account.SIG_VALIDATION_SUCCESS());
        assertEq(address(entryPoint).balance, prefund, "On-fonlama eksik ulasti");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HATA E3 — validateUserOp doğrulama sırasında depolamaya yazıyordu
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice Reddedilen işlem DEPOLAMAYA YAZMIYOR.
     *
     * Eskiden her reddediş `pendingTransactions`'a bir SSTORE yapıyordu:
     *   • ERC-7562 ihlali (bundler'lar böyle işlemi mempool'a almaz),
     *   • saldırgana ucuz depolama şişirme vektörü.
     */
    function test_E3_reddedilen_islem_depolamaya_yazilmiyor() public {
        aiCore.setStatus(9000, false);
        bytes32 opHash = bytes32(uint256(0xABC));

        uint256 result = _validate(_signature(0, _noAttestation()), 0);
        assertEq(result, account.SIG_VALIDATION_FAILED());

        (, bool isActive) = account.pendingTransactions(opHash);
        assertFalse(isActive, "Reddedilen islem depolamaya yazildi - HATA E3 geri geldi");
    }

    /// @notice Kısa imza reddedişi de depolamaya yazmamalı.
    function test_E3_kisa_imza_reddedisi_depolamaya_yazmiyor() public {
        vm.prank(address(entryPoint));
        UserOperation memory op;
        op.sender    = address(account);
        op.signature = hex"1234";
        uint256 result = account.validateUserOp(op, bytes32(uint256(0xABC)), 0);

        assertEq(result, account.SIG_VALIDATION_FAILED());
        (, bool isActive) = account.pendingTransactions(bytes32(uint256(0xABC)));
        assertFalse(isActive, "Kisa imza reddedisi depolamaya yazildi");
    }

    /**
     * @notice DEĞİŞMEZ: kaç reddediş olursa olsun tek bir depolama girdisi oluşmaz.
     *
     * Depolama şişirme DoS vektörünün kapandığını sınar.
     */
    function test_E3_tekrarlanan_reddedis_depolama_sisirmiyor() public {
        aiCore.setStatus(9000, false);

        for (uint256 i = 0; i < 50; i++) {
            vm.prank(address(entryPoint));
            UserOperation memory op = _op(_signature(0, _noAttestation()));
            account.validateUserOp(op, bytes32(i), 0);

            (, bool isActive) = account.pendingTransactions(bytes32(i));
            assertFalse(isActive, "Reddedis depolamaya yazildi");
        }
    }

    /// @notice Sahip yine de açıkça sıraya alabiliyor.
    function test_E3_sahip_acikca_siraya_alabiliyor() public {
        bytes32 opHash = bytes32(uint256(0xFEED));

        vm.prank(owner);
        account.stageForReview(opHash);

        (, bool isActive) = account.pendingTransactions(opHash);
        assertTrue(isActive, "Sahibin acik siraya almasi calismadi");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HATA E4 — Tek yönlü tırmanma zincirde yoktu
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice Zırh DÜŞÜRÜLEMİYOR.
     *
     * Eskiden `updateQuantumArmor` kontrolsüz yazıyordu; EntryPoint yoluyla
     * gelen bir çağrı zırhı ML-DSA-87'den ML-DSA-44'e düşürebiliyordu.
     */
    function test_E4_tirmanma_dusurmeyi_engelliyor() public {
        vm.startPrank(address(entryPoint));

        account.updateQuantumArmor("ML-DSA-87 (Dilithium-5)", bytes32(uint256(1)));
        assertEq(account.currentArmorRank(), 3);

        vm.expectRevert("QAdaptiveAccount: armor escalation is one-way");
        account.updateQuantumArmor("ML-DSA-44", bytes32(uint256(2)));

        vm.stopPrank();

        assertEq(account.currentArmorRank(), 3, "Zirh dusuruldu - HATA E4 geri geldi");
    }

    /// @notice Yükseltme çalışıyor.
    function test_E4_tirmanma_yukseltmeye_izin_veriyor() public {
        vm.startPrank(address(entryPoint));
        account.updateQuantumArmor("ML-DSA-44", bytes32(uint256(1)));
        assertEq(account.currentArmorRank(), 1);
        account.updateQuantumArmor("ML-DSA-65", bytes32(uint256(2)));
        assertEq(account.currentArmorRank(), 2);
        account.updateQuantumArmor("ML-DSA-87 (Dilithium-5)", bytes32(uint256(3)));
        assertEq(account.currentArmorRank(), 3);
        vm.stopPrank();
    }

    /// @notice Aynı kademeye tekrar yazmak (anahtar rotasyonu) serbest.
    function test_E4_ayni_kademede_anahtar_rotasyonu_serbest() public {
        vm.startPrank(address(entryPoint));
        account.updateQuantumArmor("ML-DSA-65", bytes32(uint256(1)));
        account.updateQuantumArmor("ML-DSA-65", bytes32(uint256(2)));
        vm.stopPrank();

        assertEq(account.quantumPublicKey(), bytes32(uint256(2)), "Anahtar rotasyonu calismadi");
    }

    /// @notice Bilinmeyen kademe adı sessizce kabul edilmiyor.
    function test_E4_bilinmeyen_kademe_reddediliyor() public {
        vm.prank(address(entryPoint));
        vm.expectRevert("QAdaptiveAccount: unknown armor tier");
        account.updateQuantumArmor("ML-DSA-999", bytes32(uint256(1)));
    }

    /// @notice Düşürmenin tek yolu sahibin açık çağrısı.
    function test_E4_sadece_sahip_dusurebiliyor() public {
        vm.prank(address(entryPoint));
        account.updateQuantumArmor("ML-DSA-87 (Dilithium-5)", bytes32(uint256(1)));

        vm.prank(owner);
        account.downgradeArmor("ML-DSA-44", bytes32(uint256(2)));

        assertEq(account.currentArmorRank(), 1, "Sahibin dusurmesi calismadi");
    }

    /// @notice Taban altına asla inilemiyor.
    function test_E4_taban_altina_inilemiyor() public {
        vm.prank(owner);
        account.raiseArmorBaseline(2); // ML-DSA-65

        assertEq(account.currentArmorRank(), 2, "Taban yukselince mevcut zirh cekilmedi");

        vm.prank(owner);
        vm.expectRevert("QAdaptiveAccount: tier below armor baseline");
        account.downgradeArmor("ML-DSA-44", bytes32(uint256(2)));
    }

    /// @notice Taban da tek yönlü.
    function test_E4_taban_tek_yonlu() public {
        vm.startPrank(owner);
        account.raiseArmorBaseline(2);

        vm.expectRevert("QAdaptiveAccount: baseline is one-way");
        account.raiseArmorBaseline(1);
        vm.stopPrank();
    }

    /**
     * @notice DEĞİŞMEZ: zırh sırası hiçbir çağrı dizisinde AZALMAZ.
     */
    function testFuzz_E4_zirh_monoton_artiyor(uint8[8] calldata secimler) public {
        string[4] memory kademeler = [
            "Standard", "ML-DSA-44", "ML-DSA-65", "ML-DSA-87 (Dilithium-5)"
        ];

        uint8 oncekiSira = account.currentArmorRank();

        for (uint256 i = 0; i < 8; i++) {
            uint256 idx = secimler[i] % 4;

            vm.prank(address(entryPoint));
            try account.updateQuantumArmor(kademeler[idx], bytes32(i + 1)) {
                // Başarılıysa sıra artmış veya aynı kalmış olmalı.
            } catch {
                // Reddedilmesi beklenen durum: düşürme girişimi.
            }

            uint8 yeniSira = account.currentArmorRank();
            assertGe(yeniSira, oncekiSira, "Zirh sirasi azaldi");
            oncekiSira = yeniSira;
        }
    }

    /**
     * @notice DEĞİŞMEZ: zırh asla tabanın altına inmez.
     */
    function testFuzz_E4_zirh_asla_tabanin_altina_inmiyor(uint8 taban, uint8[4] calldata secimler) public {
        uint8 hedefTaban = uint8(bound(uint256(taban), 1, 3));

        vm.prank(owner);
        account.raiseArmorBaseline(hedefTaban);

        string[4] memory kademeler = [
            "Standard", "ML-DSA-44", "ML-DSA-65", "ML-DSA-87 (Dilithium-5)"
        ];

        for (uint256 i = 0; i < 4; i++) {
            uint256 idx = secimler[i] % 4;

            vm.prank(address(entryPoint));
            try account.updateQuantumArmor(kademeler[idx], bytes32(i + 1)) {} catch {}

            vm.prank(owner);
            try account.downgradeArmor(kademeler[idx], bytes32(i + 1)) {} catch {}

            assertGe(
                account.currentArmorRank(), hedefTaban,
                "Zirh tabanin altina indi"
            );
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HATA E7 — execute() içinde gasleft() - 5000 taşması
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Normal `execute` çalışıyor.
    function test_E7_execute_calisiyor() public {
        aiCore.setStatus(1000, false);

        vm.prank(address(entryPoint));
        account.execute(address(burner), 0, abi.encodeWithSignature("setValue(uint256)", 42));

        assertEq(burner.value(), 42, "execute calismadi");
    }

    /**
     * @notice Düşük gazda anlamlı hata veriyor, panic(0x11) değil.
     *
     * Eski kod `gas: gasleft() - 5000` kullanıyordu; `gasleft() < 5000` olunca
     * Solidity 0.8'de çıkarma taşması olur ve asıl sebebi gizleyen bir
     * panic(0x11) ile revert ederdi.
     */
    function test_E7_dusuk_gazda_anlamli_hata() public {
        aiCore.setStatus(1000, false);

        bytes memory data = abi.encodeWithSignature("setValue(uint256)", 1);

        vm.prank(address(entryPoint));
        // 9000 gaz: require(gasleft() > 10_000) eşiğinin altında.
        (bool ok, bytes memory ret) = address(account).call{gas: 9000}(
            abi.encodeWithSignature("execute(address,uint256,bytes)", address(burner), 0, data)
        );

        assertFalse(ok, "Dusuk gazda cagri basarili oldu");
        // Panic(0x11) imzası: 0x4e487b71 + 0x11. Onun OLMADIĞINI sınıyoruz.
        if (ret.length >= 4) {
            bytes4 selector = bytes4(ret);
            assertTrue(
                selector != bytes4(0x4e487b71),
                "Aritmetik panic(0x11) donuyor - HATA E7 geri geldi"
            );
        }
    }

    /// @notice Panik modunda whitelist zorlanıyor.
    function test_panik_modunda_whitelist_zorlaniyor() public {
        aiCore.setStatus(9000, true);

        vm.prank(address(entryPoint));
        vm.expectRevert("QAdaptiveAccount: Target not whitelisted for Panic Mode");
        account.execute(address(burner), 0, abi.encodeWithSignature("setValue(uint256)", 1));

        vm.prank(owner);
        account.addSafeDestination(address(burner));

        vm.prank(address(entryPoint));
        account.execute(address(burner), 0, abi.encodeWithSignature("setValue(uint256)", 7));
        assertEq(burner.value(), 7, "Whitelist'e eklendikten sonra calismadi");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Erişim Kontrolü
    // ═════════════════════════════════════════════════════════════════════════

    function test_sadece_entrypoint_dogrulayabilir() public {
        vm.expectRevert();
        account.validateUserOp(_op(_signature(0, _noAttestation())), bytes32(0), 0);
    }

    function test_sadece_entrypoint_zirh_guncelleyebilir() public {
        vm.expectRevert();
        account.updateQuantumArmor("ML-DSA-44", bytes32(uint256(1)));
    }

    function test_sadece_sahip_risk_kaynagini_degistirebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert();
        account.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);
    }

    function test_sadece_sahip_guardian_degistirebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert();
        account.setGuardianSigner(address(0xBAD));
    }
}
