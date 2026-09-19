// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/QAdaptiveAccount.sol";
import "../contracts/QAdaptivePaymaster.sol";
import "../contracts/interfaces/IUserOperation.sol";
import "../contracts/interfaces/IEntryPoint.sol";
import "./mocks/Mocks.sol";

/**
 * @title EntryPointForkTest
 * @notice GERÇEK ERC-4337 EntryPoint v0.7 ile fork testi.
 *
 * ╔═══════════════════════════════════════════════════════════════════════════╗
 * ║  BU TEST HENÜZ ÇALIŞTIRILMADI                                             ║
 * ║                                                                           ║
 * ║  Yazıldığı ortamda ağ erişimi yoktu, dolayısıyla aşağıdaki iddiaların     ║
 * ║  hiçbiri gerçek EntryPoint'e karşı DOĞRULANMIŞ DEĞİLDİR. Test, RPC        ║
 * ║  yapılandırılmadığında kendini atlar — sahte bir "geçti" üretmez.         ║
 * ║                                                                           ║
 * ║  Çalıştırmak için:                                                        ║
 * ║    export ETH_RPC_URL="https://<saglayici>/<anahtar>"                      ║
 * ║    forge test --match-contract EntryPointForkTest -vv                     ║
 * ╚═══════════════════════════════════════════════════════════════════════════╝
 *
 * @dev Neden mock yetmiyor:
 *      `MockEntryPoint` hata E1'i yakalamak için kasıtlı olarak `receive()`
 *      içinde iki SSTORE yapar ve bu, 2300 gaz stipend'inin neden çalışmadığını
 *      kanıtlamaya yeter. Ama mock yine de BİZİM yazdığımız bir sözleşmedir;
 *      gerçek EntryPoint'in mevduat muhasebesi, nonce yönetimi ve
 *      `validateUserOp` çağrı bağlamı farklı olabilir.
 *
 *      Bu dosya o boşluğu kapatmak içindir: aynı iddialar gerçek, konuşlanmış
 *      EntryPoint v0.7 baytkoduna karşı sınanır.
 */
contract EntryPointForkTest is Test {
    /// @dev ERC-4337 v0.7 EntryPoint — tüm büyük ağlarda aynı adres.
    address constant ENTRYPOINT_V07 = 0x0000000071727De22E5E9d8BAf0edAc6f37da032;

    QAdaptiveAccount   account;
    QAdaptivePaymaster paymaster;
    MockAICore         aiCore;

    address owner    = address(0xA11CE);
    address guardian = address(0x6A5D);

    /// @dev RPC yapılandırılmamışsa testler atlanır.
    bool forkAktif;

    function setUp() public {
        string memory rpc = vm.envOr("ETH_RPC_URL", string(""));

        if (bytes(rpc).length == 0) {
            forkAktif = false;
            return;
        }

        vm.createSelectFork(rpc);

        // Adreste gerçekten kod var mı? Yoksa fork yanlış ağa bağlanmış olabilir.
        if (ENTRYPOINT_V07.code.length == 0) {
            forkAktif = false;
            return;
        }

        forkAktif = true;

        aiCore = new MockAICore();

        account = new QAdaptiveAccount(
            ENTRYPOINT_V07, address(aiCore), bytes32(uint256(0xDEAD)), owner, guardian
        );

        vm.prank(owner);
        paymaster = new QAdaptivePaymaster(
            ENTRYPOINT_V07, 0.01 ether, 0.05 ether, 0.2 ether, 1 days
        );

        vm.deal(address(account), 10 ether);
        vm.deal(owner, 10 ether);
    }

    /// @dev RPC yoksa testi atlar. `vm.skip` sayesinde sonuç "skipped" olur,
    ///      yani yanlışlıkla "geçti" diye okunamaz.
    modifier forkGerekir() {
        if (!forkAktif) {
            vm.skip(true);
        }
        _;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HATA E1 — gerçek EntryPoint'e ön-fonlama
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice Ön-fonlama GERÇEK EntryPoint'e ulaşıyor.
     *
     * Bu, `MockEntryPoint` ile yapılan testin gerçek baytkoda karşı
     * tekrarıdır. Gerçek EntryPoint'in `receive()`'ı mevduat muhasebesi için
     * depolamaya yazar; 2300 gaz stipend'i buna yetmez.
     */
    function test_fork_on_fonlama_gercek_entrypointe_ulasiyor() public forkGerekir {
        aiCore.setStatus(1000, false);

        uint256 prefund = 0.05 ether;
        uint256 oncesi  = IEntryPoint(ENTRYPOINT_V07).balanceOf(address(account));

        QAdaptiveAccount.AirVerificationMetadata memory bos;
        QAdaptiveAccount.GuardianAttestation memory att =
            QAdaptiveAccount.GuardianAttestation(0, 0, "");

        UserOperation memory op;
        op.sender    = address(account);
        op.signature = abi.encode(new bytes(0), bos, uint256(1000), att);

        vm.prank(ENTRYPOINT_V07);
        uint256 sonuc = account.validateUserOp(op, bytes32(uint256(1)), prefund);

        assertEq(
            sonuc, account.SIG_VALIDATION_SUCCESS(),
            "Gercek EntryPoint ile dogrulama basarisiz"
        );
        assertEq(
            IEntryPoint(ENTRYPOINT_V07).balanceOf(address(account)),
            oncesi + prefund,
            "On-fonlama gercek EntryPoint mevduatina yansimadi"
        );
    }

    // ═════════════════════════════════════════════════════════════════════════
    // BULGU 14 — gerçek EntryPoint'e mevduat
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * @notice `depositToEntryPoint` gerçek EntryPoint'te bakiye oluşturuyor.
     */
    function test_fork_paymaster_mevduati_gercek_entrypointte() public forkGerekir {
        uint256 miktar = 0.5 ether;

        vm.prank(owner);
        paymaster.depositToEntryPoint{value: miktar}();

        assertEq(
            IEntryPoint(ENTRYPOINT_V07).balanceOf(address(paymaster)),
            miktar,
            "Mevduat gercek EntryPoint'e ulasmadi"
        );
        assertEq(paymaster.entryPointDeposit(), miktar, "balanceOf okumasi tutmadi");
    }

    /// @notice Mevduat gerçek EntryPoint'ten çekilebiliyor.
    function test_fork_mevduat_gercek_entrypointten_cekilebiliyor() public forkGerekir {
        vm.startPrank(owner);
        paymaster.depositToEntryPoint{value: 0.5 ether}();

        address alici  = address(0xBEEF);
        uint256 oncesi = alici.balance;

        paymaster.withdrawFromEntryPoint(payable(alici), 0.2 ether);
        vm.stopPrank();

        assertEq(alici.balance, oncesi + 0.2 ether, "Cekim aliciya ulasmadi");
        assertEq(paymaster.entryPointDeposit(), 0.3 ether, "Mevduat dusulmedi");
    }

    /// @notice Fork'un gerçekten doğru ağa bağlandığını sabitler.
    function test_fork_entrypoint_baytkodu_mevcut() public forkGerekir {
        assertGt(
            ENTRYPOINT_V07.code.length, 0,
            "EntryPoint v0.7 adresinde kod yok - yanlis ag olabilir"
        );
    }
}
