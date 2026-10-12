"""
LibroTrack grafik üretimi (matplotlib).

Tür dağılımı pasta grafiği ve aylık okuma çubuk grafiği burada üretilir.
CLI katmanından ayrı tutulur; böylece çizim kodu komut işleme koduna
karışmaz ve tek başına test edilebilir.
"""

from collections.abc import Mapping, Sequence

from src.config import AYLIK_GRAFIK_DOSYA_ADI, GRAFIK_DOSYA_ADI, logger
from src.exceptions import DisaAktarimHatasi

AY_ADLARI = ("Oca", "Şub", "Mar", "Nis", "May", "Haz",
             "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")


def tur_grafigi_olustur(dagilim: Mapping[str, int],
                        dosya_adi: str = GRAFIK_DOSYA_ADI) -> bool:
    """Kitapların türlerine göre yüzdesel dağılımını pasta grafiği yapar.

    Args:
        dagilim: ``{tür: kitap sayısı}`` sözlüğü.
        dosya_adi: Grafiğin kaydedileceği .png dosyası.

    Returns:
        Grafik çizildiyse ``True``; çizilecek veri yoksa ``False``.

    Raises:
        DisaAktarimHatasi: Dosya yazılamazsa.
    """
    if not dagilim:
        return False

    # Neden: Matplotlib ağır bir kütüphanedir. CLI hızını düşürmemek için
    # yalnızca grafik çizileceği an içe aktarılır (lazy import).
    from matplotlib.figure import Figure

    sekil = Figure(figsize=(6, 6))
    eksen = sekil.subplots()
    eksen.pie(list(dagilim.values()), labels=list(dagilim.keys()),
              autopct="%1.1f%%", startangle=140)
    eksen.set_title("Tür Dağılımı")
    try:
        sekil.savefig(dosya_adi)
    except OSError as hata:
        raise DisaAktarimHatasi(
            f"Grafik dosyası yazılamadı: {hata}") from hata
    logger.info("Tür grafiği kaydedildi: %s", dosya_adi)
    return True


def aylik_grafik_olustur(aylik: Sequence[Mapping[str, int]], yil: int,
                         dosya_adi: str = AYLIK_GRAFIK_DOSYA_ADI) -> bool:
    """Bir yılın aylık bitirilen kitap sayısını çubuk grafik yapar.

    Args:
        aylik: ``Kutuphane.aylik_okuma_getir`` çıktısı (12 eleman).
        yil: Grafik başlığında gösterilecek yıl.
        dosya_adi: Grafiğin kaydedileceği .png dosyası.

    Returns:
        Grafik çizildiyse ``True``; o yıl hiç kitap bitirilmediyse
        ``False``.

    Raises:
        DisaAktarimHatasi: Dosya yazılamazsa.
    """
    sayilar = [ay["kitap_sayisi"] for ay in aylik]
    if not any(sayilar):
        return False

    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    sekil = Figure(figsize=(9, 5))
    eksen = sekil.subplots()
    cubuklar = eksen.bar(AY_ADLARI, sayilar, color="#66b3ff")
    # Neden: Grafiği sade tutmak için değeri 0 olan ayların üzerine
    # etiket basılmaz.
    eksen.bar_label(cubuklar, labels=[str(s) if s else "" for s in sayilar],
                    padding=3)
    eksen.set_title(f"{yil} Aylık Okuma Grafiği")
    eksen.set_ylabel("Bitirilen kitap sayısı")
    eksen.yaxis.set_major_locator(MaxNLocator(integer=True))
    sekil.tight_layout()
    try:
        sekil.savefig(dosya_adi)
    except OSError as hata:
        raise DisaAktarimHatasi(
            f"Grafik dosyası yazılamadı: {hata}") from hata
    logger.info("Aylık grafik kaydedildi: %s", dosya_adi)
    return True
