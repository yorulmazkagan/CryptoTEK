// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/QAdaptivePaymaster.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "./mocks/Mocks.sol";

/**
 * @title QAdaptivePaymasterTest
 * @notice BULGU 5 ve BULGU 14 regresyon testleri.
 *
 * @dev Depoda daha önce TEK BİR Solidity testi yoktu (bulgu 8) — hâlbuki
 *      gerçek ve sömürülebilir bir fon kaybı açığı tam da burada duruyordu.
 */
contract QAdaptivePaymasterTest is Test {
    QAdaptivePaymaster  paymaster;
    MockEntryPoint      entryPoint;
    AttackerArmorContract attacker;

    address owner    = address(0xA11CE);
    address legitAccount = address(0xB0B);

    uint256 constant MAX_COST_PER_OP = 0.01 ether;
    uint256 constant ACCOUNT_QUOTA   = 0.05 ether;
    uint256 constant EPOCH_BUDGET    = 0.20 ether;
    uint256 constant EPOCH_DURATION  = 1 days;

    function setUp() public {
        entryPoint = new MockEntryPoint();
        attacker   = new AttackerArmorContract();

        vm.prank(owner);
        paymaster = new QAdaptivePaymaster(
            address(entryPoint),
            MAX_COST_PER_OP,
            ACCOUNT_QUOTA,
            EPOCH_BUDGET,
            EPOCH_DURATION
        );

        // Meşru hesabı kaydet.
        vm.prank(owner);
        paymaster.setAccountSponsorship(legitAccount, true);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Yardımcılar
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev Sponsorlanan seçiciye sahip bir UserOperation kurar.
    function _armorOp(address sender) internal pure returns (UserOperation memory op) {
        op.sender   = sender;
        op.callData = abi.encodeWithSignature(
            "updateQuantumArmor(string,bytes32)", "ML-DSA-87 (Dilithium-5)", bytes32(uint256(1))
        );
    }

    function _validate(UserOperation memory op, uint256 maxCost)
        internal
        returns (bytes memory context, uint256 validationData)
    {
        vm.prank(address(entryPoint));
        return paymaster.validatePaymasterUserOp(op, bytes32(uint256(7)), maxCost);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // BULGU 5 — Fon Kaybı Açığı
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice SÖMÜRÜ SENARYOSUNUN KENDİSİ.
     *
     * Saldırgan, sponsorlanan seçiciye sahip boş bir sözleşme deploy eder.
     * Eski kod yalnızca seçiciye baktığı için bu sözleşme sponsorluk ALIRDI.
     * Artık gönderen kaydı olmadığı için reddediliyor.
     */
    function test_BULGU5_saldirgan_sozlesmesi_sponsorluk_alamiyor() public {
        UserOperation memory op = _armorOp(address(attacker));

        (, uint256 validationData) = _validate(op, MAX_COST_PER_OP);

        assertEq(validationData, 1, "Kayitsiz saldirgan sponsorluk aldi - BULGU 5 geri geldi");
        assertEq(paymaster.currentTotalSpend(), 0, "Reddedilen islem butceden dusuldu");
    }

    /// @notice Meşru, kayıtlı hesap sponsorluk alabilmeli (yanlış pozitif kontrolü).
    function test_kayitli_hesap_sponsorluk_alabiliyor() public {
        UserOperation memory op = _armorOp(legitAccount);

        (bytes memory context, uint256 validationData) = _validate(op, MAX_COST_PER_OP);

        assertEq(validationData, 0, "Kayitli hesap reddedildi");
        assertGt(context.length, 0, "postOp icin baglam donmedi");
    }

    /// @notice Kayıt geri alınabiliyor mu?
    function test_kayit_geri_alinabiliyor() public {
        vm.prank(owner);
        paymaster.setAccountSponsorship(legitAccount, false);

        (, uint256 validationData) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(validationData, 1, "Kaydi silinen hesap hala sponsorluk aliyor");
    }

    /// @notice Sponsorlanmayan seçici reddedilmeli.
    function test_sponsorlanmayan_secici_reddediliyor() public {
        UserOperation memory op;
        op.sender   = legitAccount;
        op.callData = abi.encodeWithSignature("transfer(address,uint256)", address(1), 1);

        (, uint256 validationData) = _validate(op, MAX_COST_PER_OP);
        assertEq(validationData, 1, "Ilgisiz secici sponsorlandi");
    }

    /// @notice KAPI 2 — işlem tavanı.
    function test_BULGU5_islem_tavani_asilamiyor() public {
        (, uint256 validationData) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP + 1);
        assertEq(validationData, 1, "Tavanin ustundeki maliyet sponsorlandi");
    }

    /**
     * @notice KAPI 3 — hesap kotası tükenince duruyor.
     *
     * Kota 0.05, işlem tavanı 0.01 → en fazla 5 işlem geçmeli, 6.'sı durmalı.
     */
    function test_BULGU5_hesap_kotasi_tukeniyor_ve_duruyor() public {
        uint256 gecen;
        for (uint256 i = 0; i < 6; i++) {
            (, uint256 validationData) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
            if (validationData == 0) gecen++;
        }

        assertEq(gecen, 5, "Hesap kotasi beklenenden farkli sayida islem gecirdi");

        // 7.'si de geçmemeli.
        (, uint256 son) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(son, 1, "Kota tukendikten sonra islem gecti");
    }

    /**
     * @notice BULGU 5 — tekrarlanan saldırı bütçeyi tüketemiyor.
     *
     * Saldırgan 100 kez denese bile tek bir wei sponsorluk alamamalı.
     */
    function test_BULGU5_tekrarlanan_saldiri_butceyi_tuketmiyor() public {
        for (uint256 i = 0; i < 100; i++) {
            (, uint256 validationData) = _validate(_armorOp(address(attacker)), MAX_COST_PER_OP);
            assertEq(validationData, 1, "Saldirgan sponsorluk aldi");
        }

        assertEq(paymaster.currentTotalSpend(), 0, "Saldiri butceden harcama yapti");
        assertEq(
            paymaster.currentAccountSpend(address(attacker)), 0,
            "Saldirgana kota tahsis edildi"
        );
    }

    /**
     * @notice KAPI 4 — dönem bütçesi toplamı sınırlıyor.
     *
     * Bütçe 0.20, hesap kotası 0.05 → 4 farklı hesap bütçeyi tüketir, 5.'si durur.
     */
    function test_BULGU5_donem_butcesi_toplami_sinirliyor() public {
        address[5] memory hesaplar = [
            address(0x1001), address(0x1002), address(0x1003), address(0x1004), address(0x1005)
        ];

        for (uint256 i = 0; i < 5; i++) {
            vm.prank(owner);
            paymaster.setAccountSponsorship(hesaplar[i], true);
        }

        // Her hesap kotasını (5 × 0.01) doldursun.
        uint256 toplamGecen;
        for (uint256 i = 0; i < 5; i++) {
            for (uint256 j = 0; j < 5; j++) {
                (, uint256 vd) = _validate(_armorOp(hesaplar[i]), MAX_COST_PER_OP);
                if (vd == 0) toplamGecen++;
            }
        }

        // Bütçe 0.20 / tavan 0.01 = 20 işlem.
        assertEq(toplamGecen, 20, "Donem butcesi beklenenden farkli sayida islem gecirdi");
        assertEq(paymaster.currentTotalSpend(), EPOCH_BUDGET, "Butce tam dolmadi");
    }

    /// @notice Dönem dönünce kota ve bütçe tazeleniyor.
    function test_donem_donunce_kota_tazeleniyor() public {
        for (uint256 i = 0; i < 5; i++) {
            _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        }
        (, uint256 tukenmis) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(tukenmis, 1, "Kota tukenmemis");

        vm.warp(block.timestamp + EPOCH_DURATION + 1);

        assertEq(paymaster.currentAccountSpend(legitAccount), 0, "Yeni donemde harcama sifirlanmadi");
        (, uint256 yeniDonem) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(yeniDonem, 0, "Yeni donemde islem gecmedi");
    }

    /// @notice Yalnızca EntryPoint doğrulama çağırabilir.
    function test_sadece_entrypoint_dogrulayabilir() public {
        vm.expectRevert("QAdaptivePaymaster: caller must be EntryPoint");
        paymaster.validatePaymasterUserOp(_armorOp(legitAccount), bytes32(0), MAX_COST_PER_OP);
    }

    /// @notice Yalnızca sahip kayıt değiştirebilir.
    function test_sadece_sahip_kayit_degistirebilir() public {
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.setAccountSponsorship(address(attacker), true);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // BULGU 14 — Gerçek Mevduat ve postOp Uzlaşması
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Mevduat GERÇEKTEN EntryPoint'e gidiyor.
     *
     * Eski kod parayı sözleşmede tutup yalnızca bir olay yayınlıyordu; gövdede
     * "in a real implementation..." yorumu duruyordu. Bu test, EntryPoint'teki
     * bakiyenin arttığını sınar — olayın yayınlandığını değil.
     */
    function test_BULGU14_mevduat_gercekten_entrypointe_gidiyor() public {
        vm.deal(owner, 1 ether);

        assertEq(paymaster.entryPointDeposit(), 0, "Baslangic mevduati sifir degil");

        vm.prank(owner);
        paymaster.depositToEntryPoint{value: 0.5 ether}();

        assertEq(
            paymaster.entryPointDeposit(), 0.5 ether,
            "Mevduat EntryPoint'e ulasmadi - BULGU 14 geri geldi"
        );
        assertEq(address(paymaster).balance, 0, "Para paymaster'da kaldi");
    }

    /**
     * @notice postOp ön-rezervasyonu GERÇEK maliyetle uzlaştırıyor.
     *
     * Eski `postOp` gövdesi boştu. Uzlaşma olmadan her işlem tavan kadar
     * sayılır ve kota olması gerekenden çok daha hızlı tükenirdi.
     */
    function test_BULGU14_postOp_gercek_maliyetle_uzlasiyor() public {
        (bytes memory context, uint256 vd) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(vd, 0);

        // Doğrulama tavanı rezerve etti.
        assertEq(paymaster.currentAccountSpend(legitAccount), MAX_COST_PER_OP);

        // Gerçek maliyet tavanın dörtte biri çıktı.
        uint256 gercekMaliyet = MAX_COST_PER_OP / 4;
        vm.prank(address(entryPoint));
        paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, context, gercekMaliyet);

        assertEq(
            paymaster.currentAccountSpend(legitAccount), gercekMaliyet,
            "postOp farki iade etmedi - BULGU 14 geri geldi"
        );
        assertEq(paymaster.currentTotalSpend(), gercekMaliyet, "Donem toplami uzlasmadi");
    }

    /// @notice Uzlaşma sonrası kota gerçekten daha fazla işleme izin veriyor.
    function test_uzlasma_kotayi_serbest_birakiyor() public {
        // Beş işlem yap, hepsini ucuza uzlaştır.
        for (uint256 i = 0; i < 5; i++) {
            (bytes memory ctx, uint256 vd) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
            assertEq(vd, 0);
            vm.prank(address(entryPoint));
            paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, ctx, MAX_COST_PER_OP / 10);
        }

        // Uzlaşma olmasaydı kota dolmuş olurdu; şimdi yer var.
        (, uint256 vdSonra) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);
        assertEq(vdSonra, 0, "Uzlasmaya ragmen kota dolu gorunuyor");
    }

    /// @notice Yalnızca EntryPoint postOp çağırabilir.
    function test_sadece_entrypoint_postop_cagirabilir() public {
        (bytes memory ctx, ) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);

        vm.expectRevert("QAdaptivePaymaster: caller must be EntryPoint");
        paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, ctx, 1);
    }

    /// @notice Gerçek maliyet rezervasyondan büyükse muhasebe bozulmamalı.
    function test_gercek_maliyet_rezervasyonu_asarsa_bozulmuyor() public {
        (bytes memory ctx, ) = _validate(_armorOp(legitAccount), MAX_COST_PER_OP);

        vm.prank(address(entryPoint));
        paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, ctx, MAX_COST_PER_OP * 10);

        // İade yok; rezervasyon olduğu gibi kalmalı (negatife düşmemeli).
        assertEq(paymaster.currentAccountSpend(legitAccount), MAX_COST_PER_OP);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Fuzz / Değişmez Testleri
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice DEĞİŞMEZ: kayıtsız HİÇBİR adres sponsorluk alamaz.
     */
    function testFuzz_BULGU5_kayitsiz_adres_asla_sponsorluk_alamaz(
        address rastgele,
        uint256 maxCost
    ) public {
        vm.assume(rastgele != legitAccount);
        vm.assume(rastgele != address(0));
        maxCost = bound(maxCost, 0, MAX_COST_PER_OP);

        (, uint256 validationData) = _validate(_armorOp(rastgele), maxCost);
        assertEq(validationData, 1, "Kayitsiz adres sponsorluk aldi");
    }

    /**
     * @notice DEĞİŞMEZ: dönem harcaması bütçeyi ASLA aşamaz.
     */
    function testFuzz_BULGU5_donem_harcamasi_butceyi_asmiyor(uint256[10] calldata maliyetler) public {
        for (uint256 i = 0; i < 10; i++) {
            uint256 maliyet = bound(maliyetler[i], 0, MAX_COST_PER_OP);
            _validate(_armorOp(legitAccount), maliyet);

            assertLe(
                paymaster.currentTotalSpend(), EPOCH_BUDGET,
                "Donem harcamasi butceyi asti"
            );
            assertLe(
                paymaster.currentAccountSpend(legitAccount), ACCOUNT_QUOTA,
                "Hesap harcamasi kotayi asti"
            );
        }
    }

    /// @notice Limit güncellemeleri tutarlılığı zorluyor.
    function test_limit_guncellemesi_tutarsizligi_reddediyor() public {
        vm.startPrank(owner);

        vm.expectRevert("QAdaptivePaymaster: quota below per-op cap");
        paymaster.updateLimits(1 ether, 0.5 ether, 2 ether);

        vm.expectRevert("QAdaptivePaymaster: budget below account quota");
        paymaster.updateLimits(0.1 ether, 0.5 ether, 0.2 ether);

        // Tutarlı olan geçmeli.
        paymaster.updateLimits(0.1 ether, 0.5 ether, 1 ether);
        assertEq(paymaster.maxCostPerOperation(), 0.1 ether);

        vm.stopPrank();
    }
}
