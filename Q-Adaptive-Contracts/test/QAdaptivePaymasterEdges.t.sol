// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../contracts/QAdaptivePaymaster.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "./mocks/Mocks.sol";

/**
 * @title QAdaptivePaymasterEdgesTest
 * @notice Paymaster'ın sınır ve yönetim yolları.
 *
 * @dev İlk tur testlerden sonra ölçülen dal kapsamı %61,29 idi. Kapsanmayan
 *      yollar burada: dönem devri sırasında `postOp`, mevduat çekme, sıfır
 *      adres kontrolleri, kurucu doğrulamaları ve kısa calldata.
 */
contract QAdaptivePaymasterEdgesTest is Test {
    QAdaptivePaymaster paymaster;
    MockEntryPoint     entryPoint;

    address owner  = address(0xA11CE);
    address hesap  = address(0xB0B);
    address alici  = address(0xBEEF);

    uint256 constant MAX_COST_PER_OP = 0.01 ether;
    uint256 constant ACCOUNT_QUOTA   = 0.05 ether;
    uint256 constant EPOCH_BUDGET    = 0.20 ether;
    uint256 constant EPOCH_DURATION  = 1 days;

    function setUp() public {
        entryPoint = new MockEntryPoint();

        vm.prank(owner);
        paymaster = new QAdaptivePaymaster(
            address(entryPoint), MAX_COST_PER_OP, ACCOUNT_QUOTA, EPOCH_BUDGET, EPOCH_DURATION
        );

        vm.prank(owner);
        paymaster.setAccountSponsorship(hesap, true);
    }

    function _armorOp(address sender) internal pure returns (UserOperation memory op) {
        op.sender   = sender;
        op.callData = abi.encodeWithSignature(
            "updateQuantumArmor(string,bytes32)", "ML-DSA-87 (Dilithium-5)", bytes32(uint256(1))
        );
    }

    function _validate(address sender, uint256 maxCost)
        internal
        returns (bytes memory, uint256)
    {
        vm.prank(address(entryPoint));
        return paymaster.validatePaymasterUserOp(_armorOp(sender), bytes32(uint256(7)), maxCost);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Kurucu Doğrulamaları
    // ═════════════════════════════════════════════════════════════════════════

    function test_sifir_entrypoint_reddediliyor() public {
        vm.expectRevert("QAdaptivePaymaster: entryPoint is zero");
        new QAdaptivePaymaster(address(0), 1, 1, 1, 1);
    }

    function test_sifir_donem_suresi_reddediliyor() public {
        vm.expectRevert("QAdaptivePaymaster: epochDuration is zero");
        new QAdaptivePaymaster(address(entryPoint), 1, 1, 1, 0);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Kısa / Bozuk Calldata
    // ═════════════════════════════════════════════════════════════════════════

    function test_kisa_calldata_reddediliyor() public {
        UserOperation memory op;
        op.sender   = hesap;
        op.callData = hex"1234"; // 4 bayttan kısa

        vm.prank(address(entryPoint));
        (, uint256 vd) = paymaster.validatePaymasterUserOp(op, bytes32(0), MAX_COST_PER_OP);

        assertEq(vd, 1, "Kisa calldata sponsorlandi");
    }

    function test_bos_calldata_reddediliyor() public {
        UserOperation memory op;
        op.sender = hesap;

        vm.prank(address(entryPoint));
        (, uint256 vd) = paymaster.validatePaymasterUserOp(op, bytes32(0), MAX_COST_PER_OP);

        assertEq(vd, 1, "Bos calldata sponsorlandi");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // postOp Sınır Durumları
    // ═════════════════════════════════════════════════════════════════════════

    /// @notice Boş bağlamla çağrılan postOp sessizce dönüyor.
    function test_bos_baglamla_postop_sorunsuz() public {
        vm.prank(address(entryPoint));
        paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, "", 1);
        // Revert etmemeli; muhasebe değişmemeli.
        assertEq(paymaster.currentTotalSpend(), 0);
    }

    /**
     * @notice Dönem devrildikten sonra gelen postOp muhasebeyi bozmuyor.
     *
     * Uzun süren bir işlem dönem sınırını aşabilir. Bu durumda rezervasyon
     * zaten sıfırlanmış sayılır; geri verilecek bir şey yoktur. İade
     * yapılsaydı yeni dönemin harcaması yanlışlıkla eksiltilirdi.
     */
    function test_donem_devrinden_sonra_postop_muhasebeyi_bozmuyor() public {
        (bytes memory ctx, uint256 vd) = _validate(hesap, MAX_COST_PER_OP);
        assertEq(vd, 0);

        // Yeni döneme geç ve orada bir harcama yap.
        vm.warp(block.timestamp + EPOCH_DURATION + 1);
        (, uint256 vd2) = _validate(hesap, MAX_COST_PER_OP);
        assertEq(vd2, 0);

        uint256 yeniDonemHarcamasi = paymaster.currentTotalSpend();

        // Eski dönemin postOp'u şimdi geliyor.
        vm.prank(address(entryPoint));
        paymaster.postOp(QAdaptivePaymaster.PostOpMode.opSucceeded, ctx, 1);

        assertEq(
            paymaster.currentTotalSpend(), yeniDonemHarcamasi,
            "Eski donemin postOp'u yeni donem muhasebesini degistirdi"
        );
    }

    /// @notice postOp'un farklı modları da kabul ediliyor.
    function test_postop_reverted_modu_da_uzlasiyor() public {
        (bytes memory ctx, ) = _validate(hesap, MAX_COST_PER_OP);

        vm.prank(address(entryPoint));
        paymaster.postOp(
            QAdaptivePaymaster.PostOpMode.opReverted, ctx, MAX_COST_PER_OP / 2
        );

        assertEq(paymaster.currentAccountSpend(hesap), MAX_COST_PER_OP / 2);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Mevduat Yönetimi
    // ═════════════════════════════════════════════════════════════════════════

    function test_sifir_mevduat_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: zero deposit");
        paymaster.depositToEntryPoint{value: 0}();
    }

    function test_sadece_sahip_mevduat_yatirabilir() public {
        vm.deal(address(0xBAD), 1 ether);
        vm.prank(address(0xBAD));
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.depositToEntryPoint{value: 0.1 ether}();
    }

    function test_mevduat_cekilebiliyor() public {
        vm.deal(owner, 1 ether);

        vm.prank(owner);
        paymaster.depositToEntryPoint{value: 0.5 ether}();
        assertEq(paymaster.entryPointDeposit(), 0.5 ether);

        uint256 oncesi = alici.balance;

        vm.prank(owner);
        paymaster.withdrawFromEntryPoint(payable(alici), 0.2 ether);

        assertEq(alici.balance, oncesi + 0.2 ether, "Cekim aliciya ulasmadi");
        assertEq(paymaster.entryPointDeposit(), 0.3 ether, "Mevduat dusulmedi");
    }

    function test_sifir_adrese_cekim_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: withdraw to zero");
        paymaster.withdrawFromEntryPoint(payable(address(0)), 1);
    }

    function test_sadece_sahip_cekebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.withdrawFromEntryPoint(payable(alici), 1);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Kayıt Yönetimi
    // ═════════════════════════════════════════════════════════════════════════

    function test_sifir_adres_kaydi_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: account is zero");
        paymaster.setAccountSponsorship(address(0), true);
    }

    function test_sadece_sahip_limit_guncelleyebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.updateLimits(1, 1, 1);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Sahiplik ve Dönem Uzunluğu
    // ═════════════════════════════════════════════════════════════════════════
    //
    // Slither `owner` ve `epochDuration`'ın hiç yeniden atanmadığını, dolayısıyla
    // `immutable` yapılabileceğini bildirmişti. Doğru çözüm onları dondurmak
    // değil, gerçekten değiştirilebilir kılmaktı — mevduat yönetimi sahibe
    // bağlı ve `epochDuration` diğer üç limitin aksine güncellenemiyordu.

    function test_sahiplik_devredilebiliyor() public {
        address yeniSahip = address(0xC0FFEE);

        vm.prank(owner);
        paymaster.transferOwnership(yeniSahip);
        assertEq(paymaster.owner(), yeniSahip);

        // Yeni sahip yetkileri kullanabilmeli.
        vm.prank(yeniSahip);
        paymaster.setAccountSponsorship(address(0x1234), true);
        assertTrue(paymaster.sponsoredAccounts(address(0x1234)));

        // Eski sahip artık yetkisiz.
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.setAccountSponsorship(address(0x5678), true);
    }

    function test_sifir_adrese_devir_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: new owner is zero");
        paymaster.transferOwnership(address(0));
    }

    function test_sadece_sahip_devredebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.transferOwnership(address(0xBAD));
    }

    /// @notice Dönem uzunluğu güncellenebiliyor ve sayaç buna göre değişiyor.
    function test_donem_uzunlugu_guncellenebiliyor() public {
        assertEq(paymaster.epochIndex(), 0);

        vm.warp(block.timestamp + EPOCH_DURATION / 2);
        assertEq(paymaster.epochIndex(), 0, "yarim donemde hala 0 olmali");

        // Dönem uzunluğu yarıya inince aynı an artık 1. döneme düşer.
        vm.prank(owner);
        paymaster.setEpochDuration(EPOCH_DURATION / 2);

        assertEq(paymaster.epochDuration(), EPOCH_DURATION / 2);
        assertEq(paymaster.epochIndex(), 1, "kisalan donemde indeks ilerlemeli");
    }

    function test_sifir_donem_uzunlugu_reddediliyor() public {
        vm.prank(owner);
        vm.expectRevert("QAdaptivePaymaster: epochDuration is zero");
        paymaster.setEpochDuration(0);
    }

    function test_sadece_sahip_donem_uzunlugu_degistirebilir() public {
        vm.prank(address(0xBAD));
        vm.expectRevert("QAdaptivePaymaster: caller must be owner");
        paymaster.setEpochDuration(1 hours);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Dönem Sayacı
    // ═════════════════════════════════════════════════════════════════════════

    function test_donem_indeksi_ilerliyor() public {
        assertEq(paymaster.epochIndex(), 0);
        vm.warp(block.timestamp + EPOCH_DURATION);
        assertEq(paymaster.epochIndex(), 1);
        vm.warp(block.timestamp + EPOCH_DURATION * 3);
        assertEq(paymaster.epochIndex(), 4);
    }

    /// @notice Sözleşme doğrudan ETH kabul ediyor (receive).
    function test_dogrudan_eth_kabul_ediliyor() public {
        vm.deal(address(0xCAFE), 1 ether);
        vm.prank(address(0xCAFE));
        (bool ok, ) = address(paymaster).call{value: 0.1 ether}("");
        assertTrue(ok, "receive() calismadi");
        assertEq(address(paymaster).balance, 0.1 ether);
    }

    /**
     * @notice DEĞİŞMEZ: uzlaşma muhasebeyi ASLA negatife düşürmez.
     */
    function testFuzz_uzlasma_muhasebeyi_negatife_dusurmuyor(uint96 gercekMaliyet) public {
        (bytes memory ctx, uint256 vd) = _validate(hesap, MAX_COST_PER_OP);
        assertEq(vd, 0);

        vm.prank(address(entryPoint));
        paymaster.postOp(
            QAdaptivePaymaster.PostOpMode.opSucceeded, ctx, uint256(gercekMaliyet)
        );

        assertLe(paymaster.currentAccountSpend(hesap), MAX_COST_PER_OP);
        assertLe(paymaster.currentTotalSpend(), EPOCH_BUDGET);
    }
}
