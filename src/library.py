"""
LibroTrack İş Mantığı Katmanı (Business Logic Layer).

CLI ile veritabanı arasındaki köprüdür: iş kurallarını uygular, girdileri
model sınıflarıyla doğrular ve veri erişimini ``DBManager``'e bırakır.
Dış servis (Open Library) ile konuşma sorumluluğu aynı dosyadaki ayrı bir
sınıfa (``OpenLibraryIstemcisi``) verilmiştir; böylece testlerde sahte bir
istemci kullanılabilir.
"""

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests

from src.config import (API_ZAMAN_ASIMI_SANIYE, CSV_DOSYA_ADI,
                        KAPAK_BOYUT_SINIRI_BAYT, KAPAK_KLASORU,
                        OPEN_LIBRARY_TEMEL_URL, VARSAYILAN_KULLANICI, logger)
from src.db_manager import DBManager
from src.exceptions import (APIHatasi, DisaAktarimHatasi,
                            GecersizParametreError, KayitCakismasiError,
                            KitapBulunamadiError, KitapZatenVarError,
                            KullaniciBulunamadiError, KullaniciZatenVarError,
                            VeritabaniHatasi)
from src.models import Kitap, Kullanici, Not, OkumaKaydi

Kayit = dict[str, Any]
CSV_BASLIKLARI = ("ISBN", "Başlık", "Yazar", "Bitiş Tarihi")

# Neden: Kullanıcıya özel değişiklikler (ozel_*) ortak katalogdaki değeri
# EZMEDEN, yalnızca o kullanıcının görünümünde geçerli olur. COALESCE önce
# kullanıcıya özel değeri, yoksa katalogdakini seçer.
_TUR_SQL = "COALESCE(o.ozel_tur, k.tur)"
_SAYFA_SQL = "COALESCE(o.ozel_sayfa_sayisi, k.sayfa_sayisi)"

# Open Library "work" anahtarı biçimi (ör. /works/OL45804W). URL'ye
# yerleştirmeden önce doğrulanır.
_ESER_ANAHTARI = re.compile(r"^/works/OL\d+W$")

# Neden: SQLite'ın LIKE operatörü büyük/küçük harf farkını yalnızca ASCII
# karakterlerde yok sayar ("ş" ile "Ş" farklı sayılır) ve Türkçe 'İ/ı'
# kurallarını bilmez. Bu yüzden arama metinleri Python tarafında Türkçe
# kurallarıyla normalize edilir.
_TR_BUYUK_HARF = str.maketrans({"İ": "i", "I": "ı"})
_TR_SADELESTIR = str.maketrans("ıçğöşüâîû", "icgosuaiu")


def arama_icin_normallestir(metin: str) -> str:
    """Metni büyük/küçük harf ve Türkçe aksan farkından bağımsız hale getirir.

    'İ'→'i', 'I'→'ı' dönüşümü ``lower()``'dan ÖNCE yapılır (Python'un
    varsayılan davranışı 'İ'yi iki karaktere ayırır). Ardından ç, ğ, ı, ö,
    ş, ü gibi harfler ASCII karşılıklarına indirgenir; böylece "siir"
    araması "Şiir" ve "ŞİİR"i, "isik" araması "Işık"ı bulur.

    Args:
        metin: Normalize edilecek metin.

    Returns:
        Karşılaştırmaya hazır küçük harfli, sadeleştirilmiş metin.
    """
    return metin.translate(_TR_BUYUK_HARF).lower().translate(_TR_SADELESTIR)


def _listede_yok(isbn: str) -> KitapBulunamadiError:
    """Listede olmayan kitap için standart hata nesnesini üretir."""
    return KitapBulunamadiError(
        f"'{isbn}' ISBN'li kitap kitaplığınızda bulunamadı."
    )


def _metin_ayikla(deger: Any) -> str | None:
    """Open Library'nin metin alanlarını düz metne çevirir.

    API aynı alanı bazen düz metin, bazen ``{"value": "..."}`` sözlüğü
    olarak döndürür.

    Returns:
        Boş olmayan metin; aksi halde ``None``.
    """
    if isinstance(deger, dict):
        deger = deger.get("value")
    if isinstance(deger, str) and deger.strip():
        return deger.strip()
    return None


class OpenLibraryIstemcisi:
    """ISBN ile Open Library'den kitap, kapak ve açıklama bilgisi çeker."""

    def __init__(self, temel_url: str = OPEN_LIBRARY_TEMEL_URL,
                 zaman_asimi: int = API_ZAMAN_ASIMI_SANIYE) -> None:
        """İstemciyi oluşturur.

        Args:
            temel_url: Open Library ana adresi.
            zaman_asimi: Her istek için zaman aşımı (saniye).
        """
        self.temel_url = temel_url.rstrip("/")
        self.zaman_asimi = zaman_asimi

    def _json_getir(self, url: str, params: dict[str, str] | None = None,
                    onemli: bool = True) -> Any | None:
        """Bir adresten JSON okur; hata olursa istisna yerine ``None`` verir.

        Args:
            url: İstek adresi.
            params: Sorgu parametreleri (URL'ye güvenle kodlanır).
            onemli: ``False`` ise hata yalnızca INFO olarak loglanır
                (açıklama gibi isteğe bağlı veriler için).
        """
        try:
            yanit = requests.get(url, params=params,
                                 timeout=self.zaman_asimi)
            yanit.raise_for_status()
            return yanit.json()
        except (requests.RequestException, ValueError) as hata:
            seviye = logger.warning if onemli else logger.info
            seviye("API isteği başarısız (%s): %s", url, hata)
            return None

    def kitap_getir(self, isbn: str) -> Kitap | None:
        """ISBN'e ait kitabı başlık, yazar, sayfa, kapak ve açıklamayla çeker.

        Temel bilgiler ``/api/books`` (jscmd=data) uç noktasından gelir.
        Bu uç nokta açıklama döndürmediği için açıklama ayrıca edition ve
        gerekirse work kaydından alınır. Açıklama alınamazsa kitap yine de
        döner. Ağ hataları istisna fırlatmaz; ``None`` döner ve loglanır.

        Args:
            isbn: Aranacak ISBN.

        Returns:
            Bulunursa Kitap nesnesi, aksi halde ``None``.
        """
        anahtar = f"ISBN:{isbn}"
        # Neden: Parametreleri URL'ye elle gömmek yerine ``params`` ile
        # veriyoruz; ISBN içindeki '&' gibi karakterler sorguyu bozmaz.
        veri = self._json_getir(
            f"{self.temel_url}/api/books",
            {"bibkeys": anahtar, "format": "json", "jscmd": "data"},
        )
        ham_kitap = veri.get(anahtar) if isinstance(veri, dict) else None
        if not ham_kitap:
            logger.info("Open Library'de kitap bulunamadı: %s", isbn)
            return None

        kitap = Kitap.api_verisinden_olustur(isbn, ham_kitap)
        kitap.aciklama = self._aciklama_getir(isbn)
        return kitap

    def _aciklama_getir(self, isbn: str) -> str | None:
        """Kitabın açıklamasını edition, yoksa work kaydından bulur.

        Returns:
            Açıklama metni; bulunamazsa veya hata olursa ``None``.
        """
        baski = self._json_getir(
            f"{self.temel_url}/isbn/{quote(isbn, safe='')}.json",
            onemli=False,
        )
        if not isinstance(baski, dict):
            return None

        aciklama = _metin_ayikla(baski.get("description"))
        if aciklama:
            return aciklama

        eserler = baski.get("works")
        if not (isinstance(eserler, list) and eserler
                and isinstance(eserler[0], dict)):
            return None
        eser_anahtari = eserler[0].get("key")
        if not (isinstance(eser_anahtari, str)
                and _ESER_ANAHTARI.match(eser_anahtari)):
            return None
        eser = self._json_getir(f"{self.temel_url}{eser_anahtari}.json",
                                onemli=False)
        return _metin_ayikla(eser.get("description")) \
            if isinstance(eser, dict) else None

    def kapak_indir(self, kapak_url: str, hedef: Path) -> Path:
        """Kapak görselini indirip dosyaya kaydeder.

        Güvenlik: Yalnızca ``openlibrary.org`` alan adlarından HTTPS ile
        indirilir, yanıtın görsel olduğu ve boyut sınırını aşmadığı
        doğrulanır.

        Args:
            kapak_url: Kapak görselinin adresi.
            hedef: Kaydedilecek dosya yolu.

        Returns:
            Kaydedilen dosyanın yolu.

        Raises:
            APIHatasi: Adres güvenilmezse, indirme başarısızsa veya yanıt
                geçerli bir görsel değilse.
            DisaAktarimHatasi: Dosya yazılamazsa.
        """
        ayrik = urlparse(kapak_url)
        alan = ayrik.hostname or ""
        if ayrik.scheme != "https" or not (
                alan == "openlibrary.org"
                or alan.endswith(".openlibrary.org")):
            raise APIHatasi("Güvenilmeyen kapak adresi reddedildi.")

        try:
            yanit = requests.get(kapak_url, timeout=self.zaman_asimi)
            yanit.raise_for_status()
        except requests.RequestException as hata:
            raise APIHatasi(f"Kapak indirilemedi: {hata}") from hata

        if not yanit.headers.get("Content-Type", "").startswith("image/"):
            raise APIHatasi("Kapak adresi bir görsel döndürmedi.")
        if len(yanit.content) > KAPAK_BOYUT_SINIRI_BAYT:
            raise APIHatasi("Kapak görseli izin verilen boyutu aşıyor.")

        try:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(yanit.content)
        except OSError as hata:
            raise DisaAktarimHatasi(
                f"Kapak dosyası yazılamadı ('{hedef}'): {hata}"
            ) from hata
        logger.info("Kapak indirildi: %s", hedef)
        return hedef


class Kutuphane:
    """Kullanıcı kitaplığı için iş kurallarını yöneten servis sınıfı."""

    def __init__(self, db: DBManager | None = None,
                 api_istemcisi: OpenLibraryIstemcisi | None = None) -> None:
        """Servisi oluşturur ve veritabanı şemasını hazırlar.

        Bağımlılıklar dışarıdan verilebilir (Dependency Injection); bu
        sayede testlerde geçici veritabanı ve sahte API istemcisi
        kullanılır.

        Args:
            db: Veri erişim nesnesi; verilmezse varsayılan oluşturulur.
            api_istemcisi: Open Library istemcisi; verilmezse varsayılan.

        Raises:
            VeritabaniHatasi: Veritabanı açılamazsa.
        """
        self.db = db if db is not None else DBManager()
        self.api = (api_istemcisi if api_istemcisi is not None
                    else OpenLibraryIstemcisi())
        self.db.setup_database()

    # ------------------------------------------------------------------
    # Kullanıcı profilleri (çoklu kullanıcı)
    # ------------------------------------------------------------------
    def _kullanici_id_bul(self, kullanici_adi: str) -> int | None:
        """Kullanıcı adına karşılık gelen kimliği döndürür."""
        satir = self.db.fetch_one(
            "SELECT id FROM kullanicilar WHERE kullanici_adi = ?",
            (kullanici_adi,),
        )
        return satir["id"] if satir else None

    def kullanici_ekle(self, kullanici_adi: str) -> int:
        """Yeni bir kullanıcı profili oluşturur.

        Returns:
            Yeni kullanıcının veritabanı kimliği.

        Raises:
            GecersizParametreError: Kullanıcı adı boşsa.
            KullaniciZatenVarError: Aynı adlı profil varsa.
        """
        ad = Kullanici(kullanici_adi).kullanici_adi
        try:
            yeni_id = self.db.execute(
                "INSERT INTO kullanicilar (kullanici_adi) VALUES (?)",
                (ad,),
            )
        except KayitCakismasiError as hata:
            raise KullaniciZatenVarError(
                f"'{ad}' kullanıcısı zaten mevcut."
            ) from hata
        logger.info("Yeni kullanıcı oluşturuldu: %s", ad)
        return yeni_id

    def kullanici_bul(self, kullanici_adi: str) -> int:
        """Var olan bir kullanıcının kimliğini verir.

        Raises:
            KullaniciBulunamadiError: Profil kayıtlı değilse.
        """
        ad = Kullanici(kullanici_adi).kullanici_adi
        kullanici_id = self._kullanici_id_bul(ad)
        if kullanici_id is None:
            raise KullaniciBulunamadiError(
                f"'{ad}' kullanıcısı bulunamadı. Önce oluşturun: "
                f"python libro.py kullanici-ekle --ad {ad}"
            )
        return kullanici_id

    def kullanici_getir_veya_olustur(self, kullanici_adi: str) -> int:
        """Kullanıcıyı bulur, yoksa sessizce oluşturur.

        Returns:
            Kullanıcının veritabanı kimliği.

        Raises:
            GecersizParametreError: Kullanıcı adı boşsa.
        """
        ad = Kullanici(kullanici_adi).kullanici_adi
        mevcut_id = self._kullanici_id_bul(ad)
        if mevcut_id is not None:
            return mevcut_id

        # OR IGNORE: iki işlem aynı anda açarsa oluşacak UNIQUE
        # çakışmasını zararsız hale getirir.
        self.db.execute(
            "INSERT OR IGNORE INTO kullanicilar (kullanici_adi) VALUES (?)",
            (ad,),
        )
        yeni_id = self._kullanici_id_bul(ad)
        if yeni_id is None:
            raise VeritabaniHatasi("Kullanıcı oluşturulamadı.")
        logger.info("Yeni kullanıcı oluşturuldu: %s", ad)
        return yeni_id

    def aktif_kullanici(self, kullanici_adi: str) -> int:
        """CLI'daki ``-u`` değerini kullanıcı kimliğine çevirir.

        Neden: Varsayılan kullanıcı, tek kullanıcılı kullanımı kolaylaştırmak
        için otomatik oluşturulur. Diğer adlar ise açıkça
        ``kullanici-ekle`` ile oluşturulmalıdır; böylece yazım hatası
        ("ayse" yerine "aise") sessizce yeni profil açmaz.

        Raises:
            KullaniciBulunamadiError: Varsayılan dışı profil kayıtlı değilse.
        """
        ad = Kullanici(kullanici_adi).kullanici_adi
        if ad == VARSAYILAN_KULLANICI:
            return self.kullanici_getir_veya_olustur(ad)
        return self.kullanici_bul(ad)

    def kullanicilari_listele(self) -> list[Kayit]:
        """Tüm profilleri ve her birinin kitap sayısını verir."""
        return self.db.fetch_all("""
            SELECT u.id, u.kullanici_adi, COUNT(o.id) AS kitap_sayisi
            FROM kullanicilar u
            LEFT JOIN okuma_listesi o ON o.kullanici_id = u.id
            GROUP BY u.id
            ORDER BY u.kullanici_adi COLLATE NOCASE
        """)

    def kullanici_sil(self, kullanici_adi: str) -> None:
        """Kullanıcı profilini; kitaplığı ve notlarıyla birlikte siler.

        Bağlı kayıtlar ``ON DELETE CASCADE`` ile silinir. Ortak katalogdaki
        kitaplar diğer kullanıcılar için korunur.

        Raises:
            KullaniciBulunamadiError: Profil kayıtlı değilse.
        """
        ad = Kullanici(kullanici_adi).kullanici_adi
        silinen = self.db.execute(
            "DELETE FROM kullanicilar WHERE kullanici_adi = ?", (ad,)
        )
        if silinen == 0:
            raise KullaniciBulunamadiError(f"'{ad}' kullanıcısı bulunamadı.")
        logger.info("Kullanıcı silindi: %s", ad)

    # ------------------------------------------------------------------
    # Kitap işlemleri
    # ------------------------------------------------------------------
    def api_kitap_sorgula(self, isbn: str) -> Kitap | None:
        """ISBN'i Open Library'de arar (ayrıntılar API istemcisindedir)."""
        return self.api.kitap_getir(isbn)

    def kitap_ekle(self, kullanici_id: int, kitap: Kitap,
                   durum: str = "okunacak",
                   bitis_tarihi: str | None = None) -> None:
        """Kitabı ortak kataloğa ve kullanıcının okuma listesine ekler.

        Her iki ekleme tek transaction'da yapılır; biri başarısız olursa
        hiçbiri uygulanmaz. Kitap katalogda zaten varsa mevcut bilgiler
        korunur, yalnızca eksik olan açıklama ve kapak adresi doldurulur.

        Args:
            kullanici_id: Kitabı ekleyen kullanıcı.
            kitap: Eklenecek kitap.
            durum: Başlangıç okuma durumu.
            bitis_tarihi: 'okundu' için geçmişe dönük bitiş tarihi
                (YYYY-AA-GG); verilmezse bugün kullanılır.

        Raises:
            GecersizParametreError: Durum veya tarih geçersizse.
            KitapZatenVarError: Kitap kullanıcının listesinde zaten varsa.
            VeritabaniHatasi: Beklenmeyen veritabanı hatalarında.
        """
        durum = OkumaKaydi.durum_dogrula(durum)
        bitis = OkumaKaydi.bitis_tarihi_belirle(durum, bitis_tarihi)
        try:
            self.db.execute_transaction([
                # Neden: UPSERT. Kitap katalogda yoksa eklenir; varsa
                # mevcut kayıt EZİLMEZ, yalnızca boş olan açıklama/kapak
                # alanları doldurulur.
                ("INSERT INTO kitaplar (isbn, baslik, yazar, tur, "
                 "sayfa_sayisi, aciklama, kapak_url) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?) "
                 "ON CONFLICT(isbn) DO UPDATE SET "
                 "aciklama = COALESCE(kitaplar.aciklama, "
                 "excluded.aciklama), "
                 "kapak_url = COALESCE(kitaplar.kapak_url, "
                 "excluded.kapak_url)",
                 (kitap.isbn, kitap.baslik, kitap.yazar, kitap.tur,
                  kitap.sayfa_sayisi, kitap.aciklama, kitap.kapak_url)),
                ("INSERT INTO okuma_listesi "
                 "(kullanici_id, isbn, durum, bitis_tarihi) "
                 "VALUES (?, ?, ?, ?)",
                 (kullanici_id, kitap.isbn, durum, bitis)),
            ])
        except KayitCakismasiError as hata:
            logger.info("Kitap zaten listede (kullanıcı %s): %s",
                        kullanici_id, kitap.isbn)
            raise KitapZatenVarError(
                f"'{kitap.baslik}' zaten kitaplığınızda ekli."
            ) from hata
        logger.info("Kitap eklendi (kullanıcı %s, ISBN %s, durum %s)",
                    kullanici_id, kitap.isbn, durum)

    def kitap_sil(self, kullanici_id: int, isbn: str) -> None:
        """Kitabı kullanıcının listesinden siler.

        Bağlı notlar ``ON DELETE CASCADE`` ile birlikte silinir. Ortak
        katalogdaki kayıt, kitabı kullanan diğer kullanıcılar etkilenmesin
        diye korunur.

        Raises:
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
        """
        silinen = self.db.execute(
            "DELETE FROM okuma_listesi WHERE kullanici_id = ? AND isbn = ?",
            (kullanici_id, isbn),
        )
        if silinen == 0:
            raise _listede_yok(isbn)
        logger.info("Kitap silindi (kullanıcı %s, ISBN %s)",
                    kullanici_id, isbn)

    def kitap_guncelle(self, kullanici_id: int, isbn: str,
                       tur: str | None = None,
                       sayfa_sayisi: int | None = None) -> None:
        """Tür ve/veya sayfa sayısını YALNIZCA bu kullanıcı için günceller.

        Değişiklik ortak katalogu değil, kullanıcının kendi okuma kaydını
        etkiler (``ozel_tur``, ``ozel_sayfa_sayisi``); aynı kitabı ekleyen
        diğer kullanıcılar kendi değerlerini görmeye devam eder.

        Raises:
            GecersizParametreError: Hiçbir alan verilmemişse veya değerler
                geçersizse.
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
        """
        if tur is None and sayfa_sayisi is None:
            raise GecersizParametreError(
                "Güncellenecek bir bilgi girmediniz "
                "(--tur veya --sayfa-sayisi)."
            )

        alanlar: list[str] = []
        parametreler: list[Any] = []
        if tur is not None:
            if not tur.strip():
                raise GecersizParametreError("Tür boş olamaz.")
            alanlar.append("ozel_tur = ?")
            parametreler.append(tur.strip())
        if sayfa_sayisi is not None:
            Kitap.sayfa_sayisi_dogrula(sayfa_sayisi)
            alanlar.append("ozel_sayfa_sayisi = ?")
            parametreler.append(sayfa_sayisi)

        # Neden: Dinamik UPDATE'te yalnızca sabit sütun parçaları
        # birleştirilir; kullanıcı girdisi her zaman '?' parametresiyle
        # geçer, dolayısıyla SQL injection riski yoktur.
        sorgu = (f"UPDATE okuma_listesi SET {', '.join(alanlar)} "
                 "WHERE kullanici_id = ? AND isbn = ?")
        parametreler += [kullanici_id, isbn]
        if self.db.execute(sorgu, tuple(parametreler)) == 0:
            raise _listede_yok(isbn)
        logger.info("Kitap güncellendi (kullanıcı %s, ISBN %s): %s",
                    kullanici_id, isbn,
                    ", ".join(a.split(" =")[0] for a in alanlar))

    def kitaplari_listele(self, kullanici_id: int,
                          durum: str | None = None,
                          tur: str | None = None) -> list[Kayit]:
        """Kullanıcının kitaplarını (isteğe bağlı filtrelerle) verir.

        Args:
            kullanici_id: Kullanıcı kimliği.
            durum: Verilirse yalnızca bu okuma durumundaki kitaplar.
            tur: Verilirse yalnızca bu türdeki kitaplar (büyük/küçük harf
                ve Türkçe aksan farkından bağımsız).

        Raises:
            GecersizParametreError: Filtre durumu geçersizse.
        """
        sorgu = f"""
            SELECT k.isbn, k.baslik, k.yazar,
                   {_TUR_SQL} AS tur, {_SAYFA_SQL} AS sayfa_sayisi,
                   o.durum, o.bitis_tarihi
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ?
        """
        parametreler: list[Any] = [kullanici_id]
        if durum is not None:
            sorgu += " AND o.durum = ?"
            parametreler.append(OkumaKaydi.durum_dogrula(durum))
        sorgu += " ORDER BY k.baslik COLLATE NOCASE"
        kitaplar = self.db.fetch_all(sorgu, tuple(parametreler))
        if tur is None:
            return kitaplar
        # Neden: Tür kullanıcıya özel değer (COALESCE) olabildiği ve Türkçe
        # harf kuralları SQLite'ta çalışmadığı için filtre Python'da yapılır.
        hedef = arama_icin_normallestir(tur.strip())
        return [k for k in kitaplar
                if arama_icin_normallestir(k["tur"] or "") == hedef]

    def kitap_detay(self, kullanici_id: int, isbn: str) -> Kayit:
        """Bir kitabın açıklama ve kapak dahil tüm bilgilerini verir.

        Raises:
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
        """
        detay = self.db.fetch_one(f"""
            SELECT k.isbn, k.baslik, k.yazar,
                   {_TUR_SQL} AS tur, {_SAYFA_SQL} AS sayfa_sayisi,
                   k.aciklama, k.kapak_url, o.durum, o.bitis_tarihi
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ? AND o.isbn = ?
        """, (kullanici_id, isbn))
        if detay is None:
            raise _listede_yok(isbn)
        return detay

    def kapak_indir(self, kullanici_id: int, isbn: str,
                    klasor: str = KAPAK_KLASORU) -> str:
        """Kitabın kapağını Open Library'den indirip klasöre kaydeder.

        Returns:
            Kaydedilen dosyanın yolu.

        Raises:
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
            APIHatasi: Kitap için kayıtlı kapak yoksa veya indirme
                başarısız olursa.
        """
        detay = self.kitap_detay(kullanici_id, isbn)
        if not detay["kapak_url"]:
            raise APIHatasi(
                "Bu kitap için kayıtlı bir kapak adresi yok "
                "(Open Library'de kapak bulunamamış olabilir)."
            )
        # Neden: ISBN dosya adı olacağı için yol ayırıcı gibi tehlikeli
        # karakterler temizlenir.
        guvenli_ad = re.sub(r"[^0-9A-Za-z_-]", "_", isbn)
        hedef = Path(klasor) / f"{guvenli_ad}.jpg"
        return str(self.api.kapak_indir(detay["kapak_url"], hedef))

    def kitap_ara(self, kullanici_id: int,
                  anahtar_kelime: str) -> list[Kayit]:
        """Başlık veya yazarda anahtar kelimeyi arar (Türkçe uyumlu).

        Arama büyük/küçük harf ve Türkçe aksan farkından bağımsızdır:
        "ŞİİR", "şiir" ve "siir" aynı sonucu verir.

        Raises:
            GecersizParametreError: Anahtar kelime boşsa.
        """
        aranan = arama_icin_normallestir(anahtar_kelime.strip())
        if not aranan:
            raise GecersizParametreError("Arama kelimesi boş olamaz.")

        # Neden: Kişisel bir kitaplık küçük olduğundan kullanıcının kitapları
        # çekilip Python'da filtrelenir; böylece '%' ve '_' gibi karakterler
        # joker değil düz metin olarak aranır ve kaçış (escape) gerekmez.
        return [k for k in self.kitaplari_listele(kullanici_id)
                if aranan in arama_icin_normallestir(k["baslik"])
                or aranan in arama_icin_normallestir(k["yazar"])]

    def durum_guncelle(self, kullanici_id: int, isbn: str,
                       yeni_durum: str,
                       bitis_tarihi: str | None = None) -> None:
        """Okuma durumunu değiştirir; 'okundu' ise bitiş tarihini atar.

        Başka bir duruma geçilirse eski bitiş tarihi temizlenir.

        Args:
            kullanici_id: Kullanıcı kimliği.
            isbn: Kitabın ISBN numarası.
            yeni_durum: Yeni okuma durumu.
            bitis_tarihi: 'okundu' için geçmişe dönük tarih (YYYY-AA-GG);
                verilmezse bugün kullanılır.

        Raises:
            GecersizParametreError: Durum veya tarih geçersizse.
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
        """
        yeni_durum = OkumaKaydi.durum_dogrula(yeni_durum)
        bitis = OkumaKaydi.bitis_tarihi_belirle(yeni_durum, bitis_tarihi)
        guncellenen = self.db.execute(
            "UPDATE okuma_listesi SET durum = ?, bitis_tarihi = ? "
            "WHERE kullanici_id = ? AND isbn = ?",
            (yeni_durum, bitis, kullanici_id, isbn),
        )
        if guncellenen == 0:
            raise _listede_yok(isbn)
        logger.info("Durum güncellendi (kullanıcı %s, ISBN %s): %s",
                    kullanici_id, isbn, yeni_durum)

    # ------------------------------------------------------------------
    # Notlar
    # ------------------------------------------------------------------
    def not_ekle(self, kullanici_id: int, isbn: str, not_metni: str,
                 sayfa: int | None = None) -> int:
        """Kullanıcının kitabına (isteğe bağlı sayfa ile) not ekler.

        Returns:
            Yeni notun veritabanı kimliği.

        Raises:
            KitapBulunamadiError: Kitap kullanıcının listesinde yoksa.
            GecersizParametreError: Metin boşsa veya sayfa negatifse.
        """
        kayit = self.db.fetch_one(
            "SELECT id FROM okuma_listesi "
            "WHERE kullanici_id = ? AND isbn = ?",
            (kullanici_id, isbn),
        )
        if kayit is None:
            raise _listede_yok(isbn)

        # Neden: Doğrulama kurallarını tekrar yazmak yerine Not modelini
        # kullanıyoruz.
        yeni_not = Not(okuma_listesi_id=kayit["id"], not_metni=not_metni,
                       sayfa=sayfa)
        not_id = self.db.execute(
            "INSERT INTO notlar (okuma_listesi_id, not_metni, sayfa) "
            "VALUES (?, ?, ?)",
            (yeni_not.okuma_listesi_id, yeni_not.not_metni, yeni_not.sayfa),
        )
        logger.info("Not eklendi (kullanıcı %s, ISBN %s, not %s)",
                    kullanici_id, isbn, not_id)
        return not_id

    def notlari_listele(self, kullanici_id: int, isbn: str) -> list[Kayit]:
        """Bir kitaba ait notları sayfa sırasıyla listeler."""
        sorgu = """
            SELECT n.sayfa, n.not_metni
            FROM notlar n
            JOIN okuma_listesi o ON n.okuma_listesi_id = o.id
            WHERE o.kullanici_id = ? AND o.isbn = ?
            ORDER BY n.sayfa, n.id
        """
        return self.db.fetch_all(sorgu, (kullanici_id, isbn))

    # ------------------------------------------------------------------
    # İstatistik
    # ------------------------------------------------------------------
    def istatistik_getir(self, kullanici_id: int) -> dict[str, int]:
        """Durum başına kitap sayısını ve okunan toplam sayfayı verir.

        Returns:
            ``okunacak``, ``okunuyor``, ``okundu`` ve ``toplam_sayfa``
            anahtarlarını içeren sözlük.
        """
        # Neden: Toplama işini Python döngüsüne bırakmak yerine veritabanı
        # motoruna (COUNT/SUM + GROUP BY) yaptırıyoruz.
        sorgu = f"""
            SELECT o.durum, COUNT(*) AS sayi,
                   COALESCE(SUM({_SAYFA_SQL}), 0) AS toplam_sayfa
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ?
            GROUP BY o.durum
        """
        istatistikler = {"okunacak": 0, "okunuyor": 0, "okundu": 0,
                         "toplam_sayfa": 0}
        for satir in self.db.fetch_all(sorgu, (kullanici_id,)):
            istatistikler[satir["durum"]] = satir["sayi"]
            if satir["durum"] == "okundu":
                istatistikler["toplam_sayfa"] = satir["toplam_sayfa"]
        return istatistikler

    def tur_dagilimi_getir(self, kullanici_id: int) -> dict[str, int]:
        """Kullanıcının kitaplarını türlerine göre sayar.

        Returns:
            ``{tür: kitap sayısı}`` sözlüğü (çoktan aza sıralı). Türü
            olmayan kitaplar 'Belirtilmemiş' altında toplanır.
        """
        sorgu = f"""
            SELECT COALESCE({_TUR_SQL}, 'Belirtilmemiş') AS tur,
                   COUNT(*) AS sayi
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ?
            GROUP BY tur
            ORDER BY sayi DESC, tur
        """
        return {s["tur"]: s["sayi"]
                for s in self.db.fetch_all(sorgu, (kullanici_id,))}

    def aylik_okuma_getir(self, kullanici_id: int,
                          yil: int | None = None) -> list[Kayit]:
        """Bir yılın her ayı için bitirilen kitap ve sayfa sayısını verir.

        Okunmamış aylar da ``0`` ile listelenir; böylece sonuç doğrudan
        12 çubuklu bir grafiğe çevrilebilir.

        Args:
            kullanici_id: Kullanıcı kimliği.
            yil: İstatistiği alınacak yıl; verilmezse içinde bulunulan yıl.

        Returns:
            12 elemanlı liste; her eleman ``ay`` (1-12), ``kitap_sayisi``
            ve ``sayfa_sayisi`` anahtarlarını içerir.

        Raises:
            GecersizParametreError: Yıl 1900 ile bu yıl arasında değilse.
        """
        bugun = date.today()
        yil = bugun.year if yil is None else yil
        if not 1900 <= yil <= bugun.year:
            raise GecersizParametreError(
                f"Yıl 1900 ile {bugun.year} arasında olmalıdır."
            )

        sorgu = f"""
            SELECT CAST(strftime('%m', o.bitis_tarihi) AS INTEGER) AS ay,
                   COUNT(*) AS kitap_sayisi,
                   COALESCE(SUM({_SAYFA_SQL}), 0) AS sayfa_sayisi
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ? AND o.durum = 'okundu'
              AND o.bitis_tarihi IS NOT NULL
              AND strftime('%Y', o.bitis_tarihi) = ?
            GROUP BY ay
        """
        # Neden: SQLite yalnızca dolu ayları döndürür; boş ayları 0 ile
        # Python tarafında tamamlıyoruz.
        dolu = {s["ay"]: s for s in
                self.db.fetch_all(sorgu, (kullanici_id, f"{yil:04d}"))}
        return [{"ay": ay,
                 "kitap_sayisi": dolu.get(ay, {}).get("kitap_sayisi", 0),
                 "sayfa_sayisi": dolu.get(ay, {}).get("sayfa_sayisi", 0)}
                for ay in range(1, 13)]

    # ------------------------------------------------------------------
    # Dışa aktarım
    # ------------------------------------------------------------------
    def csv_disa_aktar(self, kullanici_id: int,
                       dosya_adi: str = CSV_DOSYA_ADI) -> int:
        """Okunmuş ('okundu') kitapları CSV dosyasına yazar.

        Neden ``utf-8-sig``: Dosyanın başına BOM eklenir; böylece Excel
        Türkçe karakterleri (ş, ğ, ı...) doğru okur.

        Args:
            kullanici_id: Kitapları dışa aktarılacak kullanıcı.
            dosya_adi: Yazılacak dosyanın yolu.

        Returns:
            Yazılan kitap sayısı.

        Raises:
            KitapBulunamadiError: Hiç 'okundu' kitap yoksa.
            DisaAktarimHatasi: Dosya yazılamazsa.
        """
        okunanlar = self.kitaplari_listele(kullanici_id, "okundu")
        if not okunanlar:
            raise KitapBulunamadiError(
                "Dışa aktarılacak 'okundu' durumunda kitap bulunamadı."
            )
        try:
            with open(dosya_adi, mode="w", newline="",
                      encoding="utf-8-sig") as dosya:
                yazici = csv.writer(dosya)
                yazici.writerow(CSV_BASLIKLARI)
                for kitap in okunanlar:
                    yazici.writerow([
                        kitap["isbn"],
                        kitap["baslik"],
                        kitap["yazar"],
                        # Neden: Anahtar var ama değer NULL olabilir; bu
                        # yüzden .get(anahtar, varsayılan) yetmez.
                        kitap["bitis_tarihi"] or "Bilinmiyor",
                    ])
        except OSError as hata:
            raise DisaAktarimHatasi(
                f"CSV dosyası yazılamadı ('{dosya_adi}'): {hata}"
            ) from hata

        logger.info("CSV dışa aktarım başarılı: %s (%d kitap)",
                    dosya_adi, len(okunanlar))
        return len(okunanlar)
