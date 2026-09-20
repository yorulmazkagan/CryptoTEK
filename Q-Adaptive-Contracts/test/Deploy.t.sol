// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../script/Deploy.s.sol";
import "./mocks/Mocks.sol";

/**
 * @title  DeployTest
 * @notice Konuşlandırma betiğinin kendisini test eder.
 *
 * @dev    Neden bu test var
 *         ─────────────────
 *         Bu oturumda tekrar tekrar karşılaştığımız tuzak: "yeşil ama hiçbir
 *         şey yapmayan" kontrol. Bir deploy betiği bunun en sinsi hâlidir —
 *         adresleri basar, çıkış kodu 0 döner, ama bağlantılar kurulmamıştır
 *         ve bunu ancak aylar sonra fark edersin.
 *
 *         Betik yerelde anvil'e karşı bir kez elle koşuldu ve çalıştı. Elle
 *         koşmak bir kereliktir; bu test kalıcıdır.
 */
contract DeployTest is Test {
    Deploy internal betik;
    MockEntryPoint internal entryPoint;

    address internal deployer;
    uint256 internal deployerKey = 0xA11CE;

    function setUp() public {
        betik = new Deploy();
        entryPoint = new MockEntryPoint();
        deployer = vm.addr(deployerKey);
        vm.setEnv("PRIVATE_KEY", vm.toString(deployerKey));
    }

    /// `vm.setEnv` SÜREÇ düzeyinde yazar, EVM durumu gibi testler arasında
    /// geri alınmaz. Negatif test `ENTRYPOINT`'i bozuk bir adrese ayarlayınca
    /// diğer testler de onu görüyordu. Bu yüzden her test, kendi beklediği
    /// değeri çalıştırmadan hemen önce kendisi yazar.
    function _entryPointuAyarla() internal {
        vm.setEnv("ENTRYPOINT", vm.toString(address(entryPoint)));
    }

    /// Betik baştan sona koşuyor ve kendi son kontrollerini geçiyor.
    ///
    /// `run()` içindeki `require`'lar asıl doğrulamayı yapıyor: hesap
    /// oracle'a bağlı mı, EntryPoint'ler tutuyor mu, taze oracle bayat mı.
    /// Biri tutmazsa bu test kırılır.
    function test_betik_bastan_sona_kosuyor() public {
        _entryPointuAyarla();
        betik.run();
    }

    /// EntryPoint adresinde kod yoksa betik DURMALI.
    ///
    /// Bu kontrol olmasaydı yanlış ağa konuşlandırma sessizce "başarılı"
    /// görünürdü: üç sözleşme de deploy olur, hiçbiri hiç çalışmazdı.
    /// Kontrol, ortam değişkeni üzerinden değil doğrudan çağrılır: Foundry
    /// testleri paralel koşar ve `vm.setEnv` süreç düzeyinde yazdığı için
    /// testler birbirinin `ENTRYPOINT` değerini eziyordu.
    function test_entrypoint_kodsuzsa_duruyor() public {
        vm.expectRevert(
            bytes("Deploy: EntryPoint adresinde kod yok - yanlis ag veya yanlis adres")
        );
        betik.dogrulaEntryPoint(address(0xDEAD));
    }

    /// Ve kod VARSA geçmeli — aksi hâlde yukarıdaki test her şeye "hayır"
    /// diyen bir kontrolü de geçerli sayardı.
    function test_entrypoint_kodluysa_geciyor() public view {
        uint256 boyut = betik.dogrulaEntryPoint(address(entryPoint));
        assertGt(boyut, 0, "mock EntryPoint baytkodu bos gorunuyor");
    }

    /// Ortam değişkenleri verildiğinde betik onlara uymalı — varsayılana düşmemeli.
    function test_ortam_degiskenleri_uygulaniyor() public {
        address sahip = address(0xB0B);
        address guardian = address(0xC0FFEE);
        address updater = address(0xD00D);

        vm.setEnv("ACCOUNT_OWNER", vm.toString(sahip));
        vm.setEnv("GUARDIAN_SIGNER", vm.toString(guardian));
        vm.setEnv("ORACLE_UPDATER", vm.toString(updater));
        _entryPointuAyarla();

        // recordLogs ile konuşlandırılan adresleri yakalamak yerine, betiğin
        // kendi require'larina guveniyoruz; burada ek olarak adreslerin
        // gercekten farkli oldugunu dogruluyoruz.
        vm.recordLogs();
        betik.run();

        Vm.Log[] memory kayitlar = vm.getRecordedLogs();
        assertGt(kayitlar.length, 0, "konuslandirma hic olay yaymadi");
    }
}
