"""
Kutuphane (iş katmanı) birim testleri.

Her test, pytest'in geçici klasöründe (tmp_path) açılan izole bir SQLite
dosyası üzerinde çalışır; gerçek veritabanına (librotrack.db) ve internete
dokunulmaz.
"""

from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from src.db_manager import DBManager
from src.exceptions import (GecersizParametreError, KitapBulunamadiError,
                            KitapZatenVarError, KullaniciBulunamadiError,
                            KullaniciZatenVarError, VeritabaniHatasi)
from src.library import Kutuphane
from src.models import Kitap


@pytest.fixture
def kutuphane_kur(tmp_path):
    """Her test için geçici bir veritabanıyla temiz bir Kutuphane verir."""
    # Neden: ":memory:" kullanılamaz. DBManager her işlemde yeni bağlantı
    # açtığı için bellek içi veritabanı her bağlantıda sıfırlanır ve
    # tablolar kaybolurdu. Geçici dosya ise test bitince otomatik silinir.
    return Kutuphane(db=DBManager(str(tmp_path / "test.db")))


@pytest.fixture
def k_id(kutuphane_kur):
    """'test_user' profilinin veritabanı kimliğini verir."""
    return kutuphane_kur.kullanici_getir_veya_olustur("test_user")


# --- KULLANICI PROFİLLERİ (ÇOKLU KULLANICI) ---

def test_kullanici_getir_veya_olustur(kutuphane_kur):
    # Neden: UNIQUE kısıtının aynı kullanıcıyı iki kez oluşturmasını
    # engellediğini, aynı adın aynı kimliği verdiğini test ediyoruz.
    id1 = kutuphane_kur.kullanici_getir_veya_olustur("test_user")
    id2 = kutuphane_kur.kullanici_getir_veya_olustur("test_user")
    assert id1 == id2


def test_kullanici_ekle_ve_aktif_kullanici(kutuphane_kur):
    # Neden: Profil açılır, aynısı tekrar açılamaz; kayıtsız profil
    # (yazım hatası) sessizce oluşmaz, varsayılan kullanıcı ise otomatik
    # oluşur.
    kutuphane_kur.kullanici_ekle("ayse")
    with pytest.raises(KullaniciZatenVarError):
        kutuphane_kur.kullanici_ekle("ayse")
    assert kutuphane_kur.aktif_kullanici("ayse") > 0
    with pytest.raises(KullaniciBulunamadiError):
        kutuphane_kur.aktif_kullanici("aise")
    assert kutuphane_kur.aktif_kullanici("default_user") > 0


def test_kullanicilar_birbirinin_kitapligini_goremez(kutuphane_kur):
    # Neden: Çoklu kullanıcı özelliğinin temel kuralı: her kullanıcı
    # yalnızca kendi kitaplığını görür.
    ayse = kutuphane_kur.kullanici_ekle("ayse")
    mehmet = kutuphane_kur.kullanici_ekle("mehmet")
    kutuphane_kur.kitap_ekle(ayse, Kitap("111", "Dune", "Herbert"))
    assert len(kutuphane_kur.kitaplari_listele(ayse)) == 1
    assert kutuphane_kur.kitaplari_listele(mehmet) == []


# --- OPEN LIBRARY API (SAHTE İSTEKLERLE) ---

def test_api_kitap_sorgula_basarili(kutuphane_kur):
    # Neden: İnternet olmasa bile API fonksiyonunun iş mantığını test
    # edebilmek için gerçek istek yerine sahte (Mock) yanıt kullanıyoruz.
    yanit = Mock()
    yanit.json.return_value = {"ISBN:123": {"title": "Test Kitap"}}
    with patch("src.library.requests.get", return_value=yanit):
        kitap = kutuphane_kur.api_kitap_sorgula("123")
    assert kitap.baslik == "Test Kitap"


def test_api_kitap_sorgula_kapak_ve_aciklama_getirir(kutuphane_kur):
    # Neden: Bonus özellik. Kapak adresi /api/books yanıtından, açıklama
    # ise ISBN (baskı) kaydından alınır.
    kitap_verisi = {"ISBN:123": {
        "title": "Dune", "authors": [{"name": "Frank Herbert"}],
        "number_of_pages": 412,
        "cover": {"medium": "https://covers.openlibrary.org/b/id/1-M.jpg"},
    }}

    def sahte_get(url, params=None, timeout=None):
        yanit = Mock()
        yanit.json.return_value = (
            kitap_verisi if "/api/books" in url
            else {"description": "Çöl gezegeni."}
        )
        return yanit

    with patch("src.library.requests.get", side_effect=sahte_get):
        kitap = kutuphane_kur.api_kitap_sorgula("123")
    assert kitap.yazar == "Frank Herbert"
    assert kitap.kapak_url.endswith("1-M.jpg")
    assert kitap.aciklama == "Çöl gezegeni."


def test_api_kitap_sorgula_hata_doner(kutuphane_kur):
    # Neden: Defansif programlama gereği, internet yokken sistemin
    # çökmeyip None döndüğünü teyit ediyoruz.
    with patch("src.library.requests.get",
               side_effect=requests.ConnectionError("bağlantı yok")):
        assert kutuphane_kur.api_kitap_sorgula("0000000") is None


# --- KİTAP EKLE / LİSTELE / SİL ---

def test_kitap_ekle_basarili(kutuphane_kur, k_id):
    # Neden: İş katmanının nesneleri (OOP) SQL kayıtlarına doğru
    # çevirdiğini görüyoruz.
    kitap = Kitap("111", "Suç ve Ceza", "Dostoyevski", "Roman", 600)
    kutuphane_kur.kitap_ekle(k_id, kitap, "okunacak")
    liste = kutuphane_kur.kitaplari_listele(k_id)
    assert [k["baslik"] for k in liste] == ["Suç ve Ceza"]
    assert liste[0]["durum"] == "okunacak"


def test_kitap_ekle_ayni_kitap_hata(kutuphane_kur, k_id):
    # Neden: Veritabanından dönen UNIQUE hatasının, iş katmanında anlaşılır
    # bir özel hataya (KitapZatenVarError) dönüştüğünü kanıtlıyoruz.
    kitap = Kitap("111", "Suç ve Ceza", "Dostoyevski")
    kutuphane_kur.kitap_ekle(k_id, kitap, "okunacak")
    with pytest.raises(KitapZatenVarError):
        kutuphane_kur.kitap_ekle(k_id, kitap, "okunuyor")


def test_kitaplari_listele(kutuphane_kur, k_id):
    # Neden: JOIN sorgularının ve durum filtrelemenin doğru çalıştığını
    # doğruluyoruz.
    kutuphane_kur.kitap_ekle(k_id, Kitap("111", "A", "Yazar"), "okunacak")
    kutuphane_kur.kitap_ekle(k_id, Kitap("222", "B", "Yazar"), "okundu")
    liste = kutuphane_kur.kitaplari_listele(k_id, durum="okundu")
    assert len(liste) == 1
    assert liste[0]["isbn"] == "222"


def test_kitap_sil(kutuphane_kur, k_id):
    # Neden: DELETE işleminin kitabı listeden çıkardığını, listede olmayan
    # kitabı silmeye çalışmanın ise KitapBulunamadiError verdiğini görüyoruz.
    kutuphane_kur.kitap_ekle(k_id, Kitap("111", "A", "Yazar"))
    kutuphane_kur.kitap_sil(k_id, "111")
    assert kutuphane_kur.kitaplari_listele(k_id) == []
    with pytest.raises(KitapBulunamadiError):
        kutuphane_kur.kitap_sil(k_id, "111")


def test_kitap_guncelle_sadece_kullaniciyi_etkiler(kutuphane_kur):
    # Neden: Ortak katalog sorunu: bir kullanıcının tür/sayfa düzeltmesi,
    # aynı kitabı ekleyen diğer kullanıcının görünümünü değiştirmemeli.
    ayse = kutuphane_kur.kullanici_ekle("ayse")
    mehmet = kutuphane_kur.kullanici_ekle("mehmet")
    for kullanici in (ayse, mehmet):
        kutuphane_kur.kitap_ekle(
            kullanici, Kitap("111", "Dune", "Herbert", "Roman", 400))
    kutuphane_kur.kitap_guncelle(ayse, "111", tur="Klasik",
                                 sayfa_sayisi=999)
    ayse_kitap = kutuphane_kur.kitaplari_listele(ayse)[0]
    mehmet_kitap = kutuphane_kur.kitaplari_listele(mehmet)[0]
    assert (ayse_kitap["tur"], ayse_kitap["sayfa_sayisi"]) == ("Klasik", 999)
    assert (mehmet_kitap["tur"], mehmet_kitap["sayfa_sayisi"]) == (
        "Roman", 400)


# --- ARAMA ---

def test_kitap_ara(kutuphane_kur, k_id):
    # Neden: Aramanın kelime parçaları üzerinden başlıkta ve yazarda doğru
    # sonuç getirdiğini test ediyoruz.
    kutuphane_kur.kitap_ekle(
        k_id, Kitap("111", "Yüzüklerin Efendisi", "Tolkien"))
    assert len(kutuphane_kur.kitap_ara(k_id, "Yüzük")) == 1
    assert len(kutuphane_kur.kitap_ara(k_id, "tolkien")) == 1
    assert kutuphane_kur.kitap_ara(k_id, "Roman") == []


def test_kitap_ara_turkce_buyuk_kucuk_harf_duyarsiz(kutuphane_kur, k_id):
    # Neden: SQLite'ın LIKE'ı yalnızca ASCII harflerde duyarsızdır; Türkçe
    # için "ŞİİR", "şiir" ve "siir" aramalarının aynı kitabı bulması gerekir.
    kutuphane_kur.kitap_ekle(k_id, Kitap("1", "Şiir Kitabı", "Ömer Işık"))
    for kelime in ("ŞİİR", "şiir", "siir", "ISIK", "omer"):
        assert len(kutuphane_kur.kitap_ara(k_id, kelime)) == 1, kelime


# --- DURUM VE BİTİŞ TARİHİ ---

def test_durum_guncelle_bitis_tarihi_atar(kutuphane_kur, k_id):
    # Neden: İsterlerdeki "okundu durumuna geçildiğinde bitiş tarihi
    # otomatik atanır" kuralını kanıtlıyoruz.
    kutuphane_kur.kitap_ekle(k_id, Kitap("111", "A", "Yazar"), "okunacak")
    kutuphane_kur.durum_guncelle(k_id, "111", "okundu")
    kitap = kutuphane_kur.kitaplari_listele(k_id)[0]
    assert kitap["bitis_tarihi"] == date.today().isoformat()


def test_bitis_tarihi_gecmise_donuk_verilebilir_gelecek_reddedilir(
        kutuphane_kur, k_id):
    # Neden: Aylık grafik bitiş tarihine dayanır; geçmiş tarih kabul
    # edilmeli, gelecek tarih ise reddedilmelidir.
    kutuphane_kur.kitap_ekle(k_id, Kitap("1", "A", "Y"), "okundu",
                             "2024-03-15")
    assert (kutuphane_kur.kitaplari_listele(k_id)[0]["bitis_tarihi"]
            == "2024-03-15")
    with pytest.raises(GecersizParametreError):
        kutuphane_kur.kitap_ekle(k_id, Kitap("2", "B", "Y"), "okundu",
                                 "2999-01-01")


# --- NOTLAR ---

def test_not_ekle_basarili(kutuphane_kur, k_id):
    # Neden: Notların yabancı anahtarlar üzerinden doğru okuma kaydına
    # bağlandığını teyit ediyoruz.
    kutuphane_kur.kitap_ekle(k_id, Kitap("111", "A", "Yazar"))
    kutuphane_kur.not_ekle(k_id, "111", "Çok iyi kitap", 50)
    notlar = kutuphane_kur.notlari_listele(k_id, "111")
    assert len(notlar) == 1
    assert notlar[0]["not_metni"] == "Çok iyi kitap"


def test_not_ekle_olmayan_kitap_hata(kutuphane_kur, k_id):
    # Neden: Kullanıcının listesinde olmayan bir kitaba not eklenmesini
    # engelleyen iş kuralını test ediyoruz.
    with pytest.raises(KitapBulunamadiError):
        kutuphane_kur.not_ekle(k_id, "999", "Kitap bende yok", 10)


# --- İSTATİSTİK ---

def test_istatistik_getir_dogru_hesaplar(kutuphane_kur, k_id):
    # Neden: Veritabanı motorunun (SUM ve GROUP BY) istatistikleri doğru
    # döndürdüğünü, yalnızca okunan kitapların sayfalarının toplandığını
    # teyit ediyoruz.
    kutuphane_kur.kitap_ekle(
        k_id, Kitap("111", "A", "Yazar", sayfa_sayisi=100), "okundu")
    kutuphane_kur.kitap_ekle(
        k_id, Kitap("222", "B", "Yazar", sayfa_sayisi=200), "okundu")
    kutuphane_kur.kitap_ekle(
        k_id, Kitap("333", "C", "Yazar", sayfa_sayisi=300), "okunacak")
    istatistik = kutuphane_kur.istatistik_getir(k_id)
    assert istatistik["okundu"] == 2
    assert istatistik["toplam_sayfa"] == 300


def test_aylik_okuma_getir_aylari_dogru_sayar(kutuphane_kur, k_id):
    # Neden: Bonus özellik. Aylık grafik 12 aylık veriye dayanır; mart ayında
    # biten iki kitap ile aralıkta biten bir kitap doğru aylara düşmeli,
    # okunmamış aylar 0 olmalıdır.
    yil = date.today().year - 1
    kitaplar = (("1", 100, f"{yil}-03-15"), ("2", 200, f"{yil}-03-20"),
                ("3", 50, f"{yil}-12-01"))
    for isbn, sayfa, tarih in kitaplar:
        kutuphane_kur.kitap_ekle(
            k_id, Kitap(isbn, "K" + isbn, "Y", sayfa_sayisi=sayfa),
            "okundu", tarih)
    aylik = kutuphane_kur.aylik_okuma_getir(k_id, yil)
    assert len(aylik) == 12
    assert aylik[2] == {"ay": 3, "kitap_sayisi": 2, "sayfa_sayisi": 300}
    assert aylik[11]["kitap_sayisi"] == 1
    assert aylik[0]["kitap_sayisi"] == 0


# --- VERİ KATMANI VE DIŞA AKTARIM ---

def test_acilamayan_veritabani_kontrollu_hata_verir(tmp_path):
    # Neden: Olmayan bir klasördeki veritabanı açılamaz; program traceback
    # ile çökmek yerine VeritabaniHatasi fırlatmalıdır.
    db = DBManager(str(tmp_path / "yok_klasor" / "t.db"))
    with pytest.raises(VeritabaniHatasi):
        Kutuphane(db=db)


def test_csv_disa_aktar(kutuphane_kur, k_id, tmp_path):
    # Neden: Yalnızca 'okundu' kitapların CSV'ye yazıldığını ve Türkçe
    # karakterlerin korunduğunu doğruluyoruz.
    kutuphane_kur.kitap_ekle(k_id, Kitap("1", "Şiir", "Ömer"), "okundu")
    kutuphane_kur.kitap_ekle(k_id, Kitap("2", "Roman", "Ali"), "okunacak")
    dosya = tmp_path / "okunanlar.csv"
    assert kutuphane_kur.csv_disa_aktar(k_id, str(dosya)) == 1
    icerik = dosya.read_text(encoding="utf-8-sig")
    assert "Şiir" in icerik
    assert "Roman" not in icerik


# --- TÜR FİLTRESİ VE TÜR DAĞILIMI ---

def test_kitaplari_listele_tur_filtresi(kutuphane_kur, k_id):
    # Neden: --tur filtresi yalnızca o türü getirmeli ve harf farkından
    # (Türkçe dahil) etkilenmemelidir.
    kutuphane_kur.kitap_ekle(k_id, Kitap("1", "A", "X", tur="Roman"))
    kutuphane_kur.kitap_ekle(k_id, Kitap("2", "B", "Y", tur="Şiir"))
    assert [k["isbn"] for k in
            kutuphane_kur.kitaplari_listele(k_id, tur="roman")] == ["1"]
    assert [k["isbn"] for k in
            kutuphane_kur.kitaplari_listele(k_id, tur="ŞİİR")] == ["2"]
    assert kutuphane_kur.kitaplari_listele(k_id, tur="Tarih") == []


def test_tur_dagilimi_getir(kutuphane_kur, k_id):
    # Neden: Pasta grafiğinin verisi doğru sayılmalı; türü olmayan kitap
    # 'Belirtilmemiş' altında toplanmalıdır.
    kutuphane_kur.kitap_ekle(k_id, Kitap("1", "A", "X", tur="Roman"))
    kutuphane_kur.kitap_ekle(k_id, Kitap("2", "B", "Y", tur="Roman"))
    kutuphane_kur.kitap_ekle(k_id, Kitap("3", "C", "Z"))
    assert kutuphane_kur.tur_dagilimi_getir(k_id) == {
        "Roman": 2, "Belirtilmemiş": 1}
