# LibroTrack - Kişisel Kütüphane ve Okuma Takip Sistemi

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
│   ├── config.py          # .env okuma, sabitler ve logging ayarları
│   ├── db_manager.py      # Veritabanı bağlantısı ve sorgu işlemleri
│   ├── exceptions.py      # Özel exception sınıfları
│   ├── grafikler.py       # Pasta ve aylık çubuk grafikleri (matplotlib)
│   ├── library.py         # İş mantığı ve API işlemleri
│   └── models.py          # Kitap ve Kullanıcı OOP sınıfları
│
├── tests/                 # Pytest birim testleri (modeller, iş mantığı, CLI)
├── libro.py               # CLI giriş noktası
├── requirements.txt       # Bağımlılık listesi
└── README.md              # Proje dokümantasyonu


## Mimari

CLI (libro.py)
      ↓
Business Logic (library.py)
      ↓
Data Access (db_manager.py)
      ↓
SQLite

* **Presentation Layer:** `libro.py`
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
LOG_FILE=librotrack.log
```

## Kullanım

### Kitap Eklemek

ISBN üzerinden bilgileri otomatik almak için:

```bash
python libro.py kitap-ekle --isbn 9780201633610
```

Manuel kitap eklemek için:

```bash
python libro.py kitap-ekle --isbn 1234567890 --baslik "1984" --yazar "George Orwell" --tur "Distopya" --sayfa-sayisi 328
```
### Kitap Silmek ve Güncellemek

```bash
python libro.py kitap-sil --isbn 9780201633610 
python libro.py kitap-guncelle --isbn 9780201633610 --tur "Yazılım" --sayfa-sayisi 400
```

### Kitap Aramak
```bash
python libro.py kitap-ara --anahtar-kelime orwell
```

### Kitap Durumunu Güncellemek

Durumlar: `okunacak`, `okunuyor`, `okundu`

```bash
python libro.py durum-guncelle --isbn 9780201633610 --durum okunuyor
```

### Sayfaya Not Eklemek

```bash
python libro.py not-ekle --isbn 9780201633610 --sayfa 45 --not "Nesne yönelimli tasarımın temelleri."
```

Bir kitabın notlarını görmek için:

```bash
python libro.py not-listele --isbn 9780201633610
```
### Kitapları Listelemek

Tüm kitaplar:

```bash
python libro.py kitap-listele
```

Belirli bir durumdaki kitaplar:

```bash
python libro.py kitap-listele --durum okunuyor
python libro.py kitap-listele --tur "Roman"
```

Sonuç tablo olarak listelenir.

### İstatistik ve Dışa Aktarım

```bash
python libro.py istatistik
python libro.py istatistik --yil 2025
python libro.py disa-aktar
```

`istatistik` toplam kitap, okunan kitap ve tamamlanan sayfa sayısını yazar;
tür dağılımı pasta grafiğini `okuma_grafigi.png`, aylık okuma grafiğini
`aylik_okuma_grafigi.png` dosyasına kaydeder. `disa-aktar` okunmuş kitapları
`okunan_kitaplar.csv` dosyasına yazar.

### Çoklu Kullanıcı (`-u`)

Her kullanıcının kitaplığı birbirinden ayrıdır. `-u` parametresi komuttan **önce** yazılır; verilmezse `default_user` kullanılır (otomatik oluşur). Diğer profiller önce
`kullanici-ekle` ile oluşturulmalıdır:

```bash
python libro.py kullanici-ekle --ad ayse
python libro.py kullanici-listele
python libro.py -u ayse kitap-ekle --isbn 9780201633610
python libro.py -u ayse kitap-listele
python libro.py kullanici-sil --ad ayse --onayla
```

## Hata Yönetimi ve Loglama

Hatalar yakalanarak kullanıcıya anlaşılır mesaj gösterilir.

| Exception | Ne zaman fırlatılır |
| --- | --- |
| `VeritabaniHatasi` | Veritabanı bağlantısı veya sorgusu başarısız olduğunda |
| `KayitCakismasiError` | `VeritabaniHatasi` alt sınıfı; benzersizlik (UNIQUE) kısıtı ihlal edildiğinde |
| `KitapBulunamadiError` | Kitap kullanıcının kitaplığında olmadığı halde silme, güncelleme, durum değiştirme, not ekleme veya dışa aktarma yapılmak istendiğinde |
| `KitapZatenVarError` | Kitap kullanıcının kitaplığında zaten varken tekrar eklenmek istendiğinde |
| `GecersizParametreError` | Geçersiz değer girildiğinde (örn. boş kullanıcı adı, geçersiz durum, negatif sayfa sayısı) |
| `DisaAktarimHatasi` | CSV veya grafik dosyası yazılamadığında |

Tüm hatalar `LibroTrackError` temel sınıfından türer; `libro.py` bunları tek noktada yakalar, mesajı standart hata çıkışına (stderr) yazar ve çıkış koduyla `1` döner. Veritabanı yazma işlemleri transaction içinde yapılır; hata olursa değişiklikler geri alınır.

Loglama `src/config.py` içinde yapılandırılır. Log dosyasına (`LOG_FILE`) DEBUG ve üstü her zaman yazılır; konsola `LOG_LEVEL` (varsayılan INFO) ve üstü düşer. Konsolu sadeleştirmek için `.env` içinde `LOG_LEVEL=WARNING` yazın. Çalıştırılan her komut, yapılan ekleme/silme/güncelleme işlemleri ve başarısız olan komutlar log dosyasında kayıt altına alınır.

##  Testler

Testleri çalıştırmak için:

```bash
pytest tests/ -v
```
