"""
LibroTrack Veri Modelleri (Domain Entities).

Bu modül uygulamanın temel iş nesnelerini tanımlar. Sınıflar kapsülleme
(encapsulation) ve veri doğrulama içerir; doğrulama kuralları tek yerde
durur ve hem CLI hem iş katmanı tarafından yeniden kullanılır.
"""

from datetime import date
from typing import Any

from src.exceptions import GecersizParametreError

# Neden: Geçerli durumlar CLI, model ve veritabanında ayrı ayrı yazılmasın
# diye tek bir sabitte tutulur.
DURUMLAR: tuple[str, ...] = ("okunacak", "okunuyor", "okundu")


class Kullanici:
    """Sistemi kullanan bir profili temsil eder."""

    def __init__(self, kullanici_adi: str, id: int | None = None) -> None:
        """Kullanıcı nesnesi oluşturur.

        Args:
            kullanici_adi: Boş olmayan kullanıcı adı (baştaki/sondaki
                boşluklar temizlenir).
            id: Veritabanı kimliği; henüz kaydedilmediyse ``None``.

        Raises:
            GecersizParametreError: Kullanıcı adı boşsa.
        """
        if not isinstance(kullanici_adi, str) or not kullanici_adi.strip():
            raise GecersizParametreError("Kullanıcı adı boş olamaz.")
        self.id = id
        # Neden: Kullanıcı adı sonradan geçersiz bir değerle
        # değiştirilemesin diye doğrudan erişim kapatılır.
        self._kullanici_adi = kullanici_adi.strip()

    @property
    def kullanici_adi(self) -> str:
        """Kullanıcı adını döndürür (salt okunur)."""
        return self._kullanici_adi

    def __str__(self) -> str:
        """Kullanıcıyı okunaklı metin olarak döndürür."""
        return f"Kullanıcı: {self.kullanici_adi}"


class Kitap:
    """Kütüphanedeki fiziksel veya dijital bir kitabı temsil eder."""

    def __init__(self, isbn: str, baslik: str, yazar: str,
                 tur: str | None = None,
                 sayfa_sayisi: int | None = None,
                 aciklama: str | None = None,
                 kapak_url: str | None = None) -> None:
        """Kitap nesnesi oluşturur.

        Args:
            isbn: Kitabın benzersiz kimliği (sonradan değiştirilemez).
            baslik: Kitabın adı.
            yazar: Kitabın yazarı.
            tur: Kitabın türü (opsiyonel).
            sayfa_sayisi: Sayfa sayısı; verilirse pozitif tam sayı olmalı.
            aciklama: Kitabın tanıtım metni (Open Library'den gelir).
            kapak_url: Kitap kapağı görselinin adresi (Open Library).

        Raises:
            GecersizParametreError: Sayfa sayısı geçersizse.
        """
        # Neden: ISBN değiştirilemez olmalı ki veritabanı ilişkileri
        # (Foreign Key) bozulmasın.
        self._isbn = isbn
        self.baslik = baslik
        self.yazar = yazar
        self.tur = tur
        self.aciklama = aciklama
        self.kapak_url = kapak_url
        # Neden: Atamayı setter üzerinden yaparak kural denetimini
        # nesne oluşurken de çalıştırıyoruz (Fail-Fast).
        self.sayfa_sayisi = sayfa_sayisi

    @property
    def isbn(self) -> str:
        """Kitabın ISBN numarasını döndürür (salt okunur)."""
        return self._isbn

    @property
    def sayfa_sayisi(self) -> int | None:
        """Kitabın sayfa sayısını döndürür; bilinmiyorsa ``None``."""
        return self._sayfa_sayisi

    @sayfa_sayisi.setter
    def sayfa_sayisi(self, deger: int | None) -> None:
        """Sayfa sayısını doğrulayarak atar."""
        self._sayfa_sayisi = self.sayfa_sayisi_dogrula(deger)

    @staticmethod
    def sayfa_sayisi_dogrula(deger: int | None) -> int | None:
        """Sayfa sayısının geçerli olup olmadığını denetler.

        Args:
            deger: Denetlenecek sayfa sayısı.

        Returns:
            Geçerliyse aynı değer (``None`` da geçerlidir).

        Raises:
            GecersizParametreError: Değer pozitif tam sayı değilse.
        """
        if deger is None:
            return None
        if (not isinstance(deger, int) or isinstance(deger, bool)
                or deger <= 0):
            raise GecersizParametreError(
                "Sayfa sayısı 0'dan büyük bir tam sayı olmalıdır."
            )
        return deger

    @classmethod
    def api_verisinden_olustur(cls, isbn: str,
                               api_verisi: dict[str, Any]) -> "Kitap":
        """Open Library API verisinden Kitap nesnesi üretir (Factory).

        Dış servis her zaman kusursuz veri göndermeyebileceği için eksik
        veya bozuk alanlar (boş yazar listesi, ``0`` sayfa vb.) hataya
        yol açmak yerine varsayılan değerlere düşürülür.

        Args:
            isbn: Kitabın ISBN numarası.
            api_verisi: API'nin döndürdüğü ham sözlük.

        Returns:
            Doğrulanmış Kitap nesnesi.
        """
        baslik = api_verisi.get("title") or "Bilinmeyen Başlık"
        yazar = "Bilinmeyen Yazar"

        yazarlar = api_verisi.get("authors")
        if isinstance(yazarlar, list) and yazarlar \
                and isinstance(yazarlar[0], dict):
            yazar = yazarlar[0].get("name") or yazar

        sayfa = api_verisi.get("number_of_pages")
        try:
            sayfa = cls.sayfa_sayisi_dogrula(sayfa)
        except GecersizParametreError:
            sayfa = None  # Bozuk API verisi kitabın eklenmesini engellemez.

        return cls(isbn=isbn, baslik=baslik, yazar=yazar, tur="Genel",
                   sayfa_sayisi=sayfa,
                   kapak_url=cls._kapak_adresi(api_verisi.get("cover")))

    @staticmethod
    def _kapak_adresi(kapaklar: Any) -> str | None:
        """API'nin ``cover`` alanından en uygun kapak adresini seçer.

        Open Library ``small``, ``medium`` ve ``large`` boyutlarında adres
        verir. Liste/detay gösterimi için orta boyut yeterli olduğundan
        önce o, yoksa sırayla büyük ve küçük boyut seçilir.

        Returns:
            Bulunan ilk geçerli adres; yoksa ``None``.
        """
        if not isinstance(kapaklar, dict):
            return None
        for boyut in ("medium", "large", "small"):
            adres = kapaklar.get(boyut)
            if isinstance(adres, str) and adres.startswith("https://"):
                return adres
        return None


class OkumaKaydi:
    """Kullanıcının bir kitapla ilişkisini ve okuma durumunu tutar."""

    KABUL_EDILEN_DURUMLAR = frozenset(DURUMLAR)

    def __init__(self, kullanici_id: int, isbn: str, durum: str,
                 id: int | None = None,
                 bitis_tarihi: str | None = None) -> None:
        """Okuma kaydı oluşturur.

        Args:
            kullanici_id: Kaydın sahibi kullanıcı.
            isbn: İlgili kitabın ISBN numarası.
            durum: ``okunacak``, ``okunuyor`` veya ``okundu``.
            id: Veritabanı kimliği (opsiyonel).
            bitis_tarihi: ISO biçiminde (YYYY-MM-DD) bitiş tarihi.

        Raises:
            GecersizParametreError: Durum geçersizse.
        """
        self.id = id
        self.kullanici_id = kullanici_id
        self.isbn = isbn
        # Neden: SQLite'ın yerleşik tarih tipi olmadığı için tarihi
        # ISO biçiminde metin olarak saklıyoruz.
        self.bitis_tarihi = bitis_tarihi
        self.durum = durum

    @property
    def durum(self) -> str:
        """Okuma durumunu döndürür."""
        return self._durum

    @durum.setter
    def durum(self, yeni_durum: str) -> None:
        """Durumu doğrulayarak atar."""
        self._durum = self.durum_dogrula(yeni_durum)

    @staticmethod
    def durum_dogrula(durum: str) -> str:
        """Durumu küçük harfe çevirir ve geçerliliğini denetler.

        Args:
            durum: Denetlenecek durum metni.

        Returns:
            Normalize edilmiş (küçük harfli) durum.

        Raises:
            GecersizParametreError: Durum izin verilenlerden değilse.
        """
        normal = durum.lower() if isinstance(durum, str) else None
        if normal not in DURUMLAR:
            raise GecersizParametreError(
                "Geçersiz durum. Şunlardan biri olmalı: "
                f"{', '.join(DURUMLAR)}"
            )
        return normal

    @staticmethod
    def bitis_tarihi_belirle(durum: str,
                             bitis_tarihi: str | None = None) -> str | None:
        """Duruma göre kaydedilecek bitiş tarihini belirler.

        * ``okundu`` ve tarih verilmediyse: bugün.
        * ``okundu`` ve tarih verildiyse: o tarih (geçmişe dönük kayıt).
        * Diğer durumlar: tarih ``None``; tarih verilmesi hatadır.

        Args:
            durum: Normalize edilmiş okuma durumu.
            bitis_tarihi: ISO biçiminde (YYYY-AA-GG) isteğe bağlı tarih.

        Returns:
            ISO biçiminde tarih veya ``None``.

        Raises:
            GecersizParametreError: Tarih biçimi bozuksa, gelecekteyse
                veya 'okundu' dışındaki bir durumla verilmişse.
        """
        if bitis_tarihi is None:
            return date.today().isoformat() if durum == "okundu" else None
        if durum != "okundu":
            raise GecersizParametreError(
                "Bitiş tarihi yalnızca 'okundu' durumunda verilebilir."
            )
        try:
            tarih = date.fromisoformat(bitis_tarihi)
        except (TypeError, ValueError):
            raise GecersizParametreError(
                "Bitiş tarihi YYYY-AA-GG biçiminde olmalıdır."
            ) from None
        if tarih > date.today():
            raise GecersizParametreError("Bitiş tarihi gelecekte olamaz.")
        return tarih.isoformat()


class Not:
    """Bir okuma kaydına ait kullanıcı notunu temsil eder."""

    def __init__(self, okuma_listesi_id: int, not_metni: str,
                 sayfa: int | None = None, id: int | None = None) -> None:
        """Not nesnesi oluşturur.

        Args:
            okuma_listesi_id: Notun bağlı olduğu okuma kaydı.
            not_metni: Boş olmayan not içeriği.
            sayfa: İlgili sayfa; verilirse negatif olamaz.
            id: Veritabanı kimliği (opsiyonel).

        Raises:
            GecersizParametreError: Metin boşsa veya sayfa negatifse.
        """
        if not isinstance(not_metni, str) or not not_metni.strip():
            raise GecersizParametreError("Not metni boş olamaz.")
        self.id = id
        # Neden: Notu kitaba değil kullanıcının okuma kaydına bağlıyoruz;
        # böylece farklı kullanıcılar aynı kitaba kendi notlarını alır.
        self.okuma_listesi_id = okuma_listesi_id
        self.not_metni = not_metni.strip()
        self.sayfa = sayfa

    @property
    def sayfa(self) -> int | None:
        """Notun ait olduğu sayfa numarasını döndürür."""
        return self._sayfa

    @sayfa.setter
    def sayfa(self, deger: int | None) -> None:
        """Sayfa numarasını doğrulayarak atar (negatif olamaz)."""
        if deger is not None and (not isinstance(deger, int)
                                  or isinstance(deger, bool) or deger < 0):
            raise GecersizParametreError("Sayfa numarası negatif olamaz.")
        self._sayfa = deger
