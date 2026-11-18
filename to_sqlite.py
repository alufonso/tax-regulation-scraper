"""Migrasi sekali: data/peraturan.jsonl (format lama) -> data/peraturan.db.

Pakai: python to_sqlite.py   (URL yang sudah ada di database dilewati, jadi aman dijalankan ulang)
"""
import json
from pathlib import Path

from scraper import DB, abs_url, open_db, save

SRC = Path(__file__).parent / "data" / "peraturan.jsonl"


def migrate(src=SRC, db=DB):
    con = open_db(db)
    n = 0
    with src.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:  # baris terakhir bisa setengah jadi
                continue
            r["url"] = abs_url(r["url"])
            n += save(con, r)
    con.close()
    return n


if __name__ == "__main__":
    print(f"{migrate()} peraturan baru dimasukkan -> {DB}")
