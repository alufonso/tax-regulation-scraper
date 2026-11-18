"""Cek parser terhadap HTML asli yang disimpan. Jalankan: python tests/test_scraper.py"""
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import parse_detail, parse_list

FX = Path(__file__).parent / "fixtures"


def soup(name):
    return BeautifulSoup((FX / name).read_text(encoding="utf-8"), "html.parser")


rows = parse_list(soup("list.html"))
assert len(rows) == 5, rows
assert rows[0]["nomor"] == "49/MK/EF.2/2026"
assert rows[0]["jenis_dokumen"] == "Keputusan Menteri Keuangan"
assert rows[0]["tanggal"] == "2026-10-13" and rows[0]["status"] == "Aktif"
assert rows[3]["nomor"] == "71 TAHUN 2026"

empty_row = BeautifulSoup(
    '<div class="peraturan-content"><div class="views-field-field-nomor-dokumen"><h3></h3></div>'
    '<span class="views-field-field-tanggal-peraturan"><strong></strong></span>'
    '<span class="views-field-view-node"><a href="/id/peraturan/x">Detail</a></span></div>', "html.parser")
from scraper import abs_url
assert abs_url("/index.php/id/peraturan/x") == abs_url("/id/peraturan/x") == "https://www.pajak.go.id/id/peraturan/x"
assert parse_list(empty_row) == [{"url": "https://www.pajak.go.id/id/peraturan/x", "nomor": "",
                                  "jenis_dokumen": "", "tanggal": "", "status": ""}]

d = parse_detail(soup("d1.html"), rows[0])
assert d["judul"].startswith("NILAI KURS SEBAGAI DASAR PELUNASAN"), d["judul"]
assert d["judul_dokumen"] == "KEPUTUSAN MENTERI KEUANGAN NOMOR - 49/MK/EF.2/2026"
assert d["tanggal"] == "2026-10-13" and d["status"] == "Aktif"
assert d["kategori"] == ["PPh - Pajak Penghasilan", "PPN - Pajak Pertambahan Nilai"], d["kategori"]
assert "MEMUTUSKAN" in d["isi_text"] and "<table" in d["isi_html"]
assert "\nMengingat : 1. Undang-Undang Nomor 7 Tahun 1983" in d["isi_text"]
assert "\n14. Rp. 8,51 untuk kyat Myanmar (MMK) 1,-\n" in d["isi_text"]
assert "\xa0" not in d["isi_text"]
assert d["lampiran"] == [] and d["historis"] == []

art = BeautifulSoup(
    '<h1>X</h1><article><div class="field--name-field-lampiran-peraturan"><a href="https://www.pajak.go.id/f/L.pdf">L.pdf</a></div>'
    '<div class="field--name-field-daftar-historis-peraturan"><a href="/id/peraturan/lama">PERATURAN\nLAMA</a></div></article>',
    "html.parser")
d2 = parse_detail(art, {"url": "x", "nomor": "", "jenis_dokumen": "", "tanggal": "", "status": ""})
assert d2["terkait"] == [] and d2["judul_dokumen"] == ""
assert d2["lampiran"] == [{"judul": "L.pdf", "url": "https://www.pajak.go.id/f/L.pdf"}], d2["lampiran"]
assert d2["historis"] == [{"judul": "PERATURAN LAMA", "url": "https://www.pajak.go.id/id/peraturan/lama"}]

base = {"url": "x", "nomor": "", "jenis_dokumen": "", "tanggal": "", "status": ""}
old = parse_detail(soup("d2.html"), base)
assert old["nomor"] == "436/KMK.05/1983" and old["tanggal"] == "1983-06-28", old
assert old["kategori"] == ["PPh - Pajak Penghasilan", "PPN - Pajak Pertambahan Nilai", "Lainnya"], old["kategori"]
assert "3001-PPN Umum" in old["tag"] and old["isi_text"] == ""

# main(): detail yang gagal dilewati, sisanya tetap tersimpan, dan dicoba lagi di run berikutnya
import json
import tempfile

import scraper

detail = soup("d1.html")
broken = {rows[1]["url"]}


def fake_get(url, params=None):
    if url == scraper.LIST_URL:
        return soup("list.html") if params["page"] == 0 else BeautifulSoup("", "html.parser")
    if url in broken:
        raise RuntimeError("gagal ambil")
    return detail


import sqlite3

tmp = Path(tempfile.mkdtemp())
scraper.get = fake_get
scraper.DB = tmp / "test.db"
sys.argv = ["scraper.py"]


def saved_urls():
    with sqlite3.connect(scraper.DB) as c:
        return [u for (u,) in c.execute("select url from peraturan")]


scraper.main()
assert len(saved_urls()) == 4 and rows[1]["url"] not in saved_urls()

broken.clear()
scraper.main()  # mode harian: item yang gagal masih dianggap baru, jadi diambil
assert len(saved_urls()) == 5 and rows[1]["url"] in saved_urls()

con = sqlite3.connect(scraper.DB)
assert con.execute("select nomor, tahun, kategori, ada_isi from peraturan where url=?", (rows[0]["url"],)).fetchone() == \
    ("49/MK/EF.2/2026", 2026, "PPh - Pajak Penghasilan; PPN - Pajak Pertambahan Nilai", 1)
con.close()

# save(): tautan masuk tabel sendiri, URL dobel ditolak
con = scraper.open_db(tmp / "save.db")
assert scraper.save(con, d2) and not scraper.save(con, d2)
assert con.execute("select jenis, judul from tautan order by jenis").fetchall() == \
    [("historis", "PERATURAN LAMA"), ("lampiran", "L.pdf")]
con.close()

# to_sqlite: migrasi JSONL lama, baris rusak dilewati, URL /index.php/ disamakan
import to_sqlite

src = tmp / "lama.jsonl"
src.write_text(json.dumps({**d, "url": d["url"].replace("/id/", "/index.php/id/")}) + "\n" + '{"rusak', encoding="utf-8")
assert to_sqlite.migrate(src, scraper.DB) == 0  # sudah ada (URL sama setelah disamakan)
assert to_sqlite.migrate(src, tmp / "baru.db") == 1

# view: query list/filter/item langsung dari database
import view

view.DB = scraper.DB
assert view.list_rows({})["total"] == 5
assert view.list_rows({"q": "49/MK"})["total"] == 5 and view.list_rows({"q": "71 TAHUN"})["total"] == 0
assert view.list_rows({"tahun": "2026", "ada": "1"})["total"] == 5 and view.list_rows({"tahun": "1983"})["total"] == 0
assert view.list_rows({"kat": "PPN - Pajak Pertambahan Nilai"})["total"] == 5
assert view.list_rows({"q": "MEMUTUSKAN", "isi": "1"})["total"] == 5
assert view.list_rows({"q": "MEMUTUSKAN"})["total"] == 0
assert view.item(1)["isi_html"].startswith("<table") and view.item(999) is None
assert "Keputusan Menteri Keuangan" in view.meta()["jenis"]

print("OK")
