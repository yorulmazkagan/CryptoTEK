# =============================================================================
# Q-ADAPTIVE AI Guardian — API Test İstemcisi (test_api_client.py)
# =============================================================================
# Bu betik, çalışan FastAPI sunucusuna programatik POST istekleri göndererek
# 3 simülasyon senaryosunu test eder ve sonuçları yapılandırılmış biçimde
# konsola yazdırır.
#
# KULLANIM:
#   Terminal 1: python run_server.py          (Sunucuyu başlat)
#   Terminal 2: python test_api_client.py     (Bu betiği çalıştır)
#
# Beklenen çıktı:
#   Senaryo 1 (Standart Kullanıcı)  → action: SAFE
#   Senaryo 2 (Bot Saldırısı)       → action: TRIGGER_PANIC_MODE
#   Senaryo 3 (Private Key Çalınma) → action: TRIGGER_PANIC_MODE
# =============================================================================

import json
import sys
import time
from typing import Any, Dict, List

import requests

# ── API Yapılandırması ────────────────────────────────────────────────────────

BASE_URL        : str = "http://127.0.0.1:8000"
PREDICT_URL     : str = f"{BASE_URL}/predict"
HEALTH_URL      : str = f"{BASE_URL}/health"
REQUEST_TIMEOUT : int = 10    # saniye
RETRY_ATTEMPTS  : int = 3     # bağlantı hatası için yeniden deneme sayısı
RETRY_DELAY     : float = 1.0 # yeniden denemeler arası bekleme (saniye)


# ── Test Senaryoları (PDF Bölüm 4'e uygun) ────────────────────────────────────

TEST_SCENARIOS: List[Dict[str, Any]] = [
    {
        "name"       : "Standart Kullanıcı (DeFi Swap İşlemi)",
        "description": "Ahmet, DeFi üzerinde rutin bir token takası yapıyor.",
        "expected"   : "SAFE",
        "payload"    : {
            "Islem_Sikligi" : 1.1,
            "IP_Sapmasi"    : 0.02,
            "Gas_Sapmasi"   : 0.05,
        },
    },
    {
        "name"       : "Bot Saldırısı (Yüksek Frekanslı Spam)",
        "description": "Sisteme saniyede 50 işlem gönderen bot tespit edildi.",
        "expected"   : "TRIGGER_PANIC_MODE",
        "payload"    : {
            "Islem_Sikligi" : 50.0,
            "IP_Sapmasi"    : 0.05,
            "Gas_Sapmasi"   : 0.1,
        },
    },
    {
        "name"       : "Private Key Çalınması (Drainer Saldırısı)",
        "description": "Farklı IP'den aşırı Gas Fee ile cüzdan boşaltma girişimi.",
        "expected"   : "TRIGGER_PANIC_MODE",
        "payload"    : {
            "Islem_Sikligi" : 2.0,
            "IP_Sapmasi"    : 0.95,
            "Gas_Sapmasi"   : 15.5,
        },
    },
]

SEPARATOR = "=" * 65
THIN_SEP  = "-" * 65


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _wait_for_server(max_retries: int = 10, delay: float = 1.0) -> bool:
    """
    Sunucunun hazır olmasını bekler (health check polling).

    Args:
        max_retries : Maksimum deneme sayısı.
        delay       : Denemeler arası bekleme süresi (saniye).

    Returns:
        bool: Sunucu hazırsa True, değilse False.
    """
    print(f"  Sunucu bağlantısı bekleniyor ({HEALTH_URL})...")
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(HEALTH_URL, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("model_loaded"):
                    print(f"  ✅ Sunucu hazır (deneme {attempt}/{max_retries})")
                    return True
        except requests.exceptions.ConnectionError:
            pass
        print(f"  ⏳ Bekleniyor... ({attempt}/{max_retries})")
        time.sleep(delay)
    return False


def _send_predict_request(
    payload: Dict[str, float],
    timeout: int = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """
    /predict endpoint'ine POST isteği gönderir.

    Args:
        payload : JSON gövdesi olarak gönderilecek sözlük.
        timeout : İstek zaman aşımı (saniye).

    Returns:
        Dict: {'http_status': int, 'body': dict, 'latency_ms': float}
    """
    start = time.perf_counter()
    try:
        response = requests.post(
            url     = PREDICT_URL,
            json    = payload,
            timeout = timeout,
            headers = {"Content-Type": "application/json"},
        )
        latency_ms = (time.perf_counter() - start) * 1000
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        return {
            "http_status" : response.status_code,
            "body"        : body,
            "latency_ms"  : round(latency_ms, 2),
            "error"       : None,
        }

    except requests.exceptions.ConnectionError:
        return {
            "http_status" : None,
            "body"        : {},
            "latency_ms"  : 0.0,
            "error"       : "Bağlantı hatası — Sunucu çalışıyor mu?",
        }
    except requests.exceptions.Timeout:
        return {
            "http_status" : None,
            "body"        : {},
            "latency_ms"  : 0.0,
            "error"       : f"Zaman aşımı ({timeout}s)",
        }


def _print_scenario_result(
    idx     : int,
    scenario: Dict[str, Any],
    result  : Dict[str, Any],
) -> bool:
    """
    Tek bir senaryo sonucunu konsola yapılandırılmış biçimde yazdırır.

    Args:
        idx      : Senaryo sıra numarası.
        scenario : TEST_SCENARIOS'dan alınan senaryo tanımı.
        result   : _send_predict_request() çıktısı.

    Returns:
        bool: Test geçtiyse True.
    """
    print(f"\n--- Senaryo {idx}: {scenario['name']} ---")
    print(f"  Açıklama : {scenario['description']}")
    print(f"  Payload  : {json.dumps(scenario['payload'], ensure_ascii=False)}")
    print()

    # Bağlantı / zaman aşımı hatası
    if result["error"]:
        print(f"  ❌ İSTEK HATASI: {result['error']}")
        return False

    http_status = result["http_status"]
    body        = result["body"]
    latency     = result["latency_ms"]

    print(f"  HTTP Durum Kodu : {http_status}")
    print(f"  Yanıt Süresi    : {latency} ms")
    print()

    if http_status != 200:
        print(f"  ❌ Beklenmeyen HTTP durumu: {http_status}")
        print(f"     Yanıt gövdesi: {json.dumps(body, ensure_ascii=False, indent=4)}")
        return False

    # Başarılı yanıtı göster
    print(f"  ✅ Yanıt Gövdesi:")
    print(f"     status     : {body.get('status', 'N/A')}")
    print(f"     risk_score : %{body.get('risk_score', 0):.2f}")
    print(f"     action     : {body.get('action', 'N/A')}")
    print(f"     pqc_tier   : {body.get('pqc_tier', 'N/A')}")

    # Beklenen eylem kontrolü
    actual_action   = body.get("action", "")
    expected_action = scenario["expected"]
    passed          = actual_action == expected_action

    print()
    if passed:
        print(f"  ✅ TEST GEÇTİ — Beklenen: '{expected_action}' | Alınan: '{actual_action}'")
    else:
        print(f"  ❌ TEST BAŞARISIZ — Beklenen: '{expected_action}' | Alınan: '{actual_action}'")

    return passed


# ─────────────────────────────────────────────────────────────────────────────
# Ana Test Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def run_api_tests() -> None:
    """
    Tüm test senaryolarını çalıştırır, sonuçları yazdırır ve özet tablo verir.

    Çıkış kodu:
        0 → Tüm testler geçti
        1 → En az bir test başarısız oldu
    """
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE AI Guardian — API Test İstemcisi")
    print(SEPARATOR)
    print(f"  Hedef URL  : {PREDICT_URL}")
    print(f"  Senaryo #  : {len(TEST_SCENARIOS)}")
    print(SEPARATOR)

    # ── Sağlık Kontrolü ───────────────────────────────────────────────────────
    print()
    print("[ÖN KONTROL] Sunucu sağlık durumu kontrol ediliyor...")
    server_ready = _wait_for_server(max_retries=8, delay=1.0)

    if not server_ready:
        print()
        print("  ❌ Sunucuya bağlanılamadı!")
        print("  Çözüm: Önce 'python run_server.py' komutunu çalıştırın.")
        print()
        sys.exit(1)

    # ── Test Senaryoları ───────────────────────────────────────────────────────
    print()
    print("[TEST] Senaryolar çalıştırılıyor...")
    print(THIN_SEP)

    passed_count = 0
    failed_count = 0
    results_log  = []

    for idx, scenario in enumerate(TEST_SCENARIOS, start=1):
        result = _send_predict_request(scenario["payload"])
        passed = _print_scenario_result(idx, scenario, result)

        if passed:
            passed_count += 1
        else:
            failed_count += 1

        results_log.append({
            "scenario"    : scenario["name"],
            "passed"      : passed,
            "risk_score"  : result["body"].get("risk_score", None),
            "action"      : result["body"].get("action", None),
            "pqc_tier"    : result["body"].get("pqc_tier", None),
            "latency_ms"  : result["latency_ms"],
        })

    # ── Özet Tablo ────────────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    print("  TEST ÖZET TABLOSU")
    print(SEPARATOR)

    col_w = 40
    print(f"  {'Senaryo':<{col_w}} {'Risk%':>7}  {'Eylem':<22}  {'Sonuç':>8}")
    print(f"  {'-'*col_w} {'-'*7}  {'-'*22}  {'-'*8}")

    for log in results_log:
        name_short = log["scenario"][:col_w]
        risk_str   = f"%{log['risk_score']:.2f}" if log["risk_score"] is not None else "N/A"
        action_str = (log["action"] or "N/A")[:22]
        status_str = "✅ GEÇTİ" if log["passed"] else "❌ BAŞARISIZ"
        print(f"  {name_short:<{col_w}} {risk_str:>7}  {action_str:<22}  {status_str:>8}")

    print()
    print(f"  Toplam   : {len(TEST_SCENARIOS)} senaryo")
    print(f"  Geçen    : {passed_count} ✅")
    print(f"  Başarısız: {failed_count} {'✅' if failed_count == 0 else '❌'}")
    print()

    if failed_count == 0:
        print("  🎉 TÜM TESTLER BAŞARILI — Q-ADAPTIVE API üretime hazır!")
    else:
        print("  ⚠️  BAZI TESTLER BAŞARISIZ — Loglara bakın.")

    print(SEPARATOR)
    print()

    # Başarısız test varsa hata koduyla çık
    sys.exit(0 if failed_count == 0 else 1)


# ─────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_api_tests()
