# LibroTrack - Kişisel Kütüphane ve Okuma Takip Sistemi 📚

LibroTrack, Python ile geliştirilmiş, komut satırı (CLI) üzerinden çalışan, SQLite tabanlı bir kişisel kütüphane ve okuma takip sistemidir.

Proje, **Nesne Yönelimli Programlama (OOP)** prensipleri ve **N-Tier (Çok Katmanlı) Mimari** yaklaşımı kullanılarak geliştirilmiştir.

## Özellikler

* **N-Tier Mimari & OOP:** Veri erişimi, iş mantığı ve sunum katmanlarının birbirinden ayrılması.
* **Open Library API:** ISBN üzerinden kitap başlığı, yazar ve sayfa bilgilerinin otomatik alınması.
* **SQLite:** Harici bir veritabanı sunucusu gerektirmeyen ilişkisel veri yönetimi.
* **Hata Yönetimi & Logging:** Özel Exception sınıfları ve sistem hareketlerinin loglanması.
* **Görsel İstatistikler:** Matplotlib ile kitapların okuma durumlarının grafik olarak gösterilmesi.
* **Birim Testleri:** Pytest kullanılarak temel iş mantığının ve veritabanı kısıtlamalarının test edilmesi.

## Proje Yapısı

LibroTrack/
│
├── src/
│   ├── db_manager.py      # Veritabanı bağlantısı ve sorgu işlemleri
│   ├── library.py         # İş mantığı ve API işlemleri
│   └── models.py          # Kitap ve Kullanıcı OOP sınıfları
│
├── tests/                 # Pytest birim testleri
├── main.py                # CLI giriş noktası
├── requirements.txt       # Bağımlılık listesi
└── README.md              # Proje dokümantasyonu


## Mimari

CLI (main.py)
      ↓
Business Logic (library.py)
      ↓
Data Access (db_manager.py)
      ↓
SQLite

* **Presentation Layer:** `main.py`
* **Business Logic Layer:** `library.py`
* **Data Access Layer:** `db_manager.py`
* **Models:** `models.py`

## Kurulum

Repoyu klonlayın:

```bash
git clone https://github.com/mcan-dev/LibroTrack.git
cd LibroTrack
```

Sanal ortam oluşturun:

```bash
python -m venv venv
```

Windows:

```bash
.\venv\Scripts\activate
```

Linux / macOS:

```bash
source venv/bin/activate
```

Bağımlılıkları yükleyin:

```bash
pip install -r requirements.txt
```

## Konfigürasyon

Proje ana dizininde `.env` dosyası oluşturun:

```env
DB_PATH=librotrack.db
LOG_LEVEL=INFO
```

## Kullanım

### Kitap Eklemek

ISBN üzerinden bilgileri otomatik almak için:

```bash
python main.py kitap-ekle --isbn 9780201633610
```

Manuel kitap eklemek için:

```bash
python main.py kitap-ekle --isbn 1234567890 --baslik "1984" --yazar "George Orwell" --tur "Distopya" --sayfa 328
```

### Kitap Durumunu Güncellemek

Durumlar: `okunacak`, `okunuyor`, `okundu`

```bash
python main.py durum-guncelle --isbn 9780201633610 --durum okunuyor
```

### Sayfaya Not Eklemek

```bash
python main.py not-ekle --isbn 9780201633610 --sayfa 45 --metin "Nesne yönelimli tasarımın temelleri."
```

### Kitapları Listelemek

Tüm kitaplar:

```bash
python main.py kitap-listele
```

Belirli bir durumdaki kitaplar:

```bash
python main.py kitap-listele --durum okunuyor
```

### İstatistikleri Görüntülemek

```bash
python main.py istatistik
```

##  Testler

Testleri çalıştırmak için:

```bash
pytest tests/ -v
```
