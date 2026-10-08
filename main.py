import argparse
import sys
from src.library import Kutuphane

def main():
    # Neden: Terminalden girilen komutları ve parametreleri manuel parçalamak yerine, Python'ın yerleşik argparse kütüphanesini kullanarak hata oranını sıfıra indiriyoruz.
    parser = argparse.ArgumentParser(description="LibroTrack - Kişisel Kütüphane ve Okuma Takip Sistemi")
    
    # Neden: Sistemi çoklu kullanıcıya hazır hale getirmek için varsayılan bir profil tanımlıyoruz. İstenirse '-u mustafa' şeklinde değiştirilebilir.
    parser.add_argument('-u', '--kullanici', default='varsayilan_kullanici', help='İşlem yapılacak kullanıcı adı')
    
    subparsers = parser.add_subparsers(dest='komut', required=True, help='Kullanılabilir komutlar')
    # 6. istatistik Komutu
    istatistik_parser = subparsers.add_parser('istatistik', help='Okuma durumlarına göre pasta grafiği çizer')

    # 1. kitap-ekle Komutu
    ekle_parser = subparsers.add_parser('kitap-ekle', help='Yeni kitap ekler')
    ekle_parser.add_argument('--isbn', required=True, help='Kitabın ISBN numarası')
    ekle_parser.add_argument('--baslik', help='Kitabın başlığı (API bulamazsa zorunlu)')
    ekle_parser.add_argument('--yazar', help='Kitabın yazarı (API bulamazsa zorunlu)')
    ekle_parser.add_argument('--tur', help='Kitabın türü')
    ekle_parser.add_argument('--sayfa', type=int, help='Sayfa sayısı')

    # 2. kitap-sil Komutu
    sil_parser = subparsers.add_parser('kitap-sil', help='Kitabı listeden siler')
    sil_parser.add_argument('--isbn', required=True, help='Silinecek kitabın ISBN numarası')

    # 3. kitap-listele Komutu
    listele_parser = subparsers.add_parser('kitap-listele', help='Kitapları listeler')
    # Neden: choices parametresi ile kullanıcının hatalı bir durum (örn: 'yarım_kaldı') girmesini komut satırında engelleyerek veritabanı kısıtlamalarıyla (CHECK) uyumu sağlıyoruz.
    listele_parser.add_argument('--durum', choices=['okunacak', 'okunuyor', 'okundu'], help='Belirli durumdaki kitapları listele')

    # 4. durum-guncelle Komutu
    durum_parser = subparsers.add_parser('durum-guncelle', help='Kitabın okuma durumunu günceller')
    durum_parser.add_argument('--isbn', required=True, help='Güncellenecek kitabın ISBN numarası')
    durum_parser.add_argument('--durum', required=True, choices=['okunacak', 'okunuyor', 'okundu'], help='Yeni durum')

    # 5. not-ekle Komutu
    # Neden: '--metin' argümanını tırnak içinde bekliyoruz, aksi halde terminal boşluk karakterlerini yeni bir parametre sanıp programı çökertir.
    not_parser = subparsers.add_parser('not-ekle', help='Kitaba not ekler')
    not_parser.add_argument('--isbn', required=True, help='Not eklenecek kitabın ISBN numarası')
    not_parser.add_argument('--metin', required=True, help='Eklenecek not metni (Tırnak içinde yazınız)')
    not_parser.add_argument('--sayfa', type=int, help='Notun ait olduğu sayfa numarası')

    args = parser.parse_args()
    
    # Neden: DB bağlantısını ve API köprüsünü tek bir nesne (Kutuphane) üzerinden yöneterek, arayüz (main.py) dosyasını iş mantığından soyutluyoruz (N-Tier kuralı).
    kutuphane = Kutuphane()
    kullanici_id = kutuphane.kullanici_getir_veya_olustur(args.kullanici)

    if args.komut == 'kitap-ekle':
        baslik = args.baslik
        yazar = args.yazar
        sayfa = args.sayfa

        # Neden: Kullanıcı başlık ve yazar bilgisini komut satırına yazmaya üşendiyse, API üzerinden veriyi otomatik çekerek kullanıcı deneyimini artırıyoruz.
        if not baslik or not yazar:
            print(f"[*] {args.isbn} numaralı kitap Open Library API'de aranıyor...")
            api_veri = kutuphane.api_kitap_sorgula(args.isbn)
            
            if api_veri:
                print("\n--- API'den Gelen Bilgiler ---")
                print(f"Başlık: {api_veri['baslik']}")
                print(f"Yazar: {api_veri['yazar']}")
                print(f"Sayfa : {api_veri['sayfa_sayisi']}")
                print("------------------------------")
                
                # Neden: API'den gelen veriler (özellikle yazar isimleri) hatalı/eksik olabileceği için, veritabanına yazmadan önceki son onayı kullanıcıya bırakıyoruz.
                cevap = input("Bu kitabı kaydetmek istiyor musunuz? [E]vet / [H]ayır / [D]üzenle: ").strip().upper()
                
                if cevap == 'E':
                    baslik = api_veri['baslik']
                    yazar = api_veri['yazar']
                    sayfa = api_veri['sayfa_sayisi'] if not sayfa else sayfa
                elif cevap == 'D':
                    print(f"\n[!] İşlem iptal edildi. Lütfen komutu şu şekilde çalıştırın:")
                    print(f"python main.py kitap-ekle --isbn {args.isbn} --baslik \"Doğru Başlık\" --yazar \"Doğru Yazar\"")
                    sys.exit(0)
                else:
                    print("[-] İşlem iptal edildi.")
                    sys.exit(0)
            else:
                print("[-] HATA: Kitap API'de bulunamadı. Lütfen --baslik ve --yazar parametrelerini manuel giriniz.")
                sys.exit(1)

        basari = kutuphane.kitap_ekle(kullanici_id, args.isbn, baslik, yazar, args.tur, sayfa)
        if basari:
            print(f"[+] '{baslik}' başarıyla eklendi!")
        else:
            print("[-] Hata: Bu kitap zaten profilinizde mevcut.")

    elif args.komut == 'kitap-sil':
        if kutuphane.kitap_sil(kullanici_id, args.isbn):
            print(f"[+] {args.isbn} numaralı kitap silindi.")
        else:
            print("[-] Kitap bulunamadı veya silinemedi.")

    elif args.komut == 'kitap-listele':
        kitaplar = kutuphane.kitaplari_listele(kullanici_id, args.durum)
        if not kitaplar:
            print("[-] Listenizde bu kritere uygun kitap bulunmuyor.")
        else:
            print(f"\n--- Okuma Listesi ---")
            for k in kitaplar:
                # Neden: Terminalde verilerin kaymasını önlemek ve tablo (grid) görünümü vermek için Python string formatlama (:<15) ile sabit boşluklar ekliyoruz.
                print(f"ISBN: {k['isbn']:<15} | Başlık: {k['baslik'][:20]:<20} | Yazar: {k['yazar'][:15]:<15} | Durum: {k['durum']}")

    elif args.komut == 'durum-guncelle':
        # Neden: Yetkisiz güncellemeleri önlemek için işlemi sadece giriş yapan 'kullanici_id' ve o kullanıcının listesindeki 'isbn' üzerinden yapıyoruz.
        if kutuphane.durum_guncelle(kullanici_id, args.isbn, args.durum):
            print(f"[+] {args.isbn} numaralı kitabın durumu '{args.durum}' olarak güncellendi.")
        else:
            print("[-] Hata: Kitap profilinizde bulunamadı.")

    elif args.komut == 'not-ekle':
        # Neden: Notu kitaba değil, kullanıcının okuma kaydına bağlıyoruz. Böylece başka bir kullanıcı aynı kitabı okurken başkasının notlarını görmüyor.
        if kutuphane.not_ekle(kullanici_id, args.isbn, args.metin, args.sayfa):
            print(f"[+] Nota eklendi: '{args.metin[:30]}...'")
        else:
            print("[-] Hata: Kitap profilinizde bulunamadı, not eklenemedi.")

    elif args.komut == 'istatistik':
        veriler = kutuphane.istatistik_getir(kullanici_id)
        if not veriler:
            print("[-] Grafiği çizilecek herhangi bir kitap verisi bulunamadı.")
        else:
            try:
                # Neden: matplotlib'i dosyanın en başında import etmiyoruz. Sadece bu komut çalıştırıldığında yüklenmesini sağlayarak, CLI'ın diğer komutlardaki çalışma hızını koruyoruz.
                import matplotlib.pyplot as plt
                
                durumlar = [v['durum'].upper() for v in veriler]
                sayilar = [v['sayi'] for v in veriler]
                
                plt.figure(figsize=(6, 6))
                plt.pie(sayilar, labels=durumlar, autopct='%1.1f%%', startangle=140, colors=['#ff9999','#66b3ff','#99ff99'])
                plt.title(f"{args.kullanici} Profili Okuma İstatistikleri")
                
                print("[+] İstatistik grafiği hazırlanıyor...")
                plt.show()
            except ImportError:
                print("[-] Hata: matplotlib kütüphanesi eksik. Lütfen terminalde 'pip install matplotlib' komutunu çalıştırın.")

if __name__ == '__main__':
    main()