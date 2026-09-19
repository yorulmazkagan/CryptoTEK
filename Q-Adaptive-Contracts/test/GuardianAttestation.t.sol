// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/QAdaptiveAccount.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "./mocks/Mocks.sol";

/**
 * @title GuardianAttestationTest
 * @notice Python ↔ Solidity köprüsünün KANITI.
 *
 * @dev Bu test dosyası hiçbir imzayı kendisi üretmez. Okuduğu imzalar
 *      `Q-Adaptive-AI/src/attestation.py` tarafından üretilmiş GERÇEK
 *      imzalardır (`scripts/generate_guardian_fixture.py` ile fixture'a
 *      yazılır) ve burada GERÇEK sözleşmenin `ecrecover`'ına verilir.
 *
 *      Neden önemli: iki katmanın "aynı digest'i hesapladığını" iddia etmek
 *      kolaydır. Kanıtlamak için imzanın zincirden geçmesi gerekir. Digest
 *      hesabında tek bir bayt kayarsa — tip dizesinde bir harf, alan sırası,
 *      EIP-191 ön-eki, zincir kimliği — `ecrecover` başka bir adres döndürür
 *      ve bu testler kırılır.
 *
 *      Hesap, fixture'ın imzaladığı SABİT adrese `deployCodeTo` ile kurulur;
 *      çünkü hesap adresi digest'in içindedir ve Python imzayı atarken bu
 *      adresi bilmek zorundaydı.
 *
 *      Fixture'ı yeniden üretmek için:
 *        python3 scripts/generate_guardian_fixture.py
 */
contract GuardianAttestationTest is Test {
    QAdaptiveAccount account;
    MockAICore       aiCore;
    MockEntryPoint   entryPoint;

    address constant ACCOUNT_ADDR = 0x00000000000000000000000000000000000aCC01;
    address owner = address(0xA11CE);

    string  fixtureJson;
    address guardianAddress;
    bytes32 userOpHash;

    function setUp() public {
        // Fixture'ın imzalandığı zincir kimliğini zorla.
        vm.chainId(31337);

        fixtureJson = vm.readFile("test/fixtures/guardian_attestation.json");

        guardianAddress = vm.parseJsonAddress(fixtureJson, ".guardianAddress");
        userOpHash      = vm.parseJsonBytes32(fixtureJson, ".userOpHash");

        // Fixture'daki hesap adresinin beklediğimizle aynı olduğunu sabitle.
        address fixtureAccount = vm.parseJsonAddress(fixtureJson, ".accountAddress");
        assertEq(fixtureAccount, ACCOUNT_ADDR, "Fixture farkli bir hesap adresi icin uretilmis");

        aiCore     = new MockAICore();
        entryPoint = new MockEntryPoint();

        // Sözleşmeyi fixture'ın imzaladığı TAM adrese kur.
        deployCodeTo(
            "QAdaptiveAccount.sol:QAdaptiveAccount",
            abi.encode(
                address(entryPoint),
                address(aiCore),
                bytes32(uint256(0xDEAD)),
                owner,
                guardianAddress
            ),
            ACCOUNT_ADDR
        );
        account = QAdaptiveAccount(payable(ACCOUNT_ADDR));

        // Risk kaynağını guardian imzasına çevir.
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);

        vm.deal(ACCOUNT_ADDR, 10 ether);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Yardımcılar
    // ─────────────────────────────────────────────────────────────────────────

    function _case(string memory ad)
        internal
        view
        returns (uint256 riskScore, uint256 validUntil, bytes32 digest, bytes memory signature)
    {
        string memory kok = string.concat(".cases[?(@.name=='", ad, "')]");
        riskScore  = vm.parseJsonUint(fixtureJson, string.concat(kok, ".riskScore"));
        validUntil = vm.parseJsonUint(fixtureJson, string.concat(kok, ".validUntil"));
        digest     = vm.parseJsonBytes32(fixtureJson, string.concat(kok, ".digest"));
        signature  = vm.parseJsonBytes(fixtureJson, string.concat(kok, ".signature"));
    }

    function _emptyMetadata()
        internal
        pure
        returns (QAdaptiveAccount.AirVerificationMetadata memory m)
    {}

    function _validateWith(
        uint256 riskScore,
        uint256 validUntil,
        bytes memory signature
    ) internal returns (uint256) {
        QAdaptiveAccount.GuardianAttestation memory att =
            QAdaptiveAccount.GuardianAttestation({
                riskScore : riskScore,
                validUntil: validUntil,
                signature : signature
            });

        UserOperation memory op;
        op.sender    = ACCOUNT_ADDR;
        op.signature = abi.encode(new bytes(0), _emptyMetadata(), riskScore, att);

        vm.prank(address(entryPoint));
        return account.validateUserOp(op, userOpHash, 0);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Digest Hizalaması — asıl kanıt
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice Python'un hesapladığı digest, sözleşmenin hesapladığıyla AYNI.
     *
     * Bu test, iki bağımsız Keccak-256 + ABI kodlama uygulamasının birebir
     * aynı sonucu ürettiğini sınar. Python tarafı `hashlib.sha3_256` değil
     * gerçek Keccak-256 kullanmak zorunda — ikisi farklı dolgu kullanır ve
     * bu test o karışıklığı yakalar.
     */
    function test_python_digesti_sozlesme_digestiyle_ayni() public view {
        string[4] memory adlar = ["dusuk_risk", "esik_altinda", "esik_ustunde", "yuksek_risk"];

        for (uint256 i = 0; i < adlar.length; i++) {
            (uint256 skor, uint256 validUntil, bytes32 pythonDigest, ) = _case(adlar[i]);

            bytes32 zincirDigest = account.attestationDigest(userOpHash, skor, validUntil);

            assertEq(
                pythonDigest, zincirDigest,
                string.concat("Digest ayristi: ", adlar[i])
            );
        }
    }

    /**
     * @notice Python'un imzası zincirde GERÇEKTEN doğrulanıyor.
     *
     * `ecrecover` fixture'daki guardian adresini geri vermezse işlem
     * reddedilir; bu testin geçmesi imzanın geçerli olduğunun kanıtıdır.
     */
    function test_python_imzasi_zincirde_dogrulaniyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        uint256 sonuc = _validateWith(skor, validUntil, sig);

        assertEq(
            sonuc, account.SIG_VALIDATION_SUCCESS(),
            "Python'un urettigi imza zincirde reddedildi"
        );
    }

    /// @notice Guardian adresi fixture ile sözleşmede aynı.
    function test_guardian_adresi_hizali() public view {
        assertEq(account.guardianSigner(), guardianAddress, "Guardian adresi ayristi");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Karar Doğruluğu — imzalı skor gerçekten kapıyı sürüyor
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Eşiğin bir altındaki imzalı skor geçiyor.
    function test_esik_altindaki_imzali_skor_geciyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("esik_altinda");
        assertEq(skor, 7_499);

        assertEq(
            _validateWith(skor, validUntil, sig),
            account.SIG_VALIDATION_SUCCESS(),
            "Esigin altindaki imzali skor reddedildi"
        );
    }

    /// @notice Eşiğin bir üstündeki imzalı skor reddediliyor.
    function test_esik_ustundeki_imzali_skor_reddediliyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("esik_ustunde");
        assertEq(skor, 7_501);

        assertEq(
            _validateWith(skor, validUntil, sig),
            account.SIG_VALIDATION_FAILED(),
            "Esigin ustundeki imzali skor kapiyi gecti"
        );
    }

    /// @notice Yüksek riskli imzalı skor reddediliyor.
    function test_yuksek_riskli_imzali_skor_reddediliyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("yuksek_risk");

        assertEq(
            _validateWith(skor, validUntil, sig),
            account.SIG_VALIDATION_FAILED(),
            "Yuksek riskli imzali skor kapiyi gecti"
        );
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Kurcalama Direnci — imza gerçekten bağlayıcı mı
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice İmza geçerli ama SKOR değiştirilirse reddediliyor.
     *
     * Saldırgan, yüksek riskli bir attestation'ın imzasını alıp skoru düşük
     * yazarsa digest değişir ve `ecrecover` başka bir adres döndürür.
     */
    function test_imza_gecerli_skor_degistirilmis_reddediliyor() public {
        (, uint256 validUntil, , bytes memory sig) = _case("yuksek_risk");

        // İmza 9500 için atıldı; 1000 iddia ediliyor.
        uint256 sonuc = _validateWith(1_000, validUntil, sig);

        assertEq(
            sonuc, account.SIG_VALIDATION_FAILED(),
            "Skoru degistirilmis attestation kabul edildi"
        );
    }

    /// @notice `validUntil` değiştirilirse reddediliyor.
    function test_validUntil_degistirilmis_reddediliyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        uint256 sonuc = _validateWith(skor, validUntil - 1, sig);
        assertEq(sonuc, account.SIG_VALIDATION_FAILED(), "validUntil kurcalamasi kabul edildi");
    }

    /// @notice İmzanın tek bir biti çevrilirse reddediliyor.
    function test_tek_bit_cevrilmis_imza_reddediliyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        sig[10] = bytes1(uint8(sig[10]) ^ 0x01);

        uint256 sonuc = _validateWith(skor, validUntil, sig);
        assertEq(sonuc, account.SIG_VALIDATION_FAILED(), "Kurcalanan imza kabul edildi");
    }

    /**
     * @notice Attestation BAŞKA BİR HESABA taşınamıyor.
     *
     * Digest hesap adresini içerdiği için, aynı imza farklı bir hesapta
     * doğrulanamaz.
     */
    function test_attestation_baska_hesaba_tasinamiyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        QAdaptiveAccount baskaHesap = new QAdaptiveAccount(
            address(entryPoint), address(aiCore), bytes32(uint256(1)), owner, guardianAddress
        );
        vm.prank(owner);
        baskaHesap.setRiskSource(QAdaptiveAccount.RiskSource.GUARDIAN_SIGNATURE);

        QAdaptiveAccount.GuardianAttestation memory att =
            QAdaptiveAccount.GuardianAttestation(skor, validUntil, sig);

        UserOperation memory op;
        op.sender    = address(baskaHesap);
        op.signature = abi.encode(new bytes(0), _emptyMetadata(), skor, att);

        vm.prank(address(entryPoint));
        uint256 sonuc = baskaHesap.validateUserOp(op, userOpHash, 0);

        assertEq(
            sonuc, baskaHesap.SIG_VALIDATION_FAILED(),
            "Attestation baska bir hesapta kabul edildi"
        );
    }

    /**
     * @notice Attestation BAŞKA BİR ZİNCİRE taşınamıyor.
     */
    function test_attestation_baska_zincire_tasinamiyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        vm.chainId(1); // fixture 31337 için imzalandı

        uint256 sonuc = _validateWith(skor, validUntil, sig);
        assertEq(sonuc, account.SIG_VALIDATION_FAILED(), "Attestation baska zincirde kabul edildi");
    }

    /**
     * @notice Attestation BAŞKA BİR UserOperation'a taşınamıyor.
     */
    function test_attestation_baska_userope_tasinamiyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        QAdaptiveAccount.GuardianAttestation memory att =
            QAdaptiveAccount.GuardianAttestation(skor, validUntil, sig);

        UserOperation memory op;
        op.sender    = ACCOUNT_ADDR;
        op.signature = abi.encode(new bytes(0), _emptyMetadata(), skor, att);

        vm.prank(address(entryPoint));
        // Farklı bir userOpHash ile aynı imza.
        uint256 sonuc = account.validateUserOp(op, bytes32(uint256(0xBEEF)), 0);

        assertEq(
            sonuc, account.SIG_VALIDATION_FAILED(),
            "Attestation baska bir UserOperation'a tasinabildi"
        );
    }

    /// @notice Süresi geçmiş attestation reddediliyor.
    function test_suresi_gecmis_attestation_reddediliyor() public {
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        vm.warp(validUntil + 1);

        uint256 sonuc = _validateWith(skor, validUntil, sig);
        assertEq(sonuc, account.SIG_VALIDATION_FAILED(), "Suresi gecmis attestation kabul edildi");
    }

    /**
     * @notice HIGHEST_OF_BOTH modunda guardian riski DÜŞÜREMİYOR.
     */
    function test_ikisinin_buyugu_modunda_guardian_riski_dusuremiyor() public {
        vm.prank(owner);
        account.setRiskSource(QAdaptiveAccount.RiskSource.HIGHEST_OF_BOTH);

        aiCore.setStatus(9_000, false); // oracle yüksek
        (uint256 skor, uint256 validUntil, , bytes memory sig) = _case("dusuk_risk");

        uint256 sonuc = _validateWith(skor, validUntil, sig);
        assertEq(
            sonuc, account.SIG_VALIDATION_FAILED(),
            "Dusuk guardian skoru yuksek oracle skorunu bastirdi"
        );
    }
}
