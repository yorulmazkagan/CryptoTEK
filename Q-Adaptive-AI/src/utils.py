# =============================================================================
# Q-ADAPTIVE AI Guardian — Yardımcı Fonksiyonlar (utils.py)
# =============================================================================
# Bu modül; klasör yönetimi, gelişmiş konsol loglama ve veri doğrulama gibi
# tekrar kullanılabilir yardımcı araçları barındırır.
# =============================================================================

import os
import sys
import logging
from datetime import datetime
from pathlib import Path


# ── Loglama Yapılandırması ────────────────────────────────────────────────────

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str = "Q-ADAPTIVE", level: int = logging.INFO) -> logging.Logger:
    """
    Proje genelinde standart bir logger örneği oluşturur ve döndürür.

    Args:
        name  : Logger adı (varsayılan: 'Q-ADAPTIVE').
        level : Log seviyesi (varsayılan: INFO).

    Returns:
        logging.Logger: Yapılandırılmış logger nesnesi.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ── Dosya Sistemi Yardımcıları ────────────────────────────────────────────────

def ensure_directory(path: str) -> Path:
    """
    Verilen yolu bir Path nesnesine dönüştürür ve klasör yoksa oluşturur.

    Args:
        path : Oluşturulacak/doğrulanacak klasör yolu.

    Returns:
        Path: Oluşturulmuş/mevcut klasörün Path nesnesi.
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_timestamped_filename(base_name: str, extension: str = "csv") -> str:
    """
    Dosya adına UTC zaman damgası ekleyerek benzersiz bir dosya adı üretir.
    Örnek: 'training_data_normal_20260616_200100.csv'

    Args:
        base_name : Temel dosya adı.
        extension : Dosya uzantısı (nokta olmadan).

    Returns:
        str: Zaman damgalı dosya adı.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}.{extension}"


# ── Konsol Görselleştirme Yardımcıları ───────────────────────────────────────

SEPARATOR = "=" * 65
THIN_SEP  = "-" * 65


def print_banner(title: str) -> None:
    """Başlık için dekoratif bir konsol banner'ı yazdırır."""
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(f"{SEPARATOR}")


def print_section(title: str) -> None:
    """Alt bölüm başlığı yazdırır."""
    print(f"\n{THIN_SEP}")
    print(f"  {title}")
    print(f"{THIN_SEP}")


def print_step(step_num: int, description: str) -> None:
    """Numaralı adım mesajı yazdırır."""
    print(f"\n[ADIM {step_num}] {description}")


# ── Veri Doğrulama Yardımcıları ───────────────────────────────────────────────

def validate_dataframe(df, expected_columns: list, min_rows: int = 1) -> bool:
    """
    Bir pandas DataFrame'in beklenen sütunlara ve minimum satır sayısına
    sahip olduğunu doğrular.

    Args:
        df               : Doğrulanacak DataFrame.
        expected_columns : Beklenen sütun adları listesi.
        min_rows         : Minimum satır sayısı eşiği.

    Returns:
        bool: Doğrulama başarılıysa True.

    Raises:
        ValueError: Sütunlar eksikse veya satır sayısı yetersizse.
    """
    missing = set(expected_columns) - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame'de eksik sütunlar: {missing}")

    if len(df) < min_rows:
        raise ValueError(
            f"DataFrame en az {min_rows} satır içermeli; mevcut: {len(df)}"
        )

    return True
