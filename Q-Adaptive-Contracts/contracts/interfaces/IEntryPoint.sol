// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IEntryPoint
 * @notice ERC-4337 EntryPoint'in bu projenin kullandığı yüzeyi.
 *
 * @dev Bu arayüz daha önce YOKTU. `QAdaptivePaymaster.depositToEntryPoint()`
 *      gerçek bir mevduat yapmıyordu; gövdesinde şu yorum duruyordu:
 *
 *          // In a real implementation, this would call
 *          // IEntryPoint(entryPoint).depositTo{value: msg.value}(address(this));
 *          emit PaymasterFunded(msg.value);
 *
 *      Yani fonksiyon parayı sözleşmede tutup yalnızca bir olay yayınlıyordu.
 *      EntryPoint'te hiç bakiye oluşmadığı için paymaster gerçek bir ağda
 *      hiçbir işlemi sponsorlayamazdı.
 *
 *      `depositTo` ve `balanceOf` ERC-4337 v0.6/v0.7 EntryPoint'lerinde aynı
 *      imzaya sahiptir; `withdrawTo` da öyle.
 */
interface IEntryPoint {
    /**
     * @notice Verilen hesap adına EntryPoint'e mevduat yatırır.
     * @param account Mevduatın alacaklısı (burada paymaster'ın kendisi).
     */
    function depositTo(address account) external payable;

    /**
     * @notice Bir hesabın EntryPoint'teki mevduat bakiyesi.
     */
    function balanceOf(address account) external view returns (uint256);

    /**
     * @notice Mevduatı EntryPoint'ten çeker.
     * @param withdrawAddress Paranın gideceği adres.
     * @param withdrawAmount  Çekilecek miktar.
     */
    function withdrawTo(address payable withdrawAddress, uint256 withdrawAmount) external;
}
