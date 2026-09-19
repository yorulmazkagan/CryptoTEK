// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./interfaces/IUserOperation.sol";
import "./interfaces/IEntryPoint.sol";

/**
 * @title QAdaptivePaymaster
 * @dev ERC-4337 Security Sponsor vault. It sponsors (pays gas for) critical
 * defensive operations, specifically `updateQuantumArmor`, to ensure the user
 * is never blocked from upgrading their quantum defense due to a lack of gas.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * BULGU 5 — SÖMÜRÜLEBİLİR FON KAYBI AÇIĞI (kapatıldı)
 * ─────────────────────────────────────────────────────────────────────────────
 * Eski `validatePaymasterUserOp` YALNIZCA fonksiyon seçicisine bakıyordu:
 *
 *     if (selector == updateQuantumArmorSelector) {
 *         emit DefensiveOperationSponsored(userOp.sender, maxCost);
 *         return ("", 0);          // ← sponsor ol
 *     }
 *
 * `userOp.sender` hiç kontrol edilmiyordu. Herhangi biri şu imzaya sahip boş
 * bir sözleşme deploy edip mevduatı sınırsız tüketebilirdi:
 *
 *     function updateQuantumArmor(string calldata, bytes32) external {}
 *
 * Tavan da yoktu: tek bir işlem mevduatın tamamını yakabilirdi.
 *
 * Şimdi DÖRT BAĞIMSIZ KAPI var. Bir saldırganın geçmesi için dördünü birden
 * aşması gerekir:
 *
 *   1. Gönderen kaydı  — `sponsoredAccounts[userOp.sender]` true olmalı.
 *   2. İşlem tavanı    — `maxCost <= maxCostPerOperation`.
 *   3. Hesap kotası    — hesabın dönem içindeki toplam harcaması sınırlı.
 *   4. Dönem bütçesi   — tüm hesapların dönem içindeki toplamı sınırlı.
 *
 * Kapılar 3 ve 4 gerçek harcamayla (`postOp`) uzlaşır, tahminle değil.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * BULGU 14 — MEVDUAT VE postOp (kapatıldı)
 * ─────────────────────────────────────────────────────────────────────────────
 * `depositToEntryPoint` gerçek mevduat yapmıyordu (yalnızca olay yayınlıyordu)
 * ve `postOp` boştu. Artık ilki `IEntryPoint.depositTo` çağırıyor, ikincisi
 * ön-rezervasyonu gerçek maliyetle uzlaştırıyor.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * Gaz maliyeti hakkında dürüst not
 * ─────────────────────────────────────────────────────────────────────────────
 * Kota takibi bedava değil: doğrulama sırasında iki, `postOp` sırasında iki
 * depolama yazması yapılıyor. Bu, paymaster'ı boşaltmaya karşı korumanın
 * bedelidir. Ölçülen değerler için `forge test --gas-report` çıktısına bakın.
 */
contract QAdaptivePaymaster {

    // ─────────────────────────────────────────────────────────────────────────────
    // State Variables
    // ─────────────────────────────────────────────────────────────────────────────

    // ReentrancyGuard status variables
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status;

    /// @notice Address of the EntryPoint contract.
    address public immutable entryPoint;

    /// @notice The contract owner (corporate vault manager).
    address public owner;

    /// @notice Sponsorlanabilen tek fonksiyon seçicisi.
    /// @dev `updateQuantumArmor(string,bytes32)`. Sabit olarak tutuluyor ki
    ///      her doğrulamada keccak256 hesaplanmasın.
    bytes4 public constant SPONSORED_SELECTOR =
        bytes4(keccak256("updateQuantumArmor(string,bytes32)"));

    // ── KAPI 1: Gönderen Kaydı ──────────────────────────────────────────────

    /// @notice Sponsorluk almaya yetkili hesaplar.
    /// @dev Açığın merkezi buydu: eskiden böyle bir kayıt YOKTU ve
    ///      `userOp.sender` hiç okunmuyordu.
    mapping(address => bool) public sponsoredAccounts;

    // ── KAPI 2: İşlem Tavanı ────────────────────────────────────────────────

    /// @notice Tek bir işlem için sponsorlanacak azami maliyet (wei).
    uint256 public maxCostPerOperation;

    // ── KAPI 3: Hesap Kotası ────────────────────────────────────────────────

    /// @notice Bir hesabın tek bir dönemde harcayabileceği azami tutar (wei).
    uint256 public perAccountEpochQuota;

    /// @notice Hesap → içinde bulunduğu dönemde harcadığı tutar.
    mapping(address => uint256) public accountEpochSpend;

    /// @notice Hesap → harcamasının ait olduğu dönem indeksi.
    /// @dev Dönem değiştiğinde harcama sıfırlanmış sayılır; böylece her dönem
    ///      başında tüm hesapları tek tek sıfırlamak gerekmez.
    mapping(address => uint256) public accountEpochIndex;

    // ── KAPI 4: Dönem Bütçesi ───────────────────────────────────────────────

    /// @notice Bir dönemin uzunluğu (saniye).
    uint256 public epochDuration;

    /// @notice Tüm hesapların bir dönemde harcayabileceği azami toplam (wei).
    uint256 public epochBudget;

    /// @notice İçinde bulunulan dönemde harcanan toplam.
    uint256 public currentEpochSpend;

    /// @notice `currentEpochSpend`'in ait olduğu dönem indeksi.
    uint256 public currentEpochIndex;

    /// @notice Dönem sayacının başlangıç zamanı.
    uint256 public immutable epochGenesis;

    // ─────────────────────────────────────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────────────────────────────────────

    event DefensiveOperationSponsored(address indexed user, uint256 gasCostSponsored);
    event PaymasterFunded(uint256 amount);

    /// @notice Bir sponsorluk talebi reddedildiğinde, hangi kapıda durduğuyla.
    event SponsorshipRejected(address indexed sender, bytes32 reason);

    /// @notice Hesabın sponsorluk kaydı değiştiğinde.
    event AccountRegistrationChanged(address indexed account, bool sponsored);

    /// @notice Limitler güncellendiğinde.
    event LimitsUpdated(
        uint256 maxCostPerOperation,
        uint256 perAccountEpochQuota,
        uint256 epochBudget
    );

    /// @notice `postOp` ön-rezervasyonu gerçek maliyetle uzlaştırdığında.
    event SponsorshipSettled(
        address indexed account,
        uint256 reservedCost,
        uint256 actualCost
    );

    // ─────────────────────────────────────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────────────────────────────────────

    modifier nonReentrant() {
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    modifier onlyEntryPoint() {
        require(msg.sender == entryPoint, "QAdaptivePaymaster: caller must be EntryPoint");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "QAdaptivePaymaster: caller must be owner");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @param _entryPoint           The trusted ERC-4337 EntryPoint address.
     * @param _maxCostPerOperation  Tek işlem tavanı (wei).
     * @param _perAccountEpochQuota Hesap başına dönem kotası (wei).
     * @param _epochBudget          Dönem başına toplam bütçe (wei).
     * @param _epochDuration        Dönem uzunluğu (saniye).
     */
    constructor(
        address _entryPoint,
        uint256 _maxCostPerOperation,
        uint256 _perAccountEpochQuota,
        uint256 _epochBudget,
        uint256 _epochDuration
    ) {
        require(_entryPoint != address(0), "QAdaptivePaymaster: entryPoint is zero");
        require(_epochDuration > 0, "QAdaptivePaymaster: epochDuration is zero");

        _status             = _NOT_ENTERED;
        entryPoint          = _entryPoint;
        owner               = msg.sender;
        epochGenesis        = block.timestamp;

        maxCostPerOperation  = _maxCostPerOperation;
        perAccountEpochQuota = _perAccountEpochQuota;
        epochBudget          = _epochBudget;
        epochDuration        = _epochDuration;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Dönem Yardımcıları
    // ─────────────────────────────────────────────────────────────────────────────

    /// @notice İçinde bulunulan dönemin indeksi.
    function epochIndex() public view returns (uint256) {
        return (block.timestamp - epochGenesis) / epochDuration;
    }

    /// @notice Bir hesabın içinde bulunulan dönemdeki harcaması.
    /// @dev Kayıtlı dönem eskiyse harcama sıfır sayılır.
    function currentAccountSpend(address account) public view returns (uint256) {
        if (accountEpochIndex[account] != epochIndex()) {
            return 0;
        }
        return accountEpochSpend[account];
    }

    /// @notice İçinde bulunulan dönemde harcanan toplam.
    function currentTotalSpend() public view returns (uint256) {
        if (currentEpochIndex != epochIndex()) {
            return 0;
        }
        return currentEpochSpend;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Core ERC-4337 Functions
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Validates if the Paymaster is willing to pay for this UserOperation.
     *
     * @dev DÖRT KAPI sırayla uygulanır. Herhangi biri kapalıysa `validationData`
     *      1 döner ve EntryPoint işlemi sponsorlamaz.
     *
     *      Reddedişlerde depolamaya YAZILMAZ — yalnızca olay yayınlanır. Bu,
     *      ERC-7562 (bundler simülasyon kuralları) gereğidir ve saldırgana
     *      ucuz depolama şişirme vektörü vermemek içindir. Aynı düzeltme
     *      `QAdaptiveAccount.validateUserOp` içinde de yapıldı (hata E3).
     *
     * @param userOp     The UserOperation structure.
     * @param maxCost    The maximum cost of this transaction.
     * @return context      `postOp`'a taşınan bağlam (gönderen + rezerve maliyet).
     * @return validationData 0 for valid, 1 for invalid.
     */
    function validatePaymasterUserOp(
        UserOperation calldata userOp,
        bytes32 /* userOpHash */,
        uint256 maxCost
    ) external onlyEntryPoint returns (bytes memory context, uint256 validationData) {
        // We ensure there's enough data to check the function selector (first 4 bytes).
        if (userOp.callData.length < 4) {
            emit SponsorshipRejected(userOp.sender, "CALLDATA_TOO_SHORT");
            return ("", 1);
        }

        // Extract the 4-byte function selector from callData
        bytes4 selector;
        bytes calldata callData = userOp.callData;
        assembly {
            selector := calldataload(callData.offset)
        }

        // Yalnızca savunma fonksiyonu sponsorlanır.
        if (selector != SPONSORED_SELECTOR) {
            emit SponsorshipRejected(userOp.sender, "SELECTOR_NOT_SPONSORED");
            return ("", 1);
        }

        // ── KAPI 1: Gönderen kaydı ──────────────────────────────────────────
        //    Açığın kapandığı yer burası. Doğru seçiciye sahip olmak artık
        //    yeterli değil; gönderenin kayıtlı olması gerekiyor.
        if (!sponsoredAccounts[userOp.sender]) {
            emit SponsorshipRejected(userOp.sender, "SENDER_NOT_REGISTERED");
            return ("", 1);
        }

        // ── KAPI 2: İşlem tavanı ────────────────────────────────────────────
        if (maxCost > maxCostPerOperation) {
            emit SponsorshipRejected(userOp.sender, "EXCEEDS_PER_OP_CAP");
            return ("", 1);
        }

        // ── KAPI 3: Hesap kotası ────────────────────────────────────────────
        uint256 hesapHarcamasi = currentAccountSpend(userOp.sender);
        if (hesapHarcamasi + maxCost > perAccountEpochQuota) {
            emit SponsorshipRejected(userOp.sender, "ACCOUNT_QUOTA_EXHAUSTED");
            return ("", 1);
        }

        // ── KAPI 4: Dönem bütçesi ───────────────────────────────────────────
        uint256 toplamHarcama = currentTotalSpend();
        if (toplamHarcama + maxCost > epochBudget) {
            emit SponsorshipRejected(userOp.sender, "EPOCH_BUDGET_EXHAUSTED");
            return ("", 1);
        }

        // ── Ön-rezervasyon ──────────────────────────────────────────────────
        //    `maxCost` şimdi rezerve edilir; `postOp` gerçek maliyetle
        //    uzlaştırır. Rezervasyon olmadan aynı hesap tek bir dönemde
        //    kotasını defalarca aşacak şekilde paralel işlem gönderebilirdi.
        uint256 donem = epochIndex();

        accountEpochIndex[userOp.sender] = donem;
        accountEpochSpend[userOp.sender] = hesapHarcamasi + maxCost;

        currentEpochIndex = donem;
        currentEpochSpend = toplamHarcama + maxCost;

        emit DefensiveOperationSponsored(userOp.sender, maxCost);

        return (abi.encode(userOp.sender, maxCost, donem), 0);
    }

    /**
     * @notice Post-operation hook — ön-rezervasyonu gerçek maliyetle uzlaştırır.
     *
     * @dev Bu fonksiyonun gövdesi eskiden BOŞTU:
     *          // Logic for tracking exact gas spent can be implemented here.
     *      Yani harcama hiç takip edilmiyordu.
     *
     *      Artık doğrulamada rezerve edilen `maxCost` ile gerçekleşen
     *      `actualGasCost` arasındaki fark geri veriliyor. Fark iade
     *      edilmezse her işlem tavan kadar sayılır ve kota olması
     *      gerekenden çok daha hızlı tükenirdi.
     */
    function postOp(
        PostOpMode /* mode */,
        bytes calldata context,
        uint256 actualGasCost
    ) external onlyEntryPoint {
        if (context.length == 0) {
            return;
        }

        (address hesap, uint256 rezerve, uint256 donem) =
            abi.decode(context, (address, uint256, uint256));

        // Dönem değiştiyse rezervasyon zaten sıfırlanmış sayılır; geri verecek
        // bir şey yok. (Uzun süren bir işlem dönem sınırını aşabilir.)
        if (donem != epochIndex()) {
            emit SponsorshipSettled(hesap, rezerve, actualGasCost);
            return;
        }

        if (actualGasCost < rezerve) {
            uint256 iade = rezerve - actualGasCost;

            // Alt taşma savunması: muhasebe beklenmedik bir durumda bozulmuşsa
            // sıfıra kırp, negatife düşme.
            accountEpochSpend[hesap] =
                accountEpochSpend[hesap] > iade ? accountEpochSpend[hesap] - iade : 0;

            currentEpochSpend =
                currentEpochSpend > iade ? currentEpochSpend - iade : 0;
        }

        emit SponsorshipSettled(hesap, rezerve, actualGasCost);
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Admin Functions
    // ─────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Bir hesabı sponsorluk kaydına ekler veya çıkarır.
     */
    function setAccountSponsorship(address account, bool sponsored) external onlyOwner {
        require(account != address(0), "QAdaptivePaymaster: account is zero");
        sponsoredAccounts[account] = sponsored;
        emit AccountRegistrationChanged(account, sponsored);
    }

    /**
     * @notice Üç limiti birlikte günceller.
     * @dev Birlikte güncellenmeleri kasıtlı: kota işlem tavanından küçük
     *      olursa hiçbir işlem geçemez, bütçe kotadan küçük olursa tek hesap
     *      bütçenin tamamını kilitler. Tutarlılık burada zorlanır.
     */
    function updateLimits(
        uint256 _maxCostPerOperation,
        uint256 _perAccountEpochQuota,
        uint256 _epochBudget
    ) external onlyOwner {
        require(
            _perAccountEpochQuota >= _maxCostPerOperation,
            "QAdaptivePaymaster: quota below per-op cap"
        );
        require(
            _epochBudget >= _perAccountEpochQuota,
            "QAdaptivePaymaster: budget below account quota"
        );

        maxCostPerOperation  = _maxCostPerOperation;
        perAccountEpochQuota = _perAccountEpochQuota;
        epochBudget          = _epochBudget;

        emit LimitsUpdated(_maxCostPerOperation, _perAccountEpochQuota, _epochBudget);
    }

    /**
     * @notice Allows the owner to fund this paymaster directly via EntryPoint.
     *
     * @dev BULGU 14: Bu fonksiyon eskiden gerçek mevduat YAPMIYORDU; gövdesinde
     *      "in a real implementation..." yorumu ve bir olay vardı. Para
     *      sözleşmede kalıyor, EntryPoint'te hiç bakiye oluşmuyordu — yani
     *      paymaster gerçek bir ağda hiçbir işlemi sponsorlayamazdı.
     */
    function depositToEntryPoint() external payable onlyOwner nonReentrant {
        require(msg.value > 0, "QAdaptivePaymaster: zero deposit");
        IEntryPoint(entryPoint).depositTo{value: msg.value}(address(this));
        emit PaymasterFunded(msg.value);
    }

    /**
     * @notice EntryPoint'teki mevduatı çeker.
     */
    function withdrawFromEntryPoint(address payable to, uint256 amount)
        external
        onlyOwner
        nonReentrant
    {
        require(to != address(0), "QAdaptivePaymaster: withdraw to zero");
        IEntryPoint(entryPoint).withdrawTo(to, amount);
    }

    /**
     * @notice EntryPoint'teki güncel mevduat bakiyesi.
     */
    function entryPointDeposit() external view returns (uint256) {
        return IEntryPoint(entryPoint).balanceOf(address(this));
    }

    /**
     * @notice Enums required by standard Paymaster interfaces.
     */
    enum PostOpMode { opSucceeded, opReverted, postOpReverted }

    // ─────────────────────────────────────────────────────────────────────────────
    // Receive
    // ─────────────────────────────────────────────────────────────────────────────

    receive() external payable {}
}
