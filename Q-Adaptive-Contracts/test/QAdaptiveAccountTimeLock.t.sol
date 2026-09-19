// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/QAdaptiveAccount.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "./mocks/Mocks.sol";

/**
 * @title QAdaptiveAccountTimeLockTest
 * @notice Zaman kilidi, yüksek değerli transfer ve yönetim yolları.
 *
 * @dev Bu dosya, ilk tur testlerden sonra ölçülen dal kapsamı boşluklarını
 *      kapatmak için yazıldı. İlk ölçüm `QAdaptiveAccount` için %50,79 dal
 *      kapsamı gösteriyordu; kapsanmayan yolların çoğu burada.
 *
 *      Zaman kilidi, imza doğrulama hattından BAĞIMSIZ bir katmandır:
 *      `validateUserOp`'u kapılamaz, yalnızca `transferHighValue`'yu geciktirir.
 *      Bu ayrım test edilmezse ikisinin birbirine karıştığı bir regresyon
 *      fark edilmeden geçebilir.
 */
contract QAdaptiveAccountTimeLockTest is Test {
    QAdaptiveAccount account;
    MockAICore       aiCore;
    MockEntryPoint   entryPoint;
    GasBurner        hedef;

    address owner     = address(0xA11CE);
    address guardian  = address(0x6A5D);
    address alici     = address(0xBEEF);

    uint256 constant YUKSEK_DEGER = 5000 ether;

    function setUp() public {
        aiCore     = new MockAICore();
        entryPoint = new MockEntryPoint();
        hedef      = new GasBurner();

        account = new QAdaptiveAccount(
            address(entryPoint), address(aiCore), bytes32(uint256(0xDEAD)), owner, guardian
        );

        vm.deal(address(account), 20_000 ether);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Zaman Kilidi — Yüksek Değerli Transfer
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Eşiğin altındaki transfer kilide takılmadan geçiyor.
    function test_dusuk_degerli_transfer_kilide_takilmiyor() public {
        uint256 oncesi = alici.balance;

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, 1 ether);

        assertEq(alici.balance, oncesi + 1 ether, "Dusuk degerli transfer gerceklesmedi");
    }

    /**
     * @notice İlk çağrı transferi YAPMAZ, sıraya alır.
     *
     * Bu, zaman kilidinin çekirdeği: yüksek değerli bir transfer ilk denemede
     * gerçekleşmez, sahibe 2 saatlik iptal penceresi açılır.
     */
    function test_yuksek_degerli_transfer_ilk_cagrida_kilitleniyor() public {
        uint256 oncesi = alici.balance;
        bytes32 opHash = keccak256(abi.encode(alici, YUKSEK_DEGER));

        vm.expectEmit(true, false, false, false);
        emit QAdaptiveAccount.HighValueTransferLocked(opHash, alici, YUKSEK_DEGER, 0);

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        assertEq(alici.balance, oncesi, "Transfer ilk cagrida gerceklesti - kilit calismiyor");

        (uint256 executionTime, bool isActive) = account.lockedOperations(opHash);
        assertTrue(isActive, "Islem siraya alinmadi");
        assertEq(executionTime, block.timestamp + account.SECURITY_DELAY());
    }

    /// @notice Süre dolmadan yapılan ikinci çağrı reddediliyor.
    function test_sure_dolmadan_tekrar_denemesi_reddediliyor() public {
        vm.startPrank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        vm.warp(block.timestamp + 1 hours); // 2 saat gerekiyor

        vm.expectRevert("Q-ADAPTIVE: GUVENLIK RISKI! ISLEM 2 SAAT KILITLENDI.");
        account.transferHighValue(alici, YUKSEK_DEGER);
        vm.stopPrank();
    }

    /// @notice Süre dolduktan sonra transfer gerçekleşiyor.
    function test_sure_dolunca_transfer_gerceklesiyor() public {
        uint256 oncesi = alici.balance;

        vm.startPrank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        vm.warp(block.timestamp + account.SECURITY_DELAY());

        account.transferHighValue(alici, YUKSEK_DEGER);
        vm.stopPrank();

        assertEq(alici.balance, oncesi + YUKSEK_DEGER, "Sure dolunca transfer gerceklesmedi");
    }

    /// @notice Transfer sonrası kilit kapanıyor (tekrar kullanılamıyor).
    function test_transfer_sonrasi_kilit_kapaniyor() public {
        bytes32 opHash = keccak256(abi.encode(alici, YUKSEK_DEGER));

        vm.startPrank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);
        vm.warp(block.timestamp + account.SECURITY_DELAY());
        account.transferHighValue(alici, YUKSEK_DEGER);
        vm.stopPrank();

        (, bool isActive) = account.lockedOperations(opHash);
        assertFalse(isActive, "Kilit transfer sonrasi acik kaldi");
    }

    /// @notice Whitelist'teki hedefe yüksek transfer kilide takılmıyor.
    function test_whitelistteki_hedefe_yuksek_transfer_kilitlenmiyor() public {
        vm.prank(owner);
        account.addSafeDestination(alici);

        uint256 oncesi = alici.balance;

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        assertEq(alici.balance, oncesi + YUKSEK_DEGER, "Whitelist'teki hedef kilide takildi");
    }

    /// @notice Panik modunda whitelist dışı hedef reddediliyor.
    function test_panik_modunda_whitelist_disi_hedef_reddediliyor() public {
        aiCore.setStatus(9500, true);

        vm.prank(address(entryPoint));
        vm.expectRevert("QAdaptiveAccount: Target not whitelisted for Panic Mode");
        account.transferHighValue(alici, 1 ether);
    }

    /// @notice Panik modunda whitelist'teki hedef geçiyor.
    function test_panik_modunda_whitelistteki_hedef_geciyor() public {
        aiCore.setStatus(9500, true);

        vm.prank(owner);
        account.addSafeDestination(alici);

        uint256 oncesi = alici.balance;
        vm.prank(address(entryPoint));
        account.transferHighValue(alici, 1 ether);

        assertEq(alici.balance, oncesi + 1 ether);
    }

    /// @notice Başarısız transfer revert ediyor (alıcı ETH kabul etmiyor).
    function test_basarisiz_transfer_revert_ediyor() public {
        // GasBurner'ın receive/fallback'i yok → ETH kabul etmez.
        vm.prank(address(entryPoint));
        vm.expectRevert("QAdaptiveAccount: transfer failed");
        account.transferHighValue(address(hedef), 1 ether);
    }

    /// @notice Yalnızca EntryPoint yüksek değerli transfer başlatabilir.
    function test_sadece_entrypoint_transfer_baslatabilir() public {
        vm.expectRevert();
        account.transferHighValue(alici, 1 ether);
    }

    /**
     * @notice DEĞİŞMEZ: eşik üstü transfer, süre dolmadan ASLA gerçekleşmez.
     */
    function testFuzz_esik_ustu_transfer_sure_dolmadan_gerceklesmiyor(
        uint96 miktar,
        uint32 bekleme
    ) public {
        uint256 tutar = bound(uint256(miktar), YUKSEK_DEGER, 10_000 ether);
        uint256 sure  = bound(uint256(bekleme), 0, account.SECURITY_DELAY() - 1);

        uint256 oncesi = alici.balance;

        vm.startPrank(address(entryPoint));
        account.transferHighValue(alici, tutar);   // kilitler
        vm.warp(block.timestamp + sure);
        try account.transferHighValue(alici, tutar) {
            // Süre dolmadan başarılı olmamalı.
            assertTrue(false, "Sure dolmadan transfer gerceklesti");
        } catch {}
        vm.stopPrank();

        assertEq(alici.balance, oncesi, "Bakiye degisti");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // İptal Mekanizması
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Sahip kilitlenmiş transferi iptal edebiliyor.
    function test_sahip_kilitli_transferi_iptal_edebiliyor() public {
        bytes32 opHash = keccak256(abi.encode(alici, YUKSEK_DEGER));

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        vm.prank(owner);
        account.cancelTransaction(opHash);

        (, bool isActive) = account.lockedOperations(opHash);
        assertFalse(isActive, "Iptal calismadi");
    }

    /// @notice İptalden sonra transfer yeniden kilitleniyor (hemen geçmiyor).
    function test_iptalden_sonra_transfer_yeniden_kilitleniyor() public {
        bytes32 opHash = keccak256(abi.encode(alici, YUKSEK_DEGER));
        uint256 oncesi = alici.balance;

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        vm.prank(owner);
        account.cancelTransaction(opHash);

        vm.warp(block.timestamp + account.SECURITY_DELAY() * 2);

        // İptal edildiği için yeniden sıraya alınmalı, transfer olmamalı.
        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        assertEq(alici.balance, oncesi, "Iptal edilen islem bekleme olmadan gecti");
    }

    /// @notice Sahip, sıraya alınmış reddedilmiş işlemi de iptal edebiliyor.
    function test_sahip_siraya_alinmis_reddedisi_iptal_edebiliyor() public {
        bytes32 opHash = bytes32(uint256(0xFEED));

        vm.startPrank(owner);
        account.stageForReview(opHash);
        account.cancelTransaction(opHash);
        vm.stopPrank();

        (, bool isActive) = account.pendingTransactions(opHash);
        assertFalse(isActive, "Siraya alinmis reddedis iptal edilemedi");
    }

    /// @notice Aktif olmayan bir işlemin iptali reddediliyor.
    function test_aktif_olmayan_islem_iptali_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert();
        account.cancelTransaction(bytes32(uint256(0xC0FFEE)));
    }

    /// @notice Yalnızca sahip iptal edebilir.
    function test_sadece_sahip_iptal_edebilir() public {
        bytes32 opHash = keccak256(abi.encode(alici, YUKSEK_DEGER));

        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        vm.prank(address(0xBAD));
        vm.expectRevert();
        account.cancelTransaction(opHash);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Yönetim Fonksiyonları
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Eşik güncellemesi geçerli aralıkta çalışıyor.
    function test_esik_guncellemesi_calisiyor() public {
        vm.prank(owner);
        account.updateRollingRiskThreshold(8000);
        assertEq(account.rollingRiskThreshold(), 8000);
    }

    /// @notice Aralık dışındaki eşik reddediliyor.
    function test_aralik_disi_esik_reddediliyor() public {
        vm.startPrank(owner);

        vm.expectRevert("QAdaptiveAccount: threshold out of valid range [5500, 9000]");
        account.updateRollingRiskThreshold(5499);

        vm.expectRevert("QAdaptiveAccount: threshold out of valid range [5500, 9000]");
        account.updateRollingRiskThreshold(9001);

        // Sınırlar dahil olmalı.
        account.updateRollingRiskThreshold(5500);
        account.updateRollingRiskThreshold(9000);
        vm.stopPrank();
    }

    /// @notice DEĞİŞMEZ: eşik hiçbir zaman geçerli aralığın dışına çıkamaz.
    function testFuzz_esik_gecerli_araligin_disina_cikamiyor(uint256 deger) public {
        vm.prank(owner);
        try account.updateRollingRiskThreshold(deger) {
            uint256 guncel = account.rollingRiskThreshold();
            assertGe(guncel, 5500);
            assertLe(guncel, 9000);
        } catch {
            // Aralık dışı değerlerin reddedilmesi beklenen davranış.
            assertTrue(deger < 5500 || deger > 9000, "Gecerli deger reddedildi");
        }
    }

    /// @notice Whitelist ekleme ve çıkarma çalışıyor.
    function test_whitelist_ekleme_cikarma() public {
        vm.startPrank(owner);

        account.addSafeDestination(alici);
        assertTrue(account.safeDestinationWhitelist(alici));

        account.removeSafeDestination(alici);
        assertFalse(account.safeDestinationWhitelist(alici));

        vm.stopPrank();
    }

    /// @notice Yalnızca sahip whitelist değiştirebilir.
    function test_sadece_sahip_whitelist_degistirebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert();
        account.addSafeDestination(alici);
    }

    /// @notice Zırh taban yükseltmesi geçersiz sırayı reddediyor.
    function test_gecersiz_taban_sirasi_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptiveAccount: unknown baseline rank");
        account.raiseArmorBaseline(4);
    }

    /// @notice Zaman kilidi imza doğrulamasını KAPILAMIYOR.
    /// @dev İkisi bağımsız katmanlar; karışırlarsa bu test kırılır.
    function test_zaman_kilidi_imza_dogrulamasini_engellemiyor() public {
        aiCore.setStatus(1000, false);

        // Yüksek değerli bir transferi sıraya al.
        vm.prank(address(entryPoint));
        account.transferHighValue(alici, YUKSEK_DEGER);

        // Kilit aktifken doğrulama normal çalışmalı.
        QAdaptiveAccount.AirVerificationMetadata memory bos;
        QAdaptiveAccount.GuardianAttestation memory att =
            QAdaptiveAccount.GuardianAttestation(0, 0, "");

        UserOperation memory op;
        op.sender    = address(account);
        op.signature = abi.encode(new bytes(0), bos, uint256(1000), att);

        vm.prank(address(entryPoint));
        uint256 sonuc = account.validateUserOp(op, bytes32(uint256(1)), 0);

        assertEq(
            sonuc, account.SIG_VALIDATION_SUCCESS(),
            "Zaman kilidi imza dogrulamasini engelledi"
        );
    }
}
