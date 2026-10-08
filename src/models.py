from dataclasses import dataclass
from typing import Optional

# Neden: Veri taşıyan (DTO) sınıflarda __init__ gibi standart metotları manuel yazmamak için @dataclass kullanıyoruz.
@dataclass
class Kullanici:
    kullanici_adi: str
    # Neden: Yeni oluşturulan kullanıcının henüz DB'ye kaydedilmediği (ID almadığı) durumlar için None izni veriyoruz.
    id: Optional[int] = None

@dataclass
class Kitap:
    # Neden: Evrensel katalogda her kitabın eşsiz bir kimliğe (barkoda) ihtiyacı var, bu yüzden Optional değil.
    isbn: str
    baslik: str
    yazar: str
    # Neden: API her zaman tür veya sayfa sayısı döndürmeyebilir, eksik verinin sistemi çökertmemesi için Optional yaptık.
    tur: Optional[str] = None
    sayfa_sayisi: Optional[int] = None

@dataclass
class OkumaKaydi:
    kullanici_id: int
    isbn: str
    # Neden: Veri doğrulamasını SQLite (CHECK) ve CLI seviyesinde yaptığımız için burada Enum kullanıp modeli ağırlaştırmadık.
    durum: str
    id: Optional[int] = None
    # Neden: SQLite'ın yerleşik tarih tipi olmadığı için, ISO formatında (YYYY-MM-DD) string olarak saklıyoruz.
    bitis_tarihi: Optional[str] = None

@dataclass
class Not:
    # Neden: Notları doğrudan kitaba değil, kullanıcının o kitabı okuduğu özel oturuma bağlamak için kullanıyoruz.
    okuma_listesi_id: int
    not_metni: str
    sayfa: Optional[int] = None
    id: Optional[int] = None