import sqlite3
import os

class DBManager:
    def __init__(self, db_name="librotrack.db"):
        # Veritabanı dosyasının src içinde değil, projenin ana dizininde oluşmasını sağlıyoruz
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, db_name)
        self.conn = None
        self.cursor = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        # Sütun isimleriyle verilere erişebilmek için Row factory kullanıyoruz
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        # SQLite'da Foreign Key kısıtlamalarını manuel aktif etmek gerekir
        self.cursor.execute("PRAGMA foreign_keys = ON;")

    def disconnect(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def setup_database(self):
        """Uygulama ilk çalıştığında gerekli 4 tabloyu oluşturur."""
        self.connect()
        
        # 1. Kullanıcılar Tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS kullanicilar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kullanici_adi TEXT UNIQUE NOT NULL
            )
        ''')

        # 2. Kitaplar Tablosu (Evrensel Katalog)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS kitaplar (
                isbn TEXT PRIMARY KEY,
                baslik TEXT NOT NULL,
                yazar TEXT NOT NULL,
                tur TEXT,
                sayfa_sayisi INTEGER
            )
        ''')

        # 3. Okuma Listesi Tablosu (Köprü Tablo)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS okuma_listesi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kullanici_id INTEGER NOT NULL,
                isbn TEXT NOT NULL,
                durum TEXT CHECK(durum IN ('okunacak', 'okunuyor', 'okundu')) NOT NULL,
                bitis_tarihi TEXT,
                FOREIGN KEY (kullanici_id) REFERENCES kullanicilar(id) ON DELETE CASCADE,
                FOREIGN KEY (isbn) REFERENCES kitaplar(isbn) ON DELETE CASCADE,
                UNIQUE(kullanici_id, isbn)
            )
        ''')

        # 4. Notlar Tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notlar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                okuma_listesi_id INTEGER NOT NULL,
                sayfa INTEGER,
                not_metni TEXT NOT NULL,
                FOREIGN KEY (okuma_listesi_id) REFERENCES okuma_listesi(id) ON DELETE CASCADE
            )
        ''')

        self.disconnect()

    def execute(self, query, params=()):
        """Veri ekleme, silme ve güncelleme (INSERT, UPDATE, DELETE) işlemleri."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute(query, params)
            conn.commit()
            
            # Neden: INSERT işlemlerinde yeni ID'yi (lastrowid), UPDATE ve DELETE işlemlerinde ise etkilenen satır sayısını (rowcount) döndürmeliyiz.
            if query.strip().upper().startswith("INSERT"):
                return cursor.lastrowid
            return cursor.rowcount

    def fetch(self, query, params=(), fetch_all=True):
        """Veri okuma (SELECT) işlemleri."""
        self.connect()
        try:
            self.cursor.execute(query, params)
            result = self.cursor.fetchall() if fetch_all else self.cursor.fetchone()
            self.disconnect()
            # SQLite Row nesnelerini standart Python sözlüklerine (dictionary) çeviriyoruz
            if result:
                if fetch_all:
                    return [dict(row) for row in result]
                return dict(result)
            return [] if fetch_all else None
        except sqlite3.Error as e:
            self.disconnect()
            raise e