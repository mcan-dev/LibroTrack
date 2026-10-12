"""
LibroTrack Konfigürasyonu ve Loglama Altyapısı.

Ayarlar ``.env`` dosyasından okunur; tanımlı değilse varsayılan değerler
kullanılır. Projede tekrar eden sabitler (dosya adları, API adresi vb.)
magic string olarak dağılmasın diye burada tek yerde toplanır.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

# --- .env ile değiştirilebilen ayarlar ---
DB_PATH: str = os.getenv("DB_PATH", "librotrack.db")
LOG_FILE: str = os.getenv("LOG_FILE", "librotrack.log")


def _log_seviyesi_coz(ad: str) -> int:
    """Log seviyesi adını (ör. 'DEBUG') sayısal değere çevirir.

    Args:
        ad: .env dosyasından gelen seviye adı.

    Returns:
        Geçerli bir seviye adıysa karşılığı, değilse ``logging.INFO``.
    """
    seviye = getattr(logging, ad.strip().upper(), logging.INFO)
    return seviye if isinstance(seviye, int) else logging.INFO


LOG_LEVEL: int = _log_seviyesi_coz(os.getenv("LOG_LEVEL", "INFO"))

# --- Sabitler ---
VARSAYILAN_KULLANICI: str = "default_user"
OPEN_LIBRARY_TEMEL_URL: str = "https://openlibrary.org"
API_ZAMAN_ASIMI_SANIYE: int = 5
CSV_DOSYA_ADI: str = "okunan_kitaplar.csv"
GRAFIK_DOSYA_ADI: str = "okuma_grafigi.png"
AYLIK_GRAFIK_DOSYA_ADI: str = "aylik_okuma_grafigi.png"
KAPAK_KLASORU: str = "kapaklar"
KAPAK_BOYUT_SINIRI_BAYT: int = 5 * 1024 * 1024


def setup_logger() -> logging.Logger:
    """Uygulama genelinde kullanılacak loglama altyapısını kurar.

    Log dosyasına DEBUG ve üstü her zaman yazılır. Konsola ise
    ``LOG_LEVEL`` (varsayılan INFO) ve üstü düşer; konsolu sessizleştirmek
    için .env içinde ``LOG_LEVEL=WARNING`` yazılabilir.

    Returns:
        Yapılandırılmış log nesnesi.
    """
    log = logging.getLogger("LibroTrackLogger")
    log.setLevel(logging.DEBUG)

    # Neden: Handler'lar zaten ekliyse tekrar eklemeyerek çoklu log
    # basımını engelliyoruz.
    if log.handlers:
        return log

    konsol = logging.StreamHandler()
    konsol.setLevel(LOG_LEVEL)
    konsol.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(konsol)

    try:
        dosya = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError as hata:
        # Neden: Log dosyası açılamıyorsa (yazma izni yok vb.) program
        # import aşamasında çökmesin; yalnızca konsola uyarı verelim.
        log.warning("Log dosyası açılamadı (%s): %s", LOG_FILE, hata)
    else:
        dosya.setLevel(logging.DEBUG)
        dosya.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - "
            "%(message)s"
        ))
        log.addHandler(dosya)

    return log


# Log nesnesi projenin her yerinde kullanılmak üzere dışa aktarılır.
logger: logging.Logger = setup_logger()
