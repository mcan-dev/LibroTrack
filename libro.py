"""
LibroTrack ana giriş noktası (Presentation Layer / CLI).

Komutları ``argparse`` ile ayrıştırır, ilgili işleyici fonksiyona yönlendirir
ve iş mantığını ``Kutuphane`` sınıfına bırakır. Bu dosya yalnızca kullanıcıyla
konuşur (girdi okuma, çıktı yazdırma, çıkış kodu); kural ve SQL içermez.
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date

from src.config import (AYLIK_GRAFIK_DOSYA_ADI, CSV_DOSYA_ADI,
                        GRAFIK_DOSYA_ADI, logger)
from src.exceptions import GecersizParametreError, LibroTrackError
from src.grafikler import AY_ADLARI, aylik_grafik_olustur, tur_grafigi_olustur
from src.library import Kutuphane
from src.models import DURUMLAR, Kitap

Komut = Callable[[Kutuphane, int, argparse.Namespace], None]
ProfilKomut = Callable[[Kutuphane, argparse.Namespace], None]

# Tablo sütunları: (başlık, kayıt anahtarı, azami genişlik).
TABLO_SUTUNLARI = (("ISBN", "isbn", 14), ("Başlık", "baslik", 28),
                   ("Yazar", "yazar", 22), ("Tür", "tur", 14),
                   ("Sayfa", "sayfa_sayisi", 6), ("Durum", "durum", 9))


# --- Argüman tipleri -------------------------------------------------------
def pozitif_tam_sayi(deger: str) -> int:
    """argparse için 0'dan büyük tam sayı dönüştürücüsü.

    Args:
        deger: Komut satırından gelen metin.

    Returns:
        Pozitif tam sayı.

    Raises:
        argparse.ArgumentTypeError: Değer sayı değilse veya 0'dan büyük
            değilse.
    """
    try:
        sayi = int(deger)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{deger}' geçerli bir tam sayı değil") from None
    if sayi <= 0:
        raise argparse.ArgumentTypeError("0'dan büyük olmalıdır")
    return sayi


def negatif_olmayan_tam_sayi(deger: str) -> int:
    """argparse için 0 veya daha büyük tam sayı dönüştürücüsü.

    Raises:
        argparse.ArgumentTypeError: Değer sayı değilse veya negatifse.
    """
    try:
        sayi = int(deger)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{deger}' geçerli bir tam sayı değil") from None
    if sayi < 0:
        raise argparse.ArgumentTypeError("negatif olamaz")
    return sayi


def tarih_tipi(deger: str) -> str:
    """argparse için YYYY-AA-GG biçimli tarih dönüştürücüsü.

    Returns:
        ISO biçimine normalize edilmiş tarih metni.

    Raises:
        argparse.ArgumentTypeError: Tarih geçerli değilse.
    """
    try:
        return date.fromisoformat(deger).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{deger}' geçerli bir tarih değil (YYYY-AA-GG)") from None


# --- Çıktı yardımcıları ----------------------------------------------------
def _kisalt(metin: str, genislik: int) -> str:
    """Metni sütun genişliğine sığdırır; taşarsa sonuna '…' ekler."""
    return metin if len(metin) <= genislik else metin[:genislik - 1] + "…"


def tablo_yazdir(kitaplar: Sequence[Mapping[str, object]]) -> None:
    """Kitap kayıtlarını hizalı bir tablo olarak ekrana yazdırır.

    Args:
        kitaplar: ``Kutuphane.kitaplari_listele`` çıktısı.
    """
    # Neden: Boş (None) değerler tabloda 'None' yazmasın diye '-' gösterilir.
    satirlar = [[_kisalt(str(k.get(anahtar) or "-"), sinir)
                 for _, anahtar, sinir in TABLO_SUTUNLARI]
                for k in kitaplar]
    basliklar = [baslik for baslik, _, _ in TABLO_SUTUNLARI]
    # Neden: Her sütun, içindeki en uzun değere göre genişler; böylece
    # kısa listelerde tablo gereksiz yere geniş görünmez.
    genislikler = [max(len(satir[i]) for satir in [basliklar, *satirlar])
                   for i in range(len(basliklar))]

    def bicimle(hucreler: Sequence[str]) -> str:
        return "  ".join(h.ljust(g) for h, g in zip(hucreler, genislikler))

    print(bicimle(basliklar))
    print("  ".join("-" * g for g in genislikler))
    for satir in satirlar:
        print(bicimle(satir))
    print(f"\nToplam: {len(satirlar)} kitap")


# --- Profil komutları ------------------------------------------------------
def komut_kullanici_ekle(kutuphane: Kutuphane,
                         args: argparse.Namespace) -> None:
    """Yeni kullanıcı profili oluşturur (``kullanici-ekle``)."""
    kutuphane.kullanici_ekle(args.ad)
    print(f"Başarı: '{args.ad.strip()}' profili oluşturuldu.")


def komut_kullanici_listele(kutuphane: Kutuphane,
                            args: argparse.Namespace) -> None:
    """Profilleri listeler; aktif olanı '*' ile işaretler."""
    kullanicilar = kutuphane.kullanicilari_listele()
    if not kullanicilar:
        print("Henüz kayıtlı kullanıcı yok.")
        return
    print("\n--- KULLANICILAR ---")
    for k in kullanicilar:
        isaret = "*" if k["kullanici_adi"] == args.user else " "
        print(f"{isaret} {k['kullanici_adi']} ({k['kitap_sayisi']} kitap)")


def komut_kullanici_sil(kutuphane: Kutuphane,
                        args: argparse.Namespace) -> None:
    """Kullanıcı profilini tüm verisiyle siler (``--onayla`` gerekir).

    Raises:
        GecersizParametreError: ``--onayla`` verilmediyse.
    """
    # Neden: Tüm kitaplığı silen tehlikeli bir işlem olduğu için
    # yanlışlıkla çalışmasın diye açık onay istenir.
    if not args.onayla:
        raise GecersizParametreError("Onaylamak için --onayla ekleyin.")
    kutuphane.kullanici_sil(args.ad)
    print(f"Başarı: '{args.ad.strip()}' profili silindi.")


# --- Kitap komutları -------------------------------------------------------
def komut_kitap_ekle(kutuphane: Kutuphane, k_id: int,
                     args: argparse.Namespace) -> None:
    """Kitap ekler; ISBN Open Library'de bulunursa eksik alanları doldurur.

    Raises:
        GecersizParametreError: API'de bulunamayan kitapta başlık veya
            yazar verilmediyse.
    """
    print(f"[*] {args.isbn} aranıyor...")
    kitap = kutuphane.api_kitap_sorgula(args.isbn)
    if kitap:
        print(f"API Verisi -> Başlık: {kitap.baslik} | Yazar: {kitap.yazar}"
              f" | Sayfa: {kitap.sayfa_sayisi}")
        # Neden: Terminalden girilen değerler her zaman API verisini
        # ezmelidir (kullanıcı önceliği).
        if args.baslik:
            kitap.baslik = args.baslik
        if args.yazar:
            kitap.yazar = args.yazar
        if args.tur:
            kitap.tur = args.tur
        if args.sayfa_sayisi is not None:
            kitap.sayfa_sayisi = args.sayfa_sayisi
    else:
        if not args.baslik or not args.yazar:
            raise GecersizParametreError(
                "API'de bulunamadı. --baslik ve --yazar zorunludur.")
        kitap = Kitap(args.isbn, args.baslik, args.yazar,
                      args.tur or "Genel", args.sayfa_sayisi)

    kutuphane.kitap_ekle(k_id, kitap, args.durum, args.bitis_tarihi)
    print(f"Başarı: '{kitap.baslik}' ({args.durum}) eklendi.")


def komut_kitap_sil(kutuphane: Kutuphane, k_id: int,
                    args: argparse.Namespace) -> None:
    """Kitabı ve ona bağlı notları siler (``kitap-sil``)."""
    kutuphane.kitap_sil(k_id, args.isbn)
    print("Başarı: Kitap silindi.")


def komut_kitap_guncelle(kutuphane: Kutuphane, k_id: int,
                         args: argparse.Namespace) -> None:
    """Kitabın türünü ve/veya sayfa sayısını günceller."""
    kutuphane.kitap_guncelle(k_id, args.isbn, args.tur, args.sayfa_sayisi)
    print("Başarı: Kitap güncellendi.")


def komut_kitap_listele(kutuphane: Kutuphane, k_id: int,
                        args: argparse.Namespace) -> None:
    """Kitapları tablo olarak listeler; --durum ve --tur ile filtreler."""
    kitaplar = kutuphane.kitaplari_listele(k_id, args.durum, args.tur)
    if not kitaplar:
        print("Listenizde uygun kitap bulunmuyor.")
        return
    tablo_yazdir(kitaplar)


def komut_kitap_detay(kutuphane: Kutuphane, k_id: int,
                      args: argparse.Namespace) -> None:
    """Tek kitabın ayrıntılarını gösterir; istenirse kapağı indirir."""
    d = kutuphane.kitap_detay(k_id, args.isbn)
    print(f"\nBaşlık: {d['baslik']}\nYazar: {d['yazar']}\n"
          f"ISBN: {d['isbn']}\nTür: {d['tur']}\n"
          f"Sayfa: {d['sayfa_sayisi']}\nDurum: {d['durum']}")
    if args.kapak_indir:
        yol = kutuphane.kapak_indir(k_id, args.isbn)
        print(f"Başarı: Kapak '{yol}' konumuna kaydedildi.")


def komut_kitap_ara(kutuphane: Kutuphane, k_id: int,
                    args: argparse.Namespace) -> None:
    """Başlık veya yazarda anahtar kelime arar; sonucu tablo yazar."""
    sonuclar = kutuphane.kitap_ara(k_id, args.anahtar_kelime)
    if not sonuclar:
        print("Kitap bulunamadı.")
        return
    tablo_yazdir(sonuclar)


def komut_durum_guncelle(kutuphane: Kutuphane, k_id: int,
                         args: argparse.Namespace) -> None:
    """Okuma durumunu değiştirir; 'okundu' ise bitiş tarihi atanır."""
    kutuphane.durum_guncelle(k_id, args.isbn, args.durum, args.bitis_tarihi)
    print(f"Başarı: Durum '{args.durum}' yapıldı.")


def komut_not_ekle(kutuphane: Kutuphane, k_id: int,
                   args: argparse.Namespace) -> None:
    """Kitaba not veya alıntı ekler (``--not`` ya da ``--metin``)."""
    kutuphane.not_ekle(k_id, args.isbn, args.metin, args.sayfa)
    print("Başarı: Not eklendi.")


def komut_not_listele(kutuphane: Kutuphane, k_id: int,
                      args: argparse.Namespace) -> None:
    """Kitaba ait tüm notları sayfa numarasıyla listeler."""
    notlar = kutuphane.notlari_listele(k_id, args.isbn)
    if not notlar:
        print("Not bulunamadı.")
        return
    for n in notlar:
        sayfa = n["sayfa"] if n["sayfa"] is not None else "-"
        print(f"- {n['not_metni']} (Sayfa: {sayfa})")


def komut_istatistik(kutuphane: Kutuphane, k_id: int,
                     args: argparse.Namespace) -> None:
    """Özet istatistikleri yazar; tür ve aylık grafikleri kaydeder."""
    ist = kutuphane.istatistik_getir(k_id)
    toplam = ist["okunacak"] + ist["okunuyor"] + ist["okundu"]
    print(f"\nToplam kitap: {toplam}")
    print(f"Okunacak: {ist['okunacak']} | Okunuyor: {ist['okunuyor']} | "
          f"Okundu: {ist['okundu']}")
    print(f"Tamamlanan toplam sayfa: {ist['toplam_sayfa']}")

    if tur_grafigi_olustur(kutuphane.tur_dagilimi_getir(k_id)):
        print(f"Tür dağılımı grafiği kaydedildi: {GRAFIK_DOSYA_ADI}")

    yil = args.yil or date.today().year
    aylik = kutuphane.aylik_okuma_getir(k_id, yil)
    for ay in aylik:
        if ay["kitap_sayisi"]:
            print(f"{AY_ADLARI[ay['ay'] - 1]}: {ay['kitap_sayisi']} kitap")
    if aylik_grafik_olustur(aylik, yil):
        print(f"Aylık grafik kaydedildi: {AYLIK_GRAFIK_DOSYA_ADI}")


def komut_disa_aktar(kutuphane: Kutuphane, k_id: int,
                     args: argparse.Namespace) -> None:
    """Okunmuş kitapları CSV dosyasına aktarır."""
    kutuphane.csv_disa_aktar(k_id, CSV_DOSYA_ADI)
    print(f"Başarı: CSV dosyası oluşturuldu: {CSV_DOSYA_ADI}")


# Neden: Uzun bir if-elif zinciri yerine komut adı doğrudan işleyiciye
# eşlenir; yeni komut eklemek yalnızca bu sözlüğe bir satır eklemektir.
KOMUTLAR: dict[str, Komut] = {
    "kitap-ekle": komut_kitap_ekle,
    "kitap-sil": komut_kitap_sil,
    "kitap-guncelle": komut_kitap_guncelle,
    "kitap-listele": komut_kitap_listele,
    "kitap-detay": komut_kitap_detay,
    "kitap-ara": komut_kitap_ara,
    "durum-guncelle": komut_durum_guncelle,
    "not-ekle": komut_not_ekle,
    "not-listele": komut_not_listele,
    "istatistik": komut_istatistik,
    "disa-aktar": komut_disa_aktar,
}
PROFIL_KOMUTLARI: dict[str, ProfilKomut] = {
    "kullanici-ekle": komut_kullanici_ekle,
    "kullanici-listele": komut_kullanici_listele,
    "kullanici-sil": komut_kullanici_sil,
}


# --- Parser ----------------------------------------------------------------
def parser_olustur() -> argparse.ArgumentParser:
    """Tüm alt komutları ve argümanlarını tanımlayan ayrıştırıcıyı kurar.

    Returns:
        Yapılandırılmış ``ArgumentParser``.
    """
    p = argparse.ArgumentParser(description="LibroTrack")
    # Neden: Çoklu kullanıcı, tüm komutlar için ortak bir -u parametresiyle
    # yönetilir; verilmezse varsayılan kullanıcı devreye girer.
    p.add_argument("-u", "--user", default="default_user")
    alt = p.add_subparsers(dest="komut")

    ekle = alt.add_parser("kitap-ekle")
    ekle.add_argument("--isbn", required=True)
    ekle.add_argument("--baslik")
    ekle.add_argument("--yazar")
    ekle.add_argument("--tur")
    ekle.add_argument("--sayfa-sayisi", type=pozitif_tam_sayi)
    ekle.add_argument("--durum", choices=DURUMLAR, default="okunacak")
    ekle.add_argument("--bitis-tarihi", type=tarih_tipi)

    sil = alt.add_parser("kitap-sil")
    sil.add_argument("--isbn", required=True)

    guncelle = alt.add_parser("kitap-guncelle")
    guncelle.add_argument("--isbn", required=True)
    guncelle.add_argument("--tur")
    guncelle.add_argument("--sayfa-sayisi", type=pozitif_tam_sayi)

    listele = alt.add_parser("kitap-listele")
    listele.add_argument("--durum", choices=DURUMLAR)
    listele.add_argument("--tur")

    detay = alt.add_parser("kitap-detay")
    detay.add_argument("--isbn", required=True)
    detay.add_argument("--kapak-indir", action="store_true")

    ara = alt.add_parser("kitap-ara")
    ara.add_argument("--anahtar-kelime", required=True)

    durum = alt.add_parser("durum-guncelle")
    durum.add_argument("--isbn", required=True)
    durum.add_argument("--durum", choices=DURUMLAR, required=True)
    durum.add_argument("--bitis-tarihi", type=tarih_tipi)

    not_ekle = alt.add_parser("not-ekle")
    not_ekle.add_argument("--isbn", required=True)
    # Neden: Ödev metni '--not' kullanıyor; 'not' Python'da ayrılmış bir
    # sözcük olduğundan değer 'metin' adıyla okunur. '--metin' eski
    # kullanımlar için takma ad olarak kalır.
    not_ekle.add_argument("--not", "--metin", dest="metin", required=True)
    not_ekle.add_argument("--sayfa", type=negatif_olmayan_tam_sayi)

    not_listele = alt.add_parser("not-listele")
    not_listele.add_argument("--isbn", required=True)

    istatistik = alt.add_parser("istatistik")
    istatistik.add_argument("--yil", type=pozitif_tam_sayi)

    alt.add_parser("disa-aktar")

    k_ekle = alt.add_parser("kullanici-ekle")
    k_ekle.add_argument("--ad", required=True)
    alt.add_parser("kullanici-listele")
    k_sil = alt.add_parser("kullanici-sil")
    k_sil.add_argument("--ad", required=True)
    k_sil.add_argument("--onayla", action="store_true")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Programın giriş fonksiyonu.

    Args:
        argv: Komut satırı argümanları; ``None`` ise ``sys.argv`` kullanılır.

    Returns:
        Çıkış kodu: 0 başarı, 1 hata, 130 kullanıcı iptali.
    """
    parser = parser_olustur()
    args = parser.parse_args(argv)
    if not args.komut:
        parser.print_help()
        return 1
    try:
        # Neden: Bağlantı try bloğunun İÇİNDE kurulur; veritabanı
        # açılamazsa program Traceback ile çökmek yerine temiz hata verir.
        kutuphane = Kutuphane()
        logger.info("Komut: %s | Kullanıcı: %s", args.komut, args.user)
        if args.komut in PROFIL_KOMUTLARI:
            PROFIL_KOMUTLARI[args.komut](kutuphane, args)
        else:
            k_id = kutuphane.aktif_kullanici(args.user)
            KOMUTLAR[args.komut](kutuphane, k_id, args)
    except LibroTrackError as hata:
        # Neden: Beklenen hatalar ekrana temiz mesajla basılır; ayrıntı
        # log dosyasına yazılır.
        logger.info("Başarısız (%s): %s", args.komut, hata)
        print(f"\nHata: {hata}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nİptal edildi.", file=sys.stderr)
        return 130
    except Exception:
        # Neden: Son güvenlik ağı. Öngörülemeyen bir hata kullanıcıya
        # Traceback göstermesin; tam ayrıntı (exc_info) log dosyasına
        # yazılır ve program 1 koduyla kontrollü kapanır.
        logger.critical("Kritik hata", exc_info=True)
        print("\nBeklenmeyen hata. Log dosyasını inceleyin.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
