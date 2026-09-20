// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../contracts/QAdaptiveAICore.sol";

/**
 * @title QAdaptiveAICoreTest
 * @notice Risk oracle'ın testleri. Ağırlık bilinçli olarak **bayatlık**
 *         davranışında: oracle susarsa ne raporladığı, bu sözleşmenin tek
 *         gerçek tasarım kararıdır.
 */
contract QAdaptiveAICoreTest is Test {
    QAdaptiveAICore core;

    address owner   = address(0xA11CE);
    address updater = address(0xB0B);
    address yabanci = address(0xBAD);

    uint256 constant MAX_AGE = 1 hours;

    function setUp() public {
        // block.timestamp = 1 ile başlamak, `lastUpdate == 0` kontrolünün
        // gerçekten "hic guncellenmedi" anlamına geldiğini doğrulamayı sağlar.
        vm.warp(1);
        core = new QAdaptiveAICore(owner, updater, MAX_AGE);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Kurulum
    // ─────────────────────────────────────────────────────────────────────

    function test_kurucu_alanlari_ayarliyor() public view {
        assertEq(core.owner(), owner);
        assertEq(core.updater(), updater);
        assertEq(core.maxAge(), MAX_AGE);
    }

    function test_sifir_owner_reddediliyor() public {
        vm.expectRevert("QAdaptiveAICore: owner is zero");
        new QAdaptiveAICore(address(0), updater, MAX_AGE);
    }

    function test_sifir_updater_reddediliyor() public {
        vm.expectRevert("QAdaptiveAICore: updater is zero");
        new QAdaptiveAICore(owner, address(0), MAX_AGE);
    }

    function test_maxAge_sinirlari_zorlaniyor() public {
        vm.expectRevert("QAdaptiveAICore: maxAge out of range");
        new QAdaptiveAICore(owner, updater, 1 seconds);

        vm.expectRevert("QAdaptiveAICore: maxAge out of range");
        new QAdaptiveAICore(owner, updater, 8 days);
    }

    // ─────────────────────────────────────────────────────────────────────
    // BAYATLIK — bu sözleşmenin asıl konusu
    // ─────────────────────────────────────────────────────────────────────

    /// Yeni konuşlandırılmış oracle hiçbir şey ölçmemiştir. Risk 0 raporlamak
    /// en tehlikeli yönde yalan söylemek olurdu.
    function test_hic_guncellenmemis_oracle_BAYATTIR() public view {
        assertTrue(core.isStale(), "ilk blokta bayat olmali");

        (uint256 risk, bool panik) = core.getGlobalRiskStatus();
        assertEq(risk, core.MAX_RISK_SCORE(), "bayatken azami risk raporlanmali");
        assertFalse(panik, "bayatken panik ACILMAMALI");
    }

    /// Bayat oracle azami zırhı ister ama cüzdanı kilitlemez.
    function test_bayat_oracle_azami_risk_panik_KAPALI() public {
        vm.prank(updater);
        core.updateRiskStatus(1_000, true); // düşük risk + panik AÇIK

        // henüz taze: ne söylediyse o
        (uint256 r1, bool p1) = core.getGlobalRiskStatus();
        assertEq(r1, 1_000);
        assertTrue(p1);

        // pencereyi aş
        vm.warp(block.timestamp + MAX_AGE + 1);

        (uint256 r2, bool p2) = core.getGlobalRiskStatus();
        assertEq(r2, core.MAX_RISK_SCORE(), "bayatken azami riske cikmali");
        assertFalse(
            p2,
            "bayatken panik KAPALI kalmali - aksi halde zincir disi yigin "
            "coktugunde cuzdan tamamen kullanilamaz hale gelir"
        );
    }

    /// Sınırın tam üstünde bayat SAYILMAZ; bir saniye sonrası sayılır.
    function test_bayatlik_siniri_tam_noktasinda() public {
        vm.prank(updater);
        core.updateRiskStatus(5_000, false);

        vm.warp(block.timestamp + MAX_AGE);
        assertFalse(core.isStale(), "tam sinirda henuz bayat degil");

        vm.warp(block.timestamp + 1);
        assertTrue(core.isStale(), "sinirin 1 saniye otesi bayat");
    }

    /// Saldırgan updater'ı susturarak zırhı DÜŞÜREMEZ.
    function test_updateri_susturmak_zirhi_dusurmuyor() public {
        vm.prank(updater);
        core.updateRiskStatus(9_500, true); // yüksek risk

        vm.warp(block.timestamp + 365 days); // updater aylarca sussun

        (uint256 risk,) = core.getGlobalRiskStatus();
        assertEq(
            risk, core.MAX_RISK_SCORE(),
            "susturma saldirisi riski dusurmemeli - fail-open olurdu"
        );
    }

    function test_age_hic_guncellenmemisse_maksimum() public {
        assertEq(core.age(), type(uint256).max, "hic guncellenmemis = sonsuz yas");

        vm.prank(updater);
        core.updateRiskStatus(100, false);
        assertEq(core.age(), 0);

        vm.warp(block.timestamp + 42);
        assertEq(core.age(), 42);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Erişim kontrolü — mock'ta HİÇ yoktu
    // ─────────────────────────────────────────────────────────────────────

    function test_yabanci_risk_guncelleyemiyor() public {
        vm.prank(yabanci);
        vm.expectRevert("QAdaptiveAICore: caller is not updater");
        core.updateRiskStatus(10_000, true);
    }

    /// Sahip bile doğrudan risk yazamaz; roller ayrıdır.
    function test_owner_bile_risk_yazamiyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptiveAICore: caller is not updater");
        core.updateRiskStatus(10_000, true);
    }

    function test_yabanci_updater_degistiremiyor() public {
        vm.prank(yabanci);
        vm.expectRevert("QAdaptiveAICore: caller is not owner");
        core.setUpdater(yabanci);
    }

    function test_updater_kendini_owner_yapamiyor() public {
        vm.prank(updater);
        vm.expectRevert("QAdaptiveAICore: caller is not owner");
        core.transferOwnership(updater);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Aralık ve yönetim
    // ─────────────────────────────────────────────────────────────────────

    function test_aralik_disi_risk_reddediliyor() public {
        vm.prank(updater);
        vm.expectRevert("QAdaptiveAICore: risk out of range");
        core.updateRiskStatus(10_001, false);
    }

    function test_azami_risk_kabul_ediliyor() public {
        vm.prank(updater);
        core.updateRiskStatus(10_000, true);

        (uint256 risk, bool panik) = core.getGlobalRiskStatus();
        assertEq(risk, 10_000);
        assertTrue(panik);
    }

    function test_updater_rotasyonu() public {
        address yeni = address(0xC0FFEE);

        vm.prank(owner);
        core.setUpdater(yeni);
        assertEq(core.updater(), yeni);

        vm.prank(yeni);
        core.updateRiskStatus(2_500, false);
        (uint256 risk,) = core.getGlobalRiskStatus();
        assertEq(risk, 2_500);

        // eski updater artık yazamaz
        vm.prank(updater);
        vm.expectRevert("QAdaptiveAICore: caller is not updater");
        core.updateRiskStatus(0, false);
    }

    /// Sıfır updater kabul edilirse oracle bayat durumdan hiç çıkamaz.
    function test_updater_sifira_ayarlanamiyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptiveAICore: updater is zero");
        core.setUpdater(address(0));
    }

    function test_sahiplik_devri() public {
        address yeni = address(0xD00D);

        vm.prank(owner);
        core.transferOwnership(yeni);
        assertEq(core.owner(), yeni);

        vm.prank(owner);
        vm.expectRevert("QAdaptiveAICore: caller is not owner");
        core.setUpdater(yabanci);
    }

    function test_maxAge_degistirilebiliyor_ama_sinirli() public {
        vm.prank(owner);
        core.setMaxAge(2 hours);
        assertEq(core.maxAge(), 2 hours);

        vm.prank(owner);
        vm.expectRevert("QAdaptiveAICore: maxAge out of range");
        core.setMaxAge(30 seconds);

        vm.prank(owner);
        vm.expectRevert("QAdaptiveAICore: maxAge out of range");
        core.setMaxAge(30 days);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Fuzz
    // ─────────────────────────────────────────────────────────────────────

    /// Taze veri her zaman olduğu gibi raporlanır; bayat veri asla.
    function testFuzz_taze_veri_aynen_raporlaniyor(uint256 risk, bool panik) public {
        risk = bound(risk, 0, core.MAX_RISK_SCORE());

        vm.prank(updater);
        core.updateRiskStatus(risk, panik);

        (uint256 r, bool p) = core.getGlobalRiskStatus();
        assertEq(r, risk);
        assertEq(p, panik);
    }

    /// Ne kadar beklenirse beklensin, bayat sonuç hep aynı: azami risk, panik kapalı.
    function testFuzz_bayat_sonuc_bekleme_suresinden_bagimsiz(uint256 bekleme) public {
        bekleme = bound(bekleme, MAX_AGE + 1, 3650 days);

        vm.prank(updater);
        core.updateRiskStatus(0, false); // en düşük risk

        vm.warp(block.timestamp + bekleme);

        (uint256 r, bool p) = core.getGlobalRiskStatus();
        assertEq(r, core.MAX_RISK_SCORE());
        assertFalse(p);
    }
}
