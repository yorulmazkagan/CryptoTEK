// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "../../contracts/interfaces/IAICore.sol";
import "../../contracts/interfaces/IEntryPoint.sol";

/**
 * @title MockAICore
 * @notice Zincir üstü risk oracle'ının test ikizi.
 */
contract MockAICore is IAICore {
    uint256 public riskScore;
    bool    public panicMode;

    function setStatus(uint256 _riskScore, bool _panicMode) external {
        riskScore = _riskScore;
        panicMode = _panicMode;
    }

    function getGlobalRiskStatus() external view returns (uint256, bool) {
        return (riskScore, panicMode);
    }
}

/**
 * @title MockEntryPoint
 * @notice ERC-4337 EntryPoint'in test ikizi.
 *
 * @dev **Bu mock'un en önemli özelliği `receive()` içinde DEPOLAMAYA
 *      YAZMASIDIR.** Gerçek EntryPoint de mevduat muhasebesi için tam olarak
 *      bunu yapar ve bu yüzden ~20.000+ gaz harcar.
 *
 *      Eski hesap sözleşmesi ön-fonlamayı `call{gas: 2300}` ile yapıyordu;
 *      2300 gaz tek bir SSTORE'a bile yetmez. Bu mock kasıtlı olarak iki
 *      SSTORE yapar, böylece hata E1 geri gelirse `test_E1_*` testleri kırılır.
 *      Depolamaya yazmayan bir mock bu hatayı YAKALAYAMAZDI — denetimin
 *      kaçırdığı şey de tam buydu.
 */
contract MockEntryPoint is IEntryPoint {
    mapping(address => uint256) public deposits;

    /// @notice Kaç kez fonlandığımızı sayar (ikinci SSTORE).
    uint256 public fundingCount;

    /// @notice Son alınan ön-fonlama miktarı.
    uint256 public lastPrefund;

    event Prefunded(address indexed from, uint256 amount);

    receive() external payable {
        // İKİ depolama yazması — gerçek EntryPoint'in mevduat muhasebesi gibi.
        // 2300 gaz stipend'i bunların ilkine bile yetmez.
        fundingCount += 1;
        lastPrefund   = msg.value;
        deposits[msg.sender] += msg.value;
        emit Prefunded(msg.sender, msg.value);
    }

    function depositTo(address account) external payable {
        deposits[account] += msg.value;
    }

    function balanceOf(address account) external view returns (uint256) {
        return deposits[account];
    }

    function withdrawTo(address payable withdrawAddress, uint256 withdrawAmount) external {
        require(deposits[msg.sender] >= withdrawAmount, "MockEntryPoint: insufficient deposit");
        deposits[msg.sender] -= withdrawAmount;
        (bool ok, ) = withdrawAddress.call{value: withdrawAmount}("");
        require(ok, "MockEntryPoint: withdraw failed");
    }
}

/**
 * @title AttackerArmorContract
 * @notice BULGU 5'in sömürü aracı.
 *
 * @dev Saldırgan tam olarak bunu yapardı: paymaster'ın sponsorladığı
 *      seçiciye sahip, içi boş bir sözleşme deploy edip mevduatı tüketmek.
 *      Eski paymaster yalnızca seçiciye baktığı için bu sözleşme
 *      sponsorluk alırdı.
 */
contract AttackerArmorContract {
    uint256 public callCount;

    /// @dev Paymaster'ın sponsorladığı seçicinin birebir aynısı.
    function updateQuantumArmor(string calldata, bytes32) external {
        callCount += 1;
    }
}

/**
 * @title GasBurner
 * @notice `execute()` gaz kontrolü testleri için kontrollü gaz yakıcı.
 */
contract GasBurner {
    uint256 public value;

    function burn(uint256 iterations) external {
        for (uint256 i = 0; i < iterations; i++) {
            value = i;
        }
    }

    function setValue(uint256 v) external {
        value = v;
    }
}
