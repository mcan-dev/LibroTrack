"""CLI katmanının (libro.py) birim testleri.

Komutlar ``main(argv)`` üzerinden çağrılır; ``Kutuphane`` her testte geçici
bir veritabanına yönlendirildiği için gerçek veriye ve internete dokunulmaz.
"""

import pytest

import libro
from src.db_manager import DBManager
from src.library import Kutuphane


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """``libro.main`` için geçici veritabanlı bir çalıştırıcı verir."""
    db_yolu = str(tmp_path / "cli_test.db")

    class _SahteApi:
        # Neden: Testler internete çıkmamalı; API her zaman 'bulunamadı'
        # döndürür ve kitap elle girilen bilgilerle eklenir.
        def kitap_getir(self, isbn):
            return None

    monkeypatch.setattr(
        libro, "Kutuphane",
        lambda: Kutuphane(db=DBManager(db_yolu), api_istemcisi=_SahteApi()))
    return libro.main


def _ekle(cli, isbn, baslik, tur):
    return cli(["kitap-ekle", "--isbn", isbn, "--baslik", baslik,
                "--yazar", "Yazar", "--tur", tur, "--sayfa-sayisi", "100"])


def test_not_ekle_not_parametresiyle_calisir(cli, capsys):
    # Neden: Ödev metni notu '--not' ile veriyor; bu yazım çalışmalı.
    assert _ekle(cli, "1", "Dune", "Bilim Kurgu") == 0
    assert cli(["not-ekle", "--isbn", "1", "--not", "Harika", "--sayfa",
                "45"]) == 0
    assert cli(["not-listele", "--isbn", "1"]) == 0
    assert "Harika (Sayfa: 45)" in capsys.readouterr().out


def test_kitap_listele_tablo_ve_tur_filtresi(cli, capsys):
    # Neden: Liste tablo başlığı içermeli ve --tur yalnızca eşleşen kitabı
    # göstermelidir.
    _ekle(cli, "1", "Dune", "Bilim Kurgu")
    _ekle(cli, "2", "Suç ve Ceza", "Roman")
    capsys.readouterr()
    assert cli(["kitap-listele", "--tur", "roman"]) == 0
    cikti = capsys.readouterr().out
    assert "ISBN" in cikti and "Durum" in cikti
    assert "Suç ve Ceza" in cikti
    assert "Dune" not in cikti


def test_tekrar_eden_isbn_hata_kodu_doner(cli, capsys):
    # Neden: Aynı ISBN ikinci kez eklenemez; program çökmeden 1 koduyla
    # çıkmalı ve anlamlı mesaj vermelidir.
    assert _ekle(cli, "1", "Dune", "Bilim Kurgu") == 0
    assert _ekle(cli, "1", "Dune", "Bilim Kurgu") == 1
    assert "zaten" in capsys.readouterr().err


def test_istatistik_toplam_ve_tur_grafigi(cli, capsys, tmp_path,
                                          monkeypatch):
    # Neden: Özet toplam kitap sayısını göstermeli ve tür grafiğini .png
    # olarak kaydetmelidir.
    monkeypatch.chdir(tmp_path)
    _ekle(cli, "1", "Dune", "Bilim Kurgu")
    _ekle(cli, "2", "Suç ve Ceza", "Roman")
    capsys.readouterr()
    assert cli(["istatistik"]) == 0
    assert "Toplam kitap: 2" in capsys.readouterr().out
    assert (tmp_path / "okuma_grafigi.png").exists()
