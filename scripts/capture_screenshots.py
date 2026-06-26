#!/usr/bin/env python3
# =============================================================================
# Q-ADAPTIVE AI Guardian — Screenshot Capture Automation (capture_screenshots.py)
# =============================================================================
# This script automates capturing screenshots of the unified dashboard tabs
# (in both empty and tested/filled states) and individual standalone templates
# using Firefox headless.
# =============================================================================

import os
import time
import subprocess
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "images"

# Ensure the output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# List of screenshots to take
# Format: (URL, relative output filename)
SCREENSHOTS = [
    # ── 1. Unified Dashboard - Empty States ──────────────────────────────────
    ("http://127.0.0.1:8000/?tab=telemetri", "dashboard_telemetri_empty.png"),
    ("http://127.0.0.1:8000/?tab=simulasyon", "dashboard_simulasyon_empty.png"),
    ("http://127.0.0.1:8000/?tab=zkstark", "dashboard_zkstark_empty.png"),
    ("http://127.0.0.1:8000/?tab=onchain", "dashboard_onchain_empty.png"),

    # ── 2. Unified Dashboard - Standard Scenario (Tested) ────────────────────
    ("http://127.0.0.1:8000/?tab=telemetri&mock=standart", "dashboard_telemetri_tested_standart.png"),
    ("http://127.0.0.1:8000/?tab=simulasyon&mock=standart", "dashboard_simulasyon_tested_standart.png"),
    ("http://127.0.0.1:8000/?tab=zkstark&mock=standart", "dashboard_zkstark_tested_standart.png"),
    ("http://127.0.0.1:8000/?tab=onchain&mock=standart", "dashboard_onchain_tested_standart.png"),

    # ── 3. Unified Dashboard - Bot Attack Scenario (Tested) ──────────────────
    ("http://127.0.0.1:8000/?tab=telemetri&mock=bot", "dashboard_telemetri_tested_bot.png"),
    ("http://127.0.0.1:8000/?tab=simulasyon&mock=bot", "dashboard_simulasyon_tested_bot.png"),
    ("http://127.0.0.1:8000/?tab=zkstark&mock=bot", "dashboard_zkstark_tested_bot.png"),
    ("http://127.0.0.1:8000/?tab=onchain&mock=bot", "dashboard_onchain_tested_bot.png"),

    # ── 4. Unified Dashboard - PK Drainer Scenario (Tested) ──────────────────
    ("http://127.0.0.1:8000/?tab=telemetri&mock=drainer", "dashboard_telemetri_tested_drainer.png"),
    ("http://127.0.0.1:8000/?tab=simulasyon&mock=drainer", "dashboard_simulasyon_tested_drainer.png"),
    ("http://127.0.0.1:8000/?tab=zkstark&mock=drainer", "dashboard_zkstark_tested_drainer.png"),
    ("http://127.0.0.1:8000/?tab=onchain&mock=drainer", "dashboard_onchain_tested_drainer.png"),

    # ── 5. Standalone Templates ──────────────────────────────────────────────
    ("http://127.0.0.1:8000/ui/ai_guardian_canl_telemetri_paneli_t_rk_e/code.html", "template_canli_telemetri.png"),
    ("http://127.0.0.1:8000/ui/sim_lasyon_enjekt_r_paneli_t_rk_e/code.html", "template_simulasyon_enjektoru.png"),
    ("http://127.0.0.1:8000/ui/zk_stark_kriptografik_mant_k_paneli_t_rk_e/code.html", "template_zkstark_mantigi.png"),
    ("http://127.0.0.1:8000/ui/on_chain_durum_i_zleyicisi_t_rk_e/code.html", "template_onchain_izleyici.png"),
]

def capture_screenshot(url: str, output_name: str):
    """
    Captures a screenshot of the given URL using Firefox headless.
    Renames the default 'screenshot.png' to output_name in the images/ directory.
    """
    # Clean up any leftover screenshot.png
    default_ss = BASE_DIR / "screenshot.png"
    if default_ss.exists():
        default_ss.unlink()

    print(f"📷 Capturing: {url}")
    print(f"   Saving as: images/{output_name}")

    # Firefox command
    cmd = [
        "firefox",
        "--headless",
        "--window-size", "1920,1080",
        "--screenshot",
        url
    ]

    try:
        # Run Firefox headless
        # We redirect stderr to devnull to avoid cluttering the output with Mozilla warnings
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(BASE_DIR))
        
        # Check if screenshot was created
        if default_ss.exists():
            target_path = OUTPUT_DIR / output_name
            # Overwrite if exists
            if target_path.exists():
                target_path.unlink()
            default_ss.rename(target_path)
            print(f"   ✅ Done! (Size: {target_path.stat().st_size / 1024:.1f} KB)\n")
        else:
            print(f"   ❌ Error: screenshot.png was not generated.\n")
            
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Firefox command failed with error: {e}\n")
    except Exception as e:
        print(f"   ❌ Unexpected error occurred: {e}\n")

def main():
    print("=" * 70)
    print("  Q-ADAPTIVE AI Guardian — Screenshot Capture Automation")
    print("=" * 70)
    print(f"Target directory: {OUTPUT_DIR}\n")

    t_start = time.time()
    
    # Process each screenshot sequentially
    for url, output_name in SCREENSHOTS:
        capture_screenshot(url, output_name)
        # Small cooldown between requests
        time.sleep(1)
        
    duration = time.time() - t_start
    print("=" * 70)
    print(f"🎉 Completed! Captured {len(SCREENSHOTS)} screenshots in {duration:.1f} seconds.")
    print("=" * 70)

if __name__ == "__main__":
    main()
