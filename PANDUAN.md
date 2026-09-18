# Flight Monitor — Panduan Setup

Alur deploy-nya SAMA PERSIS seperti project Report Bagasi kemarin:
GitHub -> PythonAnywhere -> PWABuilder jadi APK.
Bedanya, project ini butuh 3 pengaturan tambahan sebelum dipakai.

## 1. Daftar API key AeroDataBox (gratis)

1. Buka rapidapi.com, buat akun (gratis)
2. Cari "AeroDataBox" di kolom pencarian
3. Pilih plan gratisnya, subscribe
4. Copy "X-RapidAPI-Key" yang muncul di halaman itu

> Catatan: kuota gratisnya bisa berubah sewaktu-waktu, cek halaman
> pricing AeroDataBox saat kamu daftar. Kalau kuota kelewat kecil
> buat kebutuhanmu, jadwal cek di langkah 4 di bawah bisa diperlonggar
> (misal tiap 10-15 menit, bukan 5 menit) biar kuota lebih awet.

## 2. Isi app.py

Buka `app.py`, cari bagian atas ("ISI BAGIAN INI"), isi:

```python
AERODATABOX_API_KEY = "..."   # dari langkah 1
CRON_KUNCI = "..."            # bikin kata sandi acak sendiri, bebas
VAPID_CLAIMS_SUB = "mailto:emailkamu@contoh.com"  # ganti sesukamu
```

`VAPID_PUBLIC_KEY` diisi belakangan (langkah 3).

## 3. Generate kunci VAPID (buat notifikasi)

Setelah project di-upload ke GitHub & sudah di-`git pull` di PythonAnywhere
(lihat langkah 4-5), buka Bash console PythonAnywhere, masuk ke folder
project, lalu jalankan:

```
pip3.10 install --user -r requirements.txt
python3.10 generate_vapid.py
```

Ini akan:
- Membuat file `vapid_private.pem` di folder project (JANGAN dihapus,
  JANGAN diupload ke GitHub publik kalau repo-nya public)
- Mencetak baris `VAPID_PUBLIC_KEY = "..."` — copy itu, tempel ke
  `app.py` (ganti baris `VAPID_PUBLIC_KEY = "ISI_SETELAH_GENERATE_VAPID"`)

Setelah itu save app.py, lalu Reload web app di tab Web.

## 4. Deploy ke GitHub + PythonAnywhere

Sama seperti project sebelumnya:
1. Bikin repo baru di GitHub, upload semua isi folder ini (jaga
   struktur folder `templates/` dan `static/`)
2. PythonAnywhere -> Web -> Add a new web app -> Manual configuration
   -> Python 3.10
3. Consoles -> Bash -> `git clone https://github.com/USERNAME/REPO.git`
4. Source code & Working directory diarahkan ke folder hasil clone
5. Edit WSGI configuration file:
   ```python
   import sys
   path = '/home/USERNAME/NAMA_REPO'
   if path not in sys.path:
       sys.path.append(path)
   from app import app as application
   ```
6. `pip3.10 install --user -r requirements.txt`
7. Jalankan `python3.10 generate_vapid.py` (langkah 3 di atas)
8. Reload web app

## 5. Setup cron pengecekan berkala (WAJIB, ini "jantung"-nya notifikasi)

PythonAnywhere gratis tidak bisa jalanin tugas terjadwal sendiri, jadi
pakai layanan gratis dari luar:

1. Buka **cron-job.org**, daftar akun gratis
2. Buat cronjob baru, isi URL:
   ```
   https://USERNAME.pythonanywhere.com/api/cron/cek?kunci=KUNCI_RAHASIA_DI_APP_PY
   ```
3. Atur jadwal tiap **5 menit**
4. Aktifkan

Tiap kali cronjob ini jalan, server bakal ngecek semua flight yang
lagi dipantau, update status, dan kirim notifikasi kalau ada yang
baru landing.

## 6. Bungkus jadi APK (PWABuilder)

Sama seperti sebelumnya — buka pwabuilder.com, masukkan URL
`https://USERNAME.pythonanywhere.com`, Package for stores -> Android.

**Catatan soal notifikasi di APK:** setelah install APK, buka
aplikasinya, akan ada banner "Aktifkan notifikasi" di atas — HARUS
ditekan & izin notifikasi HARUS diberikan, baru notifikasi landing
bisa muncul di status bar.

## Kalau field data dari AeroDataBox ternyata beda dari dugaan

Saya menulis kode pembacaan datanya (`rapikan_data_flight` di
app.py) berdasarkan struktur umum AeroDataBox, tapi API pihak
ketiga kadang berubah format. Kalau setelah pasang API key ternyata
ada data yang kosong terus (misal nama maskapai atau estimasi
waktu), kirim contoh respons mentah API-nya (bisa dilihat dengan
buka langsung di browser:
`https://aerodatabox.p.rapidapi.com/...` lewat RapidAPI's
"Test Endpoint" di dashboard mereka) dan saya perbaiki mapping-nya.
