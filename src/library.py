import requests
from src.db_manager import DBManager

class Kutuphane:
    def __init__(self):
        self.db = DBManager()
        self.db.setup_database()

    def kullanici_getir_veya_olustur(self, kullanici_adi: str) -> int:
        kullanici = self.db.fetch("SELECT id FROM kullanicilar WHERE kullanici_adi = ?", (kullanici_adi,), fetch_all=False)
        if kullanici:
            return kullanici['id']
        # Neden: Kullanıcı CLI'ı ilk kez kullanıyorsa kayıt aşamasıyla uğraştırmadan arka planda doğrudan profilini oluşturuyoruz.
        return self.db.execute("INSERT INTO kullanicilar (kullanici_adi) VALUES (?)", (kullanici_adi,))

    def api_kitap_sorgula(self, isbn: str) -> dict:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        try:
            # Neden: API sunucuları yavaşlarsa CLI ekranının sonsuza kadar donmasını engellemek için 5 saniyelik timeout koyduk.
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                key = f"ISBN:{isbn}"
                if key in data:
                    kitap_data = data[key]
                    yazarlar = ", ".join([yazar['name'] for yazar in kitap_data.get('authors', [])])
                    return {
                        "baslik": kitap_data.get('title', 'Bilinmeyen Başlık'),
                        "yazar": yazarlar if yazarlar else 'Bilinmeyen Yazar',
                        "sayfa_sayisi": kitap_data.get('number_of_pages', None)
                    }
        except requests.RequestException:
            # Neden: İnternet kesikse uygulamanın çökmesi yerine 'None' dönerek CLI'daki manuel giriş formunu devreye sokuyoruz.
            pass 
        return None

    def kitap_ekle(self, kullanici_id: int, isbn: str, baslik: str, yazar: str, tur: str = None, sayfa_sayisi: int = None, durum: str = 'okunacak') -> bool:
        # Neden: Kitap evrensel katalogda yoksa Foreign Key hatası almamak için önce oraya ekliyoruz.
        mevcut_kitap = self.db.fetch("SELECT isbn FROM kitaplar WHERE isbn = ?", (isbn,), fetch_all=False)
        if not mevcut_kitap:
            self.db.execute(
                "INSERT INTO kitaplar (isbn, baslik, yazar, tur, sayfa_sayisi) VALUES (?, ?, ?, ?, ?)",
                (isbn, baslik, yazar, tur, sayfa_sayisi)
            )
        
        try:
            self.db.execute(
                "INSERT INTO okuma_listesi (kullanici_id, isbn, durum) VALUES (?, ?, ?)",
                (kullanici_id, isbn, durum)
            )
            return True
        except Exception:
            # Neden: Aynı kullanıcı aynı kitabı ikinci kez eklerse veritabanındaki UNIQUE kısıtlaması hata fırlatır. Bunu yakalayıp işlemi durduruyoruz.
            return False

    def kitap_sil(self, kullanici_id: int, isbn: str) -> bool:
        satir_sayisi = self.db.execute(
            "DELETE FROM okuma_listesi WHERE kullanici_id = ? AND isbn = ?", 
            (kullanici_id, isbn)
        )
        return satir_sayisi > 0

    def kitaplari_listele(self, kullanici_id: int, durum: str = None):
        # Neden: Kitap sabit bilgileri ve kullanıcının eylemi (durum) farklı tablolarda olduğu için JOIN ile tek sorguda birleştiriyoruz.
        query = """
            SELECT k.isbn, k.baslik, k.yazar, o.durum 
            FROM okuma_listesi o
            JOIN kitaplar k ON o.isbn = k.isbn
            WHERE o.kullanici_id = ?
        """
        params = [kullanici_id]
        
        if durum:
            query += " AND o.durum = ?"
            params.append(durum)
            
        return self.db.fetch(query, tuple(params))

    def durum_guncelle(self, kullanici_id: int, isbn: str, yeni_durum: str) -> bool:
        # Neden: Durum bilgisini kitapta değil okuma_listesi (köprü) tablosunda tuttuğumuz için güncellemeyi spesifik kullanıcıya özel yapıyoruz.
        satir_sayisi = self.db.execute(
            "UPDATE okuma_listesi SET durum = ? WHERE kullanici_id = ? AND isbn = ?",
            (yeni_durum, kullanici_id, isbn)
        )
        return satir_sayisi > 0

    def not_ekle(self, kullanici_id: int, isbn: str, not_metni: str, sayfa: int = None) -> bool:
        # Neden: Notu doğrudan kitaba değil, o kullanıcının ilgili kitabı okuma serüvenine (okuma_listesi_id) bağlıyoruz.
        okuma_kaydi = self.db.fetch(
            "SELECT id FROM okuma_listesi WHERE kullanici_id = ? AND isbn = ?", 
            (kullanici_id, isbn), 
            fetch_all=False
        )
        
        if not okuma_kaydi:
            return False # Kullanıcının listesinde böyle bir kitap yoksa not eklenemez
            
        self.db.execute(
            "INSERT INTO notlar (okuma_listesi_id, not_metni, sayfa) VALUES (?, ?, ?)",
            (okuma_kaydi['id'], not_metni, sayfa)
        )
        return True

    def istatistik_getir(self, kullanici_id: int):
        # Neden: İstatistik için tüm tabloyu çekip Python'da saymak (memory israfı) yerine, yükü veritabanı motoruna (SQL GROUP BY) bırakıyoruz.
        query = """
            SELECT durum, COUNT(*) as sayi 
            FROM okuma_listesi 
            WHERE kullanici_id = ? 
            GROUP BY durum
        """
        return self.db.fetch(query, (kullanici_id,))