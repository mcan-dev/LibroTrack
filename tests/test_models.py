"""Model sınıflarının (Kullanici, Kitap, OkumaKaydi, Not) birim testleri."""

import pytest
from src.models import Kullanici, Kitap, OkumaKaydi, Not
from src.exceptions import GecersizParametreError


def test_kullanici_basarili_olusturma():
    # Neden: Sistemin temel yapı taşı olan Kullanıcı nesnesinin verileri
    # doğru kapsüllediğini (encapsulation) teyit ediyoruz.
    user = Kullanici("test_user", 1)
    assert user.kullanici_adi == "test_user"


def test_kullanici_str_metodu():
    # Neden: CLI ekranında anlamsız bellek adresleri yerine okunaklı
    # metin gösterildiğini garanti ediyoruz.
    user = Kullanici("test_user")
    assert str(user) == "Kullanıcı: test_user"


def test_kitap_basarili_olusturma():
    # Neden: Nesne özelliklerinin (property) bellekte doğru atandığını
    # doğruluyoruz.
    kitap = Kitap("111", "Dune", "Frank Herbert", "Bilim Kurgu", 500)
    assert kitap.baslik == "Dune"
    assert kitap.sayfa_sayisi == 500


def test_kitap_sayfa_sayisi_negatif_hata():
    # Neden: Hatalı verinin sisteme sızmasını engelleyen "Hızlı Hata
    # (Fail-Fast)" mekanizmasını test ediyoruz.
    with pytest.raises(GecersizParametreError):
        Kitap("111", "Dune", "F. Herbert", "Kurgu", -10)


def test_kitap_factory_metodu_basarili():
    # Neden: Dışarıdan (API) gelen karmaşık verinin, iç sistemin
    # anlayacağı formata (Parsing) hatasız dönüştüğünü kanıtlıyoruz.
    api_verisi = {"title": "1984", "authors": [
        {"name": "Orwell"}], "number_of_pages": 328}
    kitap = Kitap.api_verisinden_olustur("222", api_verisi)
    assert kitap.yazar == "Orwell"
    assert kitap.sayfa_sayisi == 328


def test_okuma_kaydi_gecerli_durum():
    # Neden: Doğru verilerin yanlışlıkla reddedilmediğinden emin oluyoruz
    # (False-Positive engeli).
    kayit = OkumaKaydi(1, "111", "okunuyor")
    assert kayit.durum == "okunuyor"


def test_okuma_kaydi_gecersiz_durum_hata():
    # Neden: Veritabanı kısıtlamalarına gitmeden önce, iş kurallarının
    # Python katmanında veriyi engellediğini doğruluyoruz.
    with pytest.raises(GecersizParametreError):
        OkumaKaydi(1, "111", "baslamadim")


def test_not_sayfa_negatif_hata():
    # Neden: Veri doğrulama mantığının projenin her modelinde tutarlı
    # uygulandığını görüyoruz.
    with pytest.raises(GecersizParametreError):
        Not(okuma_listesi_id=1, not_metni="Harika", sayfa=-5)
