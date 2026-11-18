# Tax Regulation Scraper

Scraper peraturan perpajakan dari [pajak.go.id/id/peraturan](https://www.pajak.go.id/id/peraturan) ke database SQLite, plus viewer lokal untuk menjelajahi hasilnya.

## Data siap pakai

Tidak perlu scraping sendiri. Unduh database dari halaman [Releases (`v1-data`)](https://github.com/alufonso/tax-regulation-scraper/releases/tag/v1-data):

| File | Ukuran (zip / asli) | Isi |
|---|---|---|
| `peraturan.db.gz` | 27 MB / 236 MB | Lengkap, termasuk `isi_html` (tampilan asli dari situs) |
| `peraturan-lite.db.gz` | 8,5 MB / ± 50 MB | Tanpa `isi_html`; isi peraturan tetap ada di `isi_text` |

Isinya 6.314 peraturan dan 2.217 tautan (lampiran PDF, historis, peraturan terkait).

Ekstrak lalu taruh di `data/peraturan.db`:

```bash
gunzip peraturan.db.gz      # di Windows bisa pakai 7-Zip
mkdir -p data && mv peraturan.db data/
```

## Instalasi

```bash
pip install -r requirements.txt
```

## Pemakaian

```bash
python scraper.py           # mode harian: berhenti di halaman pertama yang tidak ada item baru
python scraper.py --full    # telusuri semua halaman (run pertama / melanjutkan run yang terputus)
python view.py              # viewer di http://127.0.0.1:8765 (terbuka otomatis, hanya dari komputer ini)
python tests/test_scraper.py
```

Scraper memberi jeda 1 detik antar request supaya tidak membebani server, dan URL yang sudah tersimpan akan dilewati, jadi aman dijalankan ulang.

`to_sqlite.py` adalah migrasi sekali jalan dari format lama `data/peraturan.jsonl` ke SQLite.

## Struktur database

**`peraturan`**: `nomor`, `jenis_dokumen`, `tanggal` (YYYY-MM-DD), `tahun`, `status`, `judul`, `judul_dokumen`, `kategori` dan `tag` (dipisah `; `), `ada_isi` (1/0), `isi_text`, `isi_html`, `url`

**`tautan`**: `peraturan_id`, `jenis` (`lampiran` | `historis` | `terkait`), `judul`, `url`

Contoh query:

```sql
SELECT nomor, tanggal, judul FROM peraturan
WHERE jenis_dokumen = 'Peraturan Menteri Keuangan' AND tahun = 2025
ORDER BY tanggal DESC;
```

## Catatan

Data bersumber dari situs resmi Direktorat Jenderal Pajak. Selalu cek sumber aslinya (kolom `url`) untuk keperluan resmi.
