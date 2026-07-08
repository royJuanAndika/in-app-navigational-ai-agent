# Script Tag Testing — Dampak `<script>` terhadap Akurasi Identifikasi Trigger

## Latar Belakang

Pipeline NKG (Navigational Knowledge Graph) saya melakukan cleaning pada HTML mentah sebelum dikirim ke LLM untuk ekstraksi elemen dan trigger. Salah satu langkah cleaning adalah menghapus seluruh `<script>` tag (inline maupun external) menggunakan `PRESTRIP_SELECTORS` di `4_clean_html_filter.ipynb`.

Penguji sidang mengajukan keberatan: banyak elemen UI memiliki atribut `onclick` yang memanggil fungsi JavaScript yang definisinya ada di dalam `<script>` tag. Contohnya, tombol "Export TXT" memiliki `onclick="download_txt()"`, namun fungsi `download_txt()` sendiri ada di dalam `<script>` tag yang sudah dihapus. Tanpa melihat kode fungsi, LLM tidak bisa mengetahui apa yang sebenarnya dilakukan tombol tersebut.

Eksperimen ini menguji dampak penghapusan `<script>` tag terhadap akurasi identifikasi trigger oleh LLM.

## Halaman Uji

Halaman yang digunakan: `customer_report_scan.html` (laporan Absensi Mesin).

Pemilihan halaman ini didasarkan pada ukurannya yang kecil (302 baris cleaned HTML, 20 DOM IDs) sehingga cocok untuk pengujian cepat dan analisis manual.

## Metodologi

Dua pendekatan diuji dengan parameter LLM, chunking, dan prompt yang identik:

### Pendekatan 1: No-Script (baseline — digunakan di seluruh pipeline)

HTML hasil cleaning standar tanpa `<script>` tag. Pendekatan ini sudah diterapkan di seluruh pipeline NKG untuk 47 halaman.

### Pendekatan 2: With-Script-Context (eksperimen)

HTML cleaned yang sama, namun konten inline `<script>` (12 script, tanpa external library) di-append ke setiap chunk prompt yang dikirim ke LLM. Artinya LLM menerima:
- Chunk HTML bersih (tanpa script) — bagian utama prompt
- Seluruh konten inline script — di akhir prompt sebagai referensi

Pendekatan ini memastikan LLM melihat HTML elemen secara bersih (tanpa gangguan kode JS), namun tetap memiliki akses ke definisi fungsi JavaScript untuk identifikasi trigger.

**Catatan penting:** Karena seluruh konten inline script (~100KB+) di-append ke setiap chunk, mayoritas konten yang diterima LLM di setiap iterasi adalah kode script, bukan HTML. Hal ini menyebabkan peningkatan biaya token yang signifikan.

## Hasil

### Ukuran File Input

| File | Baris | Karakter | Estimasi Token | % dari Raw |
|---|---|---|---|---|
| Raw HTML (`scan.html`) | 6,689 | 293,642 | ~73,410 | 100% |
| Cleaned (no-script) | 302 | 15,428 | ~3,857 | 4.5% baris, 5.3% char |
| With-script (inline only) | 3,119 | 133,858 | ~33,464 | 46.6% baris, 45.6% char |

**Catatan:** Cleaning tanpa script menghasilkan 95.5% pengurangan baris. Cleaning dengan script (hanya inline, external library dihapus) hanya mengurangi 53.4% baris — karena konten script inline masih sangat besar.

### Statistik Chunk

| Metrik | No-Script | With-Script-Context |
|---|---|---|
| Jumlah chunk | 2 | 2 |
| Sumber HTML chunk | `cleaned/customer_report_scan.html` | `cleaned/customer_report_scan.html` (sama) |
| Rata-rata baris/chunk | 166 | 166 |
| Rata-rata karakter/chunk | 8,349 | 8,349 |
| Rata-rata token/chunk (HTML) | ~2,087 | ~2,087 |

**Catatan penting:** Kedua pendekatan mengchunk HTML yang **identik** (302 baris cleaned). Pada pendekatan with-script-context, konten script inline (~29,607 tokens) di-append ke **prompt** LLM di setiap chunk, bukan ke HTML. Artinya:

| Yang diterima LLM per chunk | No-Script | With-Script-Context |
|---|---|---|
| HTML chunk | ~2,087 tokens | ~2,087 tokens |
| Script context | 0 tokens | ~29,607 tokens |
| **Total per chunk** | **~2,087 tokens** | **~31,694 tokens** |
| **Total seluruh chunks** | **~4,174 tokens** | **~63,388 tokens** |

**Rasio biaya token: 15x lipat** (bukan 9x seperti estimasi sebelumnya).

### Detail Chunk

| Chunk | Baris | Karakter | Estimasi Token | DOM IDs |
|---|---|---|---|---|
| Chunk 1 (kedua pendekatan) | 1-248 (248 baris) | 10,594 | ~2,648 | 17 |
| Chunk 2 (kedua pendekatan) | 220-302 (83 baris) | 6,104 | ~1,526 | 5 |

### Perbandingan Biaya Ekstraksi

| Metrik | No-Script | With-Script-Context | Rasio |
|---|---|---|---|
| Runtime | 87.6 detik | 208.3 detik | 2.4x |
| DOM coverage | 20/20 (100%) | 20/20 (100%) | — |
| Elemen terekstraksi | 26 | 26 | — |
| Trigger teridentifikasi | **2** | **7** | 3.5x |

### Perbandingan Trigger

**No-Script (2 trigger):**

| # | Elemen Asal | Elemen Tujuan | Perilaku |
|---|---|---|---|
| 1 | `scan__help_icon` | `report_scan_desc` | Klik ikon bantuan → tampilkan/sembunyikan panel panduan |
| 2 | `scan__btn_apply_date` | `data_report` | Klik "Apply" pada date picker → muat data laporan ke tabel |

**With-Script-Context (7 trigger):**

| # | Elemen Asal | Elemen Tujuan | Perilaku | Tipe Aksi |
|---|---|---|---|---|
| 1 | `scan__help_icon` | `report_scan_desc` | Klik ikon bantuan → tampilkan panel panduan | Navigasi |
| 2 | `scan__btn_apply_date` | `data_report` | Klik "Apply" → muat data ke tabel | Navigasi |
| 3 | `report_date` | `abc1` | Ubah rentang tanggal → trigger reload data | Navigasi |
| 4 | `btn_txt` | `scan__download_txt_action` | Klik ikon export → download file .txt | Aksi Langsung |
| 5 | `btn_print` | `scan__print_action` | Klik ikon print → buka dialog print browser | Aksi Langsung |
| 6 | `scan__search_kantor` | `data_report` | Ketik di kolom search Kantor → filter tabel lokal | Filter Lokal |
| 7 | `scan__search_tanggal` | `data_report` | Ketik di kolom search Tanggal → filter tabel lokal | Filter Lokal |

### Analisis Detail Trigger

**5 trigger tambahan dari With-Script-Context dikategorikan sebagai berikut:**

1. **`btn_txt` → download TXT:** Fungsi `download_txt()` di JavaScript membuat file `.txt` secara client-side dari isi textarea `#to_txt` dan mengunduhnya secara langsung. Tidak ada pemanggilan server, tidak ada modal, tidak ada navigasi halaman.

2. **`btn_print` → print:** Fungsi `printDiv('report_container')` mengganti isi `document.body` dengan konten `#report_container`, lalu memanggil `window.print()` yang membuka dialog print bawaan browser. Tidak ada modal, tidak ada navigasi halaman.

3. **`report_date` → abc1:** Merupakan duplikat dari trigger #2 (apply date). Perubahan rentang tanggal pada datepicker juga memicu load data, namun sudah tertangkap oleh `scan__btn_apply_date`.

4. **`scan__search_kantor` → data_report:** Kolom pencarian pada DataTables yang melakukan filter client-side. Ketika pengguna mengetik, tabel langsung difilter tanpa pemanggilan server atau navigasi.

5. **`scan__search_tanggal` → data_report:** Sama seperti #4, filter client-side pada kolomTanggal Absensi.

**Kesimpulan analisis:** Dari 5 trigger tambahan, hanya 2 yang merupakan aksi genuine (download TXT, print). Namun kedua aksi ini bukan navigasi — melainkan aksi langsung (download file, buka dialog print). Sisanya adalah duplikat atau filter lokal DataTables yang tidak termasuk navigasi.

## Kesimpulan

1. **No-script menangkap 100% trigger navigasi inti halaman.** Kedua trigger utama (bantuan dan apply date) teridentifikasi dengan benar tanpa bantuan script context.

2. **With-script-context menambahkan aksi sekunder** (download, print) yang sebelumnya tidak teridentifikasi. Namun aksi-aksi ini bukan navigasi — melainkan aksi langsung yang tidak membuka modal atau berpindah halaman.

3. **Biaya peningkatan tidak sebanding:** With-script-context membutuhkan 2.4x lipat waktu eksekusi dan token yang jauh lebih besar karena konten script (~100KB+) di-append ke setiap chunk. Untuk pipeline 47 halaman, dampak biaya ini sangat signifikan.

4. **Pendekatan no-script sudah memadai** untuk kebutuhan navigasi pengguna dalam HR SaaS admin panel. Trigger navigasi inti (buka panel, muat data) sudah teridentifikasi. Aksi sekunder seperti download dan print merupakan operasi langsung yang tidak memerlukan representasi dalam NKG.

## Argumentasi untuk Sidang

> "Eksperimen ini menguji dampak penyertaan `<script>` tag terhadap akurasi identifikasi trigger. Hasil menunjukkan bahwa tanpa script, pipeline berhasil mengidentifikasi 2 trigger navigasi inti dari halaman uji (100% akurasi untuk navigasi). Dengan penyertaan script context, pipeline mengidentifikasi 7 trigger (+250%), namun 5 di antaranya terdiri dari aksi langsung (download, print), filter lokal DataTables, dan duplikat — bukan navigasi.
>
> Selain itu, pendekatan with-script-context membutuhkan biaya token yang jauh lebih besar. Kedua pendekatan mengchunk HTML yang identik (302 baris cleaned), namun pada with-script-context, seluruh konten script inline (~29,607 tokens) di-append ke prompt di setiap chunk. Total token yang diproses LLM: ~4,174 (no-script) vs ~63,388 (with-script-context) — **15 kali lipat**. Dampaknya: runtime meningkat 2.4x lipat (87.6s → 208.3s).
>
> Untuk pipeline produksi yang memproses 47 halaman, pendekatan tanpa script sudah memadai untuk menangkap trigger navigasi inti dengan biaya yang efisien. Peningkatan akurasi dari script context tidak sebanding dengan biaya token 15x lipat dan latensi 2.4x lipat, mengingat trigger tambahan yang ditemukan bukan merupakan navigasi."

## File Hasil

| File | Deskripsi |
|---|---|
| `output_no_script/customer_report_scan.nkg.json` | Hasil NKG tanpa script (baseline) |
| `output_with_script/customer_report_scan.nkg.json` | Hasil NKG dengan script context |
| `raw/scan.html` | HTML mentah (sebelum cleaning) |
| `cleaned/customer_report_scan.html` | HTML hasil cleaning standar |
| `with_script/customer_report_scan_with_script.html` | HTML hasil cleaning dengan script dipertahankan |
| `generate_with_script.py` | Script untuk generate variant with_script |
