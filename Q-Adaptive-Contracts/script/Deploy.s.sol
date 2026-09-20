// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../contracts/QAdaptiveAICore.sol";
import "../contracts/QAdaptiveAccount.sol";
import "../contracts/QAdaptivePaymaster.sol";

/**
 * @title  Deploy
 * @notice Q-ADAPTIVE yığınını bir EVM ağına konuşlandırır.
 *
 * @dev    Kullanım
 *         ────────
 *           cp .env.example .env     # doldur
 *           source .env
 *
 *           # 1) Kuru koşu — hiçbir işlem yayınlanmaz
 *           forge script script/Deploy.s.sol:Deploy --rpc-url "$RPC_URL"
 *
 *           # 2) Gerçek konuşlandırma
 *           forge script script/Deploy.s.sol:Deploy --rpc-url "$RPC_URL" \
 *               --broadcast --verify
 *
 *         EntryPoint hakkında
 *         ───────────────────
 *         v0.7 EntryPoint, CREATE2 ile tüm ağlarda **aynı** adrestedir:
 *         0x0000000071727De22E5E9d8BAf0edAc6f37da032
 *         Betik, konuşlandırmadan önce o adreste gerçekten kod olduğunu
 *         doğrular. Bu kontrol olmasa, yanlış ağa ya da EntryPoint'in henüz
 *         konuşlandırılmadığı bir ağa sessizce deploy edilebilirdi — ve
 *         sonuç, hiçbir zaman çalışmayacak ama "başarılı" görünen bir yığın
 *         olurdu.
 */
contract Deploy is Script {
    /// @dev ERC-4337 v0.7 kanonik EntryPoint adresi (tüm ağlarda aynı).
    address internal constant CANONICAL_ENTRYPOINT =
        0x0000000071727De22E5E9d8BAf0edAc6f37da032;

    // Paymaster politika varsayılanları — testnet için ölçülü tutuldu.
    uint256 internal constant DEFAULT_MAX_COST_PER_OP = 0.01 ether;
    uint256 internal constant DEFAULT_PER_ACCOUNT_QUOTA = 0.05 ether;
    uint256 internal constant DEFAULT_EPOCH_BUDGET = 0.5 ether;
    uint256 internal constant DEFAULT_EPOCH_DURATION = 1 days;

    /// @dev Oracle bayatlık penceresi. Kısa tutmak güvenli yöndedir:
    ///      guardian susarsa zırh azamiye çıkar (bkz. QAdaptiveAICore).
    uint256 internal constant DEFAULT_ORACLE_MAX_AGE = 1 hours;

    /**
     * @notice Verilen adreste gerçekten sözleşme kodu olduğunu doğrular.
     * @dev    `public` olması bilinçli: testler bunu ortam değişkenine
     *         dokunmadan doğrudan çağırabiliyor. Foundry testleri paralel
     *         koşar ve `vm.setEnv` süreç düzeyinde yazar — negatif kontrolü
     *         ortama bağlamak testleri birbirine karıştırıyordu.
     * @return Adresteki baytkod uzunluğu.
     */
    function dogrulaEntryPoint(address entryPoint) public view returns (uint256) {
        uint256 epCodeSize;
        // solhint-disable-next-line no-inline-assembly
        assembly {
            epCodeSize := extcodesize(entryPoint)
        }
        require(
            epCodeSize > 0,
            "Deploy: EntryPoint adresinde kod yok - yanlis ag veya yanlis adres"
        );
        return epCodeSize;
    }

    function run() external {
        // ── Yapılandırma ────────────────────────────────────────────────
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        address entryPoint = vm.envOr("ENTRYPOINT", CANONICAL_ENTRYPOINT);
        address guardian = vm.envOr("GUARDIAN_SIGNER", deployer);
        address oracleUpdater = vm.envOr("ORACLE_UPDATER", deployer);
        address accountOwner = vm.envOr("ACCOUNT_OWNER", deployer);
        bytes32 quantumKey = vm.envOr(
            "INITIAL_QUANTUM_KEY",
            keccak256(abi.encodePacked("Q-ADAPTIVE/v1/initial-quantum-key", deployer))
        );

        // ── Ön kontrol: EntryPoint gerçekten orada mı? ──────────────────
        // Bu, "yeşil ama hiçbir şey yapmayan" konuşlandırmanın panzehiri.
        uint256 epCodeSize = dogrulaEntryPoint(entryPoint);

        console2.log("== Q-ADAPTIVE konuslandirma ==");
        console2.log("zincir id      :", block.chainid);
        console2.log("deployer       :", deployer);
        console2.log("EntryPoint     :", entryPoint);
        console2.log("EntryPoint kod :", epCodeSize, "bayt");
        console2.log("guardian imzaci:", guardian);
        console2.log("oracle updater :", oracleUpdater);
        console2.log("hesap sahibi   :", accountOwner);

        // ── Konuşlandırma ───────────────────────────────────────────────
        vm.startBroadcast(deployerKey);

        QAdaptiveAICore aiCore = new QAdaptiveAICore(
            deployer, // owner — sonra transferOwnership ile devredilebilir
            oracleUpdater,
            DEFAULT_ORACLE_MAX_AGE
        );

        QAdaptiveAccount account = new QAdaptiveAccount(
            entryPoint,
            address(aiCore),
            quantumKey,
            accountOwner,
            guardian
        );

        QAdaptivePaymaster paymaster = new QAdaptivePaymaster(
            entryPoint,
            DEFAULT_MAX_COST_PER_OP,
            DEFAULT_PER_ACCOUNT_QUOTA,
            DEFAULT_EPOCH_BUDGET,
            DEFAULT_EPOCH_DURATION
        );

        vm.stopBroadcast();

        // ── Konuşlandırma sonrası doğrulama ─────────────────────────────
        // Adres basmak yetmez; bağlantıların gerçekten kurulduğunu görmeliyiz.
        require(
            address(account.aiCore()) == address(aiCore),
            "Deploy: hesap oracle'a bagli degil"
        );
        require(account.entryPoint() == entryPoint, "Deploy: hesap EntryPoint yanlis");
        require(paymaster.entryPoint() == entryPoint, "Deploy: paymaster EntryPoint yanlis");
        require(account.owner() == accountOwner, "Deploy: hesap sahibi yanlis");
        require(aiCore.updater() == oracleUpdater, "Deploy: oracle updater yanlis");

        // Oracle henüz hiç güncellenmedi → bayat olmalı → azami zirh.
        (uint256 risk, bool panik) = aiCore.getGlobalRiskStatus();
        require(aiCore.isStale(), "Deploy: taze oracle bayat olmaliydi");
        require(risk == aiCore.MAX_RISK_SCORE(), "Deploy: bayat oracle azami risk vermeli");
        require(!panik, "Deploy: bayat oracle panik ACMAMALI");

        console2.log("");
        console2.log("-- konuslandirildi --");
        console2.log("QAdaptiveAICore   :", address(aiCore));
        console2.log("QAdaptiveAccount  :", address(account));
        console2.log("QAdaptivePaymaster:", address(paymaster));
        console2.log("");
        console2.log("Oracle baslangicta BAYAT (hic guncellenmedi) -> azami zirh, panik kapali.");
        console2.log("Guardian ilk riski yazana kadar bu boyle kalir:");
        console2.log("  cast send", address(aiCore));
        console2.log("    'updateRiskStatus(uint256,bool)' <risk_x100> <panik>");
    }
}
