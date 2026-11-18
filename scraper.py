"""Scraper peraturan pajak.go.id/id/peraturan -> data/peraturan.db (SQLite).

Pakai:
  python scraper.py           # mode harian: berhenti di halaman list pertama yang tidak ada item baru
  python scraper.py --full    # telusuri semua halaman (run pertama / melanjutkan run yang terputus)
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.pajak.go.id"
LIST_URL = BASE + "/id/peraturan"
DB = Path(__file__).parent / "data" / "peraturan.db"
DELAY = 1.0  # detik antar request, jangan bebani server pemerintah

SCHEMA = """
CREATE TABLE IF NOT EXISTS peraturan (
    id            INTEGER PRIMARY KEY,
    nomor         TEXT,
    jenis_dokumen TEXT,
    tanggal       TEXT,      -- YYYY-MM-DD
    tahun         INTEGER,
    status        TEXT,
    judul         TEXT,
    judul_dokumen TEXT,
    kategori      TEXT,      -- dipisah '; '
    tag           TEXT,      -- dipisah '; '
    ada_isi       INTEGER,   -- 1/0
    isi_text      TEXT,
    isi_html      TEXT,
    url           TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS tautan (  -- lampiran PDF, historis, dan peraturan terkait
    peraturan_id INTEGER REFERENCES peraturan(id),
    jenis        TEXT,     -- 'lampiran' | 'historis' | 'terkait'
    judul        TEXT,
    url          TEXT
);
CREATE INDEX IF NOT EXISTS idx_tanggal ON peraturan(tanggal);
CREATE INDEX IF NOT EXISTS idx_jenis ON peraturan(jenis_dokumen);
CREATE INDEX IF NOT EXISTS idx_tautan ON tautan(peraturan_id);
"""


def open_db(path=None):
    path = path or DB
    path.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def save(con, r):
    """Simpan 1 peraturan + tautannya dalam satu transaksi. False kalau URL sudah ada."""
    with con:
        cur = con.execute(
            "INSERT OR IGNORE INTO peraturan (nomor, jenis_dokumen, tanggal, tahun, status, judul, judul_dokumen,"
            " kategori, tag, ada_isi, isi_text, isi_html, url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["nomor"], r["jenis_dokumen"], r["tanggal"], int(r["tanggal"][:4]) if r["tanggal"] else None,
             r["status"], r["judul"], r["judul_dokumen"], "; ".join(r["kategori"]), "; ".join(r["tag"]),
             int(bool(r["isi_text"])), r["isi_text"], r["isi_html"], r["url"]))
        if not cur.rowcount:
            return False
        con.executemany("INSERT INTO tautan VALUES (?,?,?,?)",
                        [(cur.lastrowid, k, x["judul"], x["url"])
                         for k in ("lampiran", "historis", "terkait") for x in r.get(k, [])])
    return True

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (tax-regulation-scraper)"


def get(url, params=None):
    for attempt in range(5):
        try:
            r = session.get(url, params=params, timeout=30)
            r.raise_for_status()
            time.sleep(DELAY)
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException as e:
            wait = 5 * (attempt + 1)
            print(f"  ! {url} gagal ({e}), coba lagi dalam {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"gagal ambil {url}")


def text(el):
    return " ".join(el.get_text(" ").replace("\xad", "").split()) if el else ""  # split() juga membuang \xa0


BLOCKS = ["p", "div", "tr", "li", "ol", "ul", "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"]


def body_text(body):
    """Isi peraturan sebagai teks rapi. Dokumen disusun pakai tabel layout
    ("Menimbang | : | a. | bahwa ..."), jadi 1 baris tabel = 1 baris teks."""
    body = BeautifulSoup(str(body), "html.parser")  # salinan, isi_html tetap utuh
    for tr in body.find_all("tr"):  # newline di sumber HTML antar <td> jangan memecah baris
        for s in tr.find_all(string=True, recursive=False):
            s.replace_with(" ")
    for cell in body.find_all(["td", "th"]):
        if not cell.find("table"):
            cell.string = f" {text(cell)} "
    for br in body.find_all("br"):
        br.replace_with("\n")
    for el in body.find_all(BLOCKS):
        el.insert_before("\n")
        el.insert_after("\n")
    lines = (" ".join(line.split()) for line in body.get_text().replace("\xad", "").splitlines())
    return "\n".join(line for line in lines if line)


def field(article, name):
    """Nilai field Drupal; field__item dipakai agar label ('Tanggal Peraturan') tidak ikut."""
    f = article.select_one(f".field--name-field-{name}")
    if not f:
        return ""
    item = f.select_one(".field__item")
    return text(item or f)


def abs_url(href):
    # situs kadang memberi link "/index.php/id/..." untuk halaman yang sama -> samakan agar tidak tersimpan dobel
    return urljoin(BASE, href).replace("/index.php/", "/", 1)


def links(article, name):
    return [{"judul": text(a), "url": abs_url(a["href"])}
            for a in article.select(f".field--name-field-{name} a[href]")]


def parse_list(soup):
    rows = []
    for row in soup.select(".peraturan-content"):
        # link "Detail" selalu ada; link di nomor hilang kalau nomornya kosong di situs
        a = row.select_one(".views-field-view-node a")
        t = row.select_one(".views-field-field-tanggal-peraturan time")
        rows.append({
            "url": abs_url(a["href"]),
            "nomor": text(row.select_one(".views-field-field-nomor-dokumen")),
            "jenis_dokumen": text(row.select_one(".views-field-field-jenis-dokumen")),
            "tanggal": t["datetime"][:10] if t else "",
            "status": text(row.select_one(".views-field-field-status-peraturan")),
        })
    return rows


def parse_detail(soup, base):
    art = soup.select_one("article")
    body = art.select_one(".field--name-field-body-dalam-html")
    t = art.select_one(".field--name-field-tanggal-peraturan time")
    return {
        **base,
        "judul": text(soup.select_one("h1")),
        "judul_dokumen": " Nomor - ".join(filter(None, [field(art, "jenis-dokumen"), field(art, "nomor-dokumen")])).upper(),
        "jenis_dokumen": field(art, "jenis-dokumen") or base["jenis_dokumen"],
        "nomor": field(art, "nomor-dokumen") or base["nomor"],
        "tanggal": t["datetime"][:10] if t else base["tanggal"],
        "status": field(art, "status-peraturan") or base["status"],
        "kategori": [text(x) for x in art.select(".field--name-field-kategori-peraturan .field__item")],
        "tag": [text(x) for x in art.select(".field--name-field-tag-peraturan .field__item")],
        # hanya link; file PDF lampiran tidak diunduh
        "lampiran": links(art, "lampiran-peraturan"),
        "historis": links(art, "daftar-historis-peraturan"),
        "terkait": links(art, "peraturan-terkait"),
        "isi_text": body_text(body) if body else "",
        "isi_html": body.decode_contents() if body else "",  # simpan html juga, tabel kurs dsb. hilang strukturnya di teks
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="telusuri semua halaman list")
    args = ap.parse_args()
    if sys.platform == "win32":  # cegah Windows sleep selama scraper jalan (otomatis berakhir saat proses selesai)
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

    con = open_db()
    seen = {u for (u,) in con.execute("SELECT url FROM peraturan")}
    print(f"{len(seen)} peraturan sudah tersimpan")

    added = 0
    failed = []
    page = 0
    while True:
        rows = parse_list(get(LIST_URL, {"page": page}))
        if not rows:
            break
        new = [r for r in rows if r["url"] not in seen]
        print(f"halaman {page}: {len(new)} baru dari {len(rows)}")
        # shortcut: mode harian berhenti di halaman tanpa item baru; peraturan lama yang baru diunggah
        # di tengah urutan bisa terlewat -> jalankan --full sesekali (mis. mingguan).
        if not new and not args.full:
            break
        for r in new:
            # satu halaman rusak/hilang jangan menghentikan run berjam-jam; tidak masuk `seen`, jadi --full berikutnya mencoba lagi
            try:
                rec = parse_detail(get(r["url"]), r)
            except Exception as e:
                print(f"  ! dilewati {r['url']}: {e!r}", file=sys.stderr)
                failed.append(r["url"])
                continue
            save(con, rec)  # commit per peraturan: aman kalau dihentikan di tengah jalan
            seen.add(r["url"])
            added += 1
        page += 1
    con.close()
    print(f"selesai: {added} peraturan baru -> {DB}")
    if failed:
        print(f"{len(failed)} gagal (jalankan --full lagi untuk mencoba ulang):", *failed, sep="\n  ")


if __name__ == "__main__":
    main()
