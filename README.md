# 🎬 YouTube Video Updater (EBS)

**Amaç:** Bu araç, **yükleme yapmadan** mevcut YouTube videolarınızın meta verilerini (başlık, açıklama, etiketler, kategori, gizlilik, publishAt, thumbnail, playlist) **toplu olarak günceller**.  
Excel/CSV tablosu ile çalışır ve metro (ttkbootstrap) tarzı modern bir GUI sunar.

> Not: Video yükleme (videos.insert) yapmaz. Yalnızca güncelleme çağrılarını kullanır (kota açısından çok daha ekonomiktir).

---

## 🚀 Özellikler
- Excel/CSV’den **video_id** bazlı toplu güncelleme
- Başlık, açıklama, etiket, kategori, gizlilik (`public|unlisted|private|scheduled`)
- Planlı yayın (`publishAt`) desteği
- Thumbnail yükleme (Shorts için opsiyonel atlama)
- Playlist’e ekleme (URL’den `list=` ID’si otomatik ayıklanır)
- Son yüklenen videoları ve playlistleri GUI’den listeleme
- Eşzamanlı (multi-thread) işlem, anlık log ve durum takibi
- ttkbootstrap ile modern arayüz

---

## 📦 Kurulum
```bash
pip install -r requirements.txt
```

> Python 3.9+ önerilir.

---

## ▶️ Çalıştırma
```bash
python youtube_video_updater.py
```

GUI’de:
1. **Dosya Seç** → Excel/CSV dosyanı seç.
2. **Google’da Yetkilendir** → Tarayıcıda giriş yap, izin ver.
3. **Güncellemeyi Başlat** → Satırlar işlenir.
4. (İsteğe bağlı) **Oynatma Listelerimi Göster** / **Son Videoları Göster** butonlarını kullan.

---

## 🔑 API ve Yetkilendirme (YouTube Data API v3)
1. **Google Cloud Console**: https://console.cloud.google.com/
2. Yeni **Proje** oluştur.
3. **APIs & Services → Library** → **YouTube Data API v3** → **Enable**.
4. **APIs & Services → OAuth consent screen**:
   - **User Type: External**, App Name/Emails doldur.
   - **Test Users** bölümüne YouTube kanalında oturum açtığın Gmail hesabını ekle.
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - **Application type = Desktop App** → JSON’u indir.
6. İndirdiğin JSON’u proje klasörüne **`client_secret.json`** adıyla koy.
7. Uygulamayı çalıştır → **Google’da Yetkilendir** → izin ver → ilk girişte **`token.json`** oluşur.

> Gerekli OAuth kapsamları (scopes):  
> - `https://www.googleapis.com/auth/youtube.upload`  
> - `https://www.googleapis.com/auth/youtube`

---

## 📊 Excel / CSV Şablonu
Örnek dosyaları: **`youtube_video_updater_template.xlsx`**, **`youtube_video_updater_template.csv`**

Zorunlu sütun: `video_id`  
İsteğe bağlı sütunlar: `title, description, tags, categoryId, privacyStatus, publishAt, made_for_kids, thumbnail_path, playlist_id, is_short`

| video_id     | title               | description            | tags                    | categoryId | privacyStatus | publishAt                  | made_for_kids | thumbnail_path           | playlist_id | is_short |
|--------------|---------------------|------------------------|-------------------------|------------|---------------|----------------------------|---------------|--------------------------|-------------|----------|
| QP54m2M24VZI  | Yeni Başlık 1       | Yeni açıklama\nDevam  | beykoz,haber,gündem     | 22         |               |                            | false         |                          |             |          |
| dQw4w19WgXcQ  |                     | Planlı yayın örneği    | teknoloji,gelecek       |            | scheduled     | 2025-10-05T14:00:00+03:00 |               |                          |             |          |
| 3JZ_D23ELwOQ  | Kısa Video Başlığı  | Shorts açıklaması      | short,deneme            | 22         | public        |                            | false         | C:\vid\thumb.jpg       |             | true     |
| 9bZkp27q19f0  |                     |                        |                         |            | public        |                            |               |                          | https://www.youtube.com/playlist?list=PLxxxx |          |

> Notlar:
> - `privacyStatus`: `public | unlisted | private | scheduled`
> - `publishAt`: ISO 8601 (TZ’li) → `YYYY-MM-DDTHH:MM:SS+03:00`
> - `is_short = true` ise thumbnail API çağrısı atlanır.
> - `playlist_id` alanına tam URL verebilirsin; program `list=` değerini ID olarak ayıklar.

---

## ⚙️ Kota (Quota)
- `videos.update`, `thumbnails.set`, `playlistItems.insert` çağrıları **düşük kota** harcar.
- Video yükleme yapılmadığı için (en pahalı işlem olan `videos.insert` yok), **günlük çok sayıda düzenlemeyi** rahatça yapabilirsin.

---

## 🧩 Hata/Sorun Giderme
- **403 `access_denied`** → OAuth **Test Users** listesine hesap ekli mi?
- **`Playlist not found`** → URL değilse ID yanlış olabilir ya da erişim yoktur.
- **Thumbnail reddi** → jpg/png önerilir, 2MB altı, 1280×720 ve üstü.
- **Kanal seçimi** → Marka hesabı kullanıyorsan yetkilendirmede doğru kanalı seç.

---

## 📜 Lisans
MIT License
