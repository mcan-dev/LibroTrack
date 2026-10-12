"""
LibroTrack Veritabanı Yöneticisi (Data Access Layer).

SQLite ile uygulama arasındaki tek iletişim noktasıdır. İş mantığından
izoledir: SQL ve ``sqlite3`` bağımlılığı yalnızca bu modülde bulunur.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from src.config import DB_PATH, logger
from src.exceptions import KayitCakismasiError, VeritabaniHatasi

SCHEMA = """
CREATE TABLE IF NOT EXISTS kullanicilar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_adi TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS kitaplar (
    isbn TEXT PRIMARY KEY,
    baslik TEXT NOT NULL,
    yazar TEXT NOT NULL,
    tur TEXT,
    sayfa_sayisi INTEGER CHECK(sayfa_sayisi > 0),
    aciklama TEXT,
    kapak_url TEXT
);

CREATE TABLE IF NOT EXISTS okuma_listesi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_id INTEGER NOT NULL,
    isbn TEXT NOT NULL,
    durum TEXT NOT NULL
        CHECK(durum IN ('okunacak', 'okunuyor', 'okundu')),
    bitis_tarihi TEXT,
    ozel_tur TEXT,
    ozel_sayfa_sayisi INTEGER CHECK(ozel_sayfa_sayisi > 0),
    FOREIGN KEY (kullanici_id) REFERENCES kullanicilar(id)
        ON DELETE CASCADE,
    FOREIGN KEY (isbn) REFERENCES kitaplar(isbn) ON DELETE CASCADE,
    UNIQUE(kullanici_id, isbn)
);

CREATE TABLE IF NOT EXISTS notlar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    okuma_listesi_id INTEGER NOT NULL,
    sayfa INTEGER CHECK(sayfa >= 0),
    not_metni TEXT NOT NULL,
    FOREIGN KEY (okuma_listesi_id) REFERENCES okuma_listesi(id)
        ON DELETE CASCADE
);

-- Neden: SQLite yabancı anahtar sütunlarını otomatik indekslemez. Bu
-- indeks, not listelemeyi ve Cascade silmeyi tam tablo taramasından kurtarır.
CREATE INDEX IF NOT EXISTS idx_notlar_okuma_listesi
    ON notlar(okuma_listesi_id);

-- Neden: Aylık okuma istatistiği kullanıcı + durum + tarihe göre filtreler.
CREATE INDEX IF NOT EXISTS idx_okuma_bitis
    ON okuma_listesi(kullanici_id, durum, bitis_tarihi);
"""

# Neden: ``CREATE TABLE IF NOT EXISTS`` var olan bir tabloya yeni sütun
# eklemez. Eski sürümle oluşturulmuş veritabanları bozulmadan
# yükseltilsin diye eksik sütunlar ``ALTER TABLE`` ile eklenir.
# (tablo, sütun, tanım)
_EK_SUTUNLAR = (
    ("kitaplar", "aciklama", "TEXT"),
    ("kitaplar", "kapak_url", "TEXT"),
    ("okuma_listesi", "ozel_tur", "TEXT"),
    ("okuma_listesi", "ozel_sayfa_sayisi",
     "INTEGER CHECK(ozel_sayfa_sayisi > 0)"),
)

Satir = dict[str, Any]
Islem = tuple[str, tuple[Any, ...]]


class DBManager:
    """SQLite bağlantılarını ve temel okuma/yazma işlemlerini yönetir."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        """DBManager oluşturur.

        Args:
            db_path: Veritabanı dosya yolu. Testlerde geçici bir dosya
                verilerek gerçek veritabanına dokunulmaz.
        """
        self.db_path = db_path

    @contextmanager
    def _baglanti(self) -> Iterator[sqlite3.Connection]:
        """Bağlantıyı açar; başarıda commit, hatada rollback yapar.

        Neden: ``with sqlite3.connect(...)`` yalnızca commit/rollback
        yapar, bağlantıyı KAPATMAZ. Bağlantının kapanmasını ``finally``
        ile garanti ederek kaynak sızıntısını ve dosya kilitlenmesini
        önlüyoruz.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            # Neden: SQLite varsayılan olarak yabancı anahtarları
            # denetlemez; Cascade silmenin çalışması için açıyoruz.
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _hata_donustur(hata: sqlite3.Error, islem: str,
                       sorgu: str) -> VeritabaniHatasi:
        """``sqlite3`` hatasını projenin özel hatasına çevirir.

        Beklenen UNIQUE çakışmaları yalnızca INFO olarak, diğer hatalar
        ERROR olarak kaydedilir. SQL metni konsola sızmasın diye yalnızca
        DEBUG seviyesinde (log dosyasında) yazılır.
        """
        if isinstance(hata, sqlite3.IntegrityError) \
                and "UNIQUE" in str(hata):
            logger.info("Benzersizlik kısıtı: %s", hata)
            return KayitCakismasiError("Kayıt zaten mevcut.")
        logger.error("%s hatası: %s", islem, hata)
        logger.debug("Hatalı sorgu: %s", sorgu)
        return VeritabaniHatasi(
            f"{islem} sırasında veritabanı hatası oluştu: {hata}"
        )

    @staticmethod
    def _sonuc(cursor: sqlite3.Cursor, sorgu: str) -> int:
        """INSERT için yeni kimliği, diğerleri için etkilenen satırı verir."""
        if sorgu.lstrip().upper().startswith("INSERT"):
            return int(cursor.lastrowid or 0)
        return cursor.rowcount

    def setup_database(self) -> None:
        """Gerekli tabloları ve indeksleri (yoksa) oluşturur.

        Raises:
            VeritabaniHatasi: Veritabanı açılamazsa veya şema kurulamazsa.
        """
        try:
            with self._baglanti() as conn:
                conn.executescript(SCHEMA)
                self._eksik_sutunlari_ekle(conn)
        except sqlite3.Error as hata:
            raise self._hata_donustur(
                hata, "Veritabanı hazırlama", "SCHEMA"
            ) from hata
        logger.debug("Veritabanı tabloları kontrol edildi/oluşturuldu.")

    @staticmethod
    def _eksik_sutunlari_ekle(conn: sqlite3.Connection) -> None:
        """Eski şemada bulunmayan sütunları tablolara ekler (migration).

        Tablo ve sütun adları yalnızca bu dosyadaki sabitlerden geldiği
        için SQL'e doğrudan yazılmaları güvenlidir.
        """
        for tablo, sutun, tanim in _EK_SUTUNLAR:
            mevcut = {satir["name"] for satir
                      in conn.execute(f"PRAGMA table_info({tablo})")}
            if sutun not in mevcut:
                conn.execute(
                    f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tanim}"
                )
                logger.info("Şema güncellendi: %s.%s eklendi", tablo, sutun)

    def execute(self, sorgu: str, params: tuple[Any, ...] = ()) -> int:
        """Tek bir INSERT/UPDATE/DELETE çalıştırır.

        Args:
            sorgu: Parametreli SQL ifadesi.
            params: Sorgu parametreleri.

        Returns:
            INSERT ise yeni satır kimliği, değilse etkilenen satır sayısı.

        Raises:
            KayitCakismasiError: UNIQUE kısıtı ihlal edilirse.
            VeritabaniHatasi: Diğer tüm veritabanı hatalarında.
        """
        try:
            with self._baglanti() as conn:
                return self._sonuc(conn.execute(sorgu, params), sorgu)
        except sqlite3.Error as hata:
            raise self._hata_donustur(hata, "Veri yazma", sorgu) from hata

    def execute_transaction(self, islemler: Sequence[Islem]) -> list[int]:
        """Birden fazla yazma işlemini TEK transaction'da çalıştırır.

        Biri başarısız olursa hiçbiri uygulanmaz (atomiklik).

        Args:
            islemler: ``(sorgu, parametreler)`` çiftlerinin dizisi.

        Returns:
            Her işlem için :meth:`execute` ile aynı türde sonuç listesi.

        Raises:
            KayitCakismasiError: UNIQUE kısıtı ihlal edilirse.
            VeritabaniHatasi: Diğer tüm veritabanı hatalarında.
        """
        sorgu = ""
        try:
            with self._baglanti() as conn:
                sonuclar = []
                for sorgu, params in islemler:
                    sonuclar.append(
                        self._sonuc(conn.execute(sorgu, params), sorgu)
                    )
                return sonuclar
        except sqlite3.Error as hata:
            raise self._hata_donustur(hata, "Veri yazma", sorgu) from hata

    def fetch_all(self, sorgu: str,
                  params: tuple[Any, ...] = ()) -> list[Satir]:
        """SELECT sorgusunun tüm satırlarını sözlük listesi olarak verir.

        Neden: ``sqlite3.Row`` yerine düz ``dict`` döndürerek iş katmanını
        ``sqlite3`` kütüphanesinden bağımsız tutuyoruz.

        Raises:
            VeritabaniHatasi: Sorgu veya bağlantı hatasında.
        """
        try:
            with self._baglanti() as conn:
                return [dict(s) for s in conn.execute(sorgu, params)]
        except sqlite3.Error as hata:
            raise self._hata_donustur(hata, "Veri okuma", sorgu) from hata

    def fetch_one(self, sorgu: str,
                  params: tuple[Any, ...] = ()) -> Satir | None:
        """SELECT sorgusunun ilk satırını verir; sonuç yoksa ``None``.

        Raises:
            VeritabaniHatasi: Sorgu veya bağlantı hatasında.
        """
        try:
            with self._baglanti() as conn:
                satir = conn.execute(sorgu, params).fetchone()
                return dict(satir) if satir else None
        except sqlite3.Error as hata:
            raise self._hata_donustur(hata, "Veri okuma", sorgu) from hata
