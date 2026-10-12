"""
LibroTrack Özel Hata (Exception) Sınıfları.

Sistemin kontrolsüz çökmesini engellemek için kullanılan özel hatalar.
Hepsi tek bir temel sınıftan türediği için CLI katmanı tek bir
``except LibroTrackError`` ile tüm beklenen hataları yakalayabilir.

Hata hiyerarşisi::

    LibroTrackError
    ├── KitapBulunamadiError
    ├── KitapZatenVarError
    ├── KullaniciBulunamadiError
    ├── KullaniciZatenVarError
    ├── GecersizParametreError
    ├── DisaAktarimHatasi
    ├── APIHatasi
    └── VeritabaniHatasi
        └── KayitCakismasiError
"""


class LibroTrackError(Exception):
    """Proje genelindeki tüm özel hataların miras aldığı temel sınıf."""


class KitapBulunamadiError(LibroTrackError):
    """Kitap, kullanıcının listesinde bulunamadığında fırlatılır."""


class KitapZatenVarError(LibroTrackError):
    """Kitap, kullanıcının listesinde zaten mevcut olduğunda fırlatılır."""


class GecersizParametreError(LibroTrackError):
    """Kullanıcı hatalı, eksik veya mantıksız değer girdiğinde fırlatılır."""


class DisaAktarimHatasi(LibroTrackError):
    """CSV veya grafik gibi çıktı dosyaları yazılamadığında fırlatılır."""


class VeritabaniHatasi(LibroTrackError):
    """SQLite tarafında bağlantı veya sorgu hatası oluştuğunda fırlatılır."""


class KayitCakismasiError(VeritabaniHatasi):
    """Benzersizlik (UNIQUE) kısıtı ihlal edildiğinde fırlatılır."""


class KullaniciBulunamadiError(LibroTrackError):
    """İstenen kullanıcı profili sistemde kayıtlı olmadığında fırlatılır."""


class KullaniciZatenVarError(LibroTrackError):
    """Oluşturulmak istenen kullanıcı profili zaten mevcut olduğunda."""


class APIHatasi(LibroTrackError):
    """Open Library'den kapak gibi bir veri alınamadığında fırlatılır."""
