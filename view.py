"""Viewer hasil scrape: baca langsung dari data/peraturan.db.

Pakai: python view.py   -> buka http://127.0.0.1:8765 (otomatis), Ctrl+C untuk berhenti
"""
import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from scraper import DB

PORT = 8765
PAGE_SIZE = 200
LIST_COLS = "id, nomor, judul, jenis_dokumen, tanggal, status, ada_isi"


def db():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)  # read-only: viewer tidak pernah mengubah data
    con.row_factory = sqlite3.Row
    return con


def list_rows(p):
    where, args = [], []
    if q := p.get("q", "").strip():
        cols = ["nomor", "judul"] + (["isi_text"] if p.get("isi") == "1" else [])
        where.append("(" + " OR ".join(f"{c} LIKE ?" for c in cols) + ")")
        args += [f"%{q}%"] * len(cols)
    for key, col in [("jenis", "jenis_dokumen"), ("tahun", "tahun"), ("status", "status")]:
        if p.get(key):
            where.append(f"{col} = ?")
            args.append(p[key])
    if p.get("kat"):
        where.append("('; ' || kategori || '; ') LIKE ?")
        args.append(f"%; {p['kat']}; %")
    if p.get("ada") == "1":
        where.append("ada_isi = 1")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    with db() as con:
        total = con.execute(f"SELECT count(*) FROM peraturan {w}", args).fetchone()[0]
        rows = con.execute(f"SELECT {LIST_COLS} FROM peraturan {w} ORDER BY tanggal DESC, id LIMIT ? OFFSET ?",
                           args + [PAGE_SIZE, int(p.get("offset") or 0)]).fetchall()
    return {"total": total, "rows": [dict(r) for r in rows]}


def meta():
    with db() as con:
        col = lambda sql: [r[0] for r in con.execute(sql) if r[0] not in (None, "")]
        kat = sorted({k for (s,) in con.execute("SELECT kategori FROM peraturan") for k in (s or "").split("; ") if k})
        return {"jenis": col("SELECT DISTINCT jenis_dokumen FROM peraturan ORDER BY 1"),
                "tahun": col("SELECT DISTINCT tahun FROM peraturan ORDER BY 1 DESC"),
                "status": col("SELECT DISTINCT status FROM peraturan ORDER BY 1"),
                "kategori": kat,
                "total": con.execute("SELECT count(*) FROM peraturan").fetchone()[0]}


def item(i):
    with db() as con:
        r = con.execute("SELECT * FROM peraturan WHERE id = ?", (i,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["tautan"] = [dict(t) for t in con.execute("SELECT jenis, judul, url FROM tautan WHERE peraturan_id = ?", (i,))]
        return d


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        p = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(PAGE.encode(), "text/html")
            if u.path == "/api/list":
                return self.json(list_rows(p))
            if u.path == "/api/meta":
                return self.json(meta())
            if u.path == "/api/item":
                d = item(int(p.get("id", 0)))
                return self.json(d) if d else self.send(b"tidak ada", "text/plain", 404)
            self.send(b"not found", "text/plain", 404)
        except (ValueError, sqlite3.Error) as e:
            self.send(str(e).encode(), "text/plain", 400)

    def json(self, obj):
        self.send(json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # jangan banjiri terminal
        pass


PAGE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Peraturan Pajak</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--mute:#5d6b7a;--line:#e3e7ec;--acc:#1f5fa8;--accs:#e3edf8;--sel:#eef4fb}
@media (prefers-color-scheme:dark){:root{--bg:#11161c;--card:#19212a;--ink:#e6ebf0;--mute:#93a1b0;--line:#2a3541;--acc:#7fb0ea;--accs:#22344a;--sel:#1e2b3a}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Segoe UI",sans-serif;display:flex;flex-direction:column}
header{padding:12px 16px;border-bottom:1px solid var(--line);background:var(--card);display:flex;flex-wrap:wrap;gap:8px;align-items:center}
header h1{font-size:1rem;margin:0 12px 0 0}
input,select,button{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
input[type=search]{flex:1;min-width:200px}label{display:flex;gap:4px;align-items:center;color:var(--mute)}
#count{color:var(--mute);margin-left:auto}
main{flex:1;display:grid;grid-template-columns:minmax(300px,420px) 1fr;min-height:0}
#list{overflow-y:auto;border-right:1px solid var(--line);margin:0;padding:0;list-style:none}
#list li{padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer}
#list li:hover{background:var(--sel)}#list li.on{background:var(--accs)}
#list b{display:block;color:var(--acc)}#list .t{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
#list small,.m{color:var(--mute)}.empty{color:#b3261e}
#more{width:100%;padding:10px;border:0;background:none;color:var(--acc);cursor:pointer}
#detail{overflow-y:auto;padding:20px 28px}
#detail h2{font-size:1.15rem;margin:4px 0 8px}
.meta{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:12px 0;font-size:.9rem}.meta dt{color:var(--mute)}.meta dd{margin:0}
.chip{display:inline-block;background:var(--accs);border-radius:99px;padding:1px 9px;margin:0 4px 4px 0;font-size:.8rem}
.tabs{display:flex;gap:6px;margin:16px 0 8px}.tabs button{cursor:pointer}.tabs button[aria-pressed=true]{background:var(--acc);color:#fff;border-color:var(--acc)}
pre{white-space:pre-wrap;word-break:break-word;font:13px/1.65 system-ui,"Segoe UI",sans-serif;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin:0}
iframe{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff;min-height:400px}
mark{background:#ffe58a;color:#000}a{color:var(--acc)}
@media (max-width:760px){main{grid-template-columns:1fr;grid-template-rows:45% 55%}#list{border-right:0;border-bottom:1px solid var(--line)}#detail{padding:16px}}
</style></head><body>
<header>
<h1>Peraturan Pajak</h1>
<input type="search" id="q" placeholder="Cari nomor atau judul…" aria-label="Cari">
<label><input type="checkbox" id="isi"> cari di isi juga</label>
<select id="jenis" aria-label="Jenis dokumen"><option value="">Semua jenis</option></select>
<select id="tahun" aria-label="Tahun"><option value="">Semua tahun</option></select>
<select id="status" aria-label="Status"><option value="">Semua status</option></select>
<select id="kat" aria-label="Kategori"><option value="">Semua kategori</option></select>
<label><input type="checkbox" id="ada"> hanya yang ada isinya</label>
<span id="count"></span>
</header>
<main><ul id="list"></ul><section id="detail"><p class="m">Pilih peraturan di sebelah kiri.</p></section></main>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IFRAME_CSS = '<base href="https://www.pajak.go.id/" target="_blank"><style>body{font:14px/1.5 system-ui,"Segoe UI",sans-serif;margin:16px;color:#111}'
  + 'table{border-collapse:collapse;max-width:100%}td,th{padding:2px 6px;vertical-align:top}table table td,table table th{border:1px solid #bbb}img{max-width:100%}</style>';
let total = 0, offset = 0, total_all = 0, seq = 0;

fetch('/api/meta').then(r => r.json()).then(m => {
  m.jenis.forEach(v => $('jenis').add(new Option(v, v))); m.tahun.forEach(v => $('tahun').add(new Option(v, v)));
  m.status.forEach(v => $('status').add(new Option(v, v))); m.kategori.forEach(v => $('kat').add(new Option(v, v)));
  total_all = m.total; load(true);
});
function params(){
  return new URLSearchParams({q: $('q').value, isi: $('isi').checked ? 1 : 0, jenis: $('jenis').value, tahun: $('tahun').value,
    status: $('status').value, kat: $('kat').value, ada: $('ada').checked ? 1 : 0, offset});
}
async function load(reset){
  if (reset) { offset = 0; $('list').innerHTML = ''; }
  const my = ++seq, d = await (await fetch('/api/list?' + params())).json();
  if (my !== seq) return;  // hasil pencarian lama yang telat datang dibuang
  total = d.total; $('count').textContent = total.toLocaleString('id') + ' dari ' + total_all.toLocaleString('id') + ' peraturan';
  $('more')?.remove();
  d.rows.forEach(r => {
    const li = document.createElement('li');
    li.innerHTML = '<b>' + esc(r.nomor || '(tanpa nomor)') + '</b><span class="t">' + esc(r.judul) + '</span><small>'
      + esc(r.jenis_dokumen) + ' · ' + esc(r.tanggal) + ' · ' + esc(r.status) + (r.ada_isi ? '' : ' · <span class="empty">tanpa isi</span>') + '</small>';
    li.onclick = () => { document.querySelector('#list li.on')?.classList.remove('on'); li.classList.add('on'); show(r.id); };
    $('list').appendChild(li);
  });
  offset += d.rows.length;
  if (offset < total) { const b = document.createElement('button'); b.id = 'more'; b.textContent = 'Tampilkan lebih banyak (' + (total - offset) + ' lagi)'; b.onclick = () => load(false); $('list').appendChild(b); }
}
const links = (t, jenis) => t.filter(x => x.jenis === jenis).map(x => '<a href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.judul) + '</a>').join('<br>') || '–';
const chips = s => (s || '').split('; ').filter(Boolean).map(x => '<span class="chip">' + esc(x) + '</span>').join('') || '–';
async function show(id){
  const r = await (await fetch('/api/item?id=' + id)).json();
  const q = $('q').value.trim();
  let isi = esc(r.isi_text);
  if (q && $('isi').checked) isi = isi.replace(new RegExp(esc(q).replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'gi'), m => '<mark>' + m + '</mark>');
  $('detail').innerHTML = '<div class="m">' + esc(r.judul_dokumen) + '</div><h2>' + esc(r.judul) + '</h2>'
    + '<dl class="meta"><dt>Jenis</dt><dd>' + esc(r.jenis_dokumen || '–') + '</dd><dt>Nomor</dt><dd>' + esc(r.nomor || '–') + '</dd>'
    + '<dt>Tanggal</dt><dd>' + esc(r.tanggal || '–') + '</dd><dt>Status</dt><dd>' + esc(r.status || '–') + '</dd>'
    + '<dt>Kategori</dt><dd>' + chips(r.kategori) + '</dd><dt>Tag</dt><dd>' + chips(r.tag) + '</dd>'
    + '<dt>Lampiran</dt><dd>' + links(r.tautan, 'lampiran') + '</dd><dt>Historis</dt><dd>' + links(r.tautan, 'historis') + '</dd>'
    + '<dt>Terkait</dt><dd>' + links(r.tautan, 'terkait') + '</dd>'
    + '<dt>Sumber</dt><dd><a href="' + esc(r.url) + '" target="_blank" rel="noopener">buka di pajak.go.id</a></dd></dl>'
    + (r.ada_isi
      ? '<div class="tabs"><button id="tAsli" aria-pressed="true">Tampilan asli (dengan tabel)</button><button id="tTeks" aria-pressed="false">Teks</button></div>'
        + '<iframe id="asli" sandbox="allow-same-origin allow-popups" title="Isi peraturan"></iframe><pre id="teks" hidden>' + isi + '</pre>'
      : '<p class="empty">Situs tidak memuat isi untuk peraturan ini.</p>');
  $('detail').scrollTop = 0;
  if (!r.ada_isi) return;
  const f = $('asli');  // sandbox tanpa allow-scripts: HTML dari situs ditampilkan tapi skripnya tidak jalan
  f.onload = () => { f.style.height = f.contentDocument.documentElement.scrollHeight + 20 + 'px'; };
  f.srcdoc = IFRAME_CSS + r.isi_html;
  const tab = asli => { $('tAsli').setAttribute('aria-pressed', asli); $('tTeks').setAttribute('aria-pressed', !asli); f.hidden = !asli; $('teks').hidden = asli; };
  $('tAsli').onclick = () => tab(true); $('tTeks').onclick = () => tab(false);
  if (q && $('isi').checked) tab(false);  // sedang mencari di isi -> tampilkan teks yang di-highlight
}
let timer; $('q').oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(true), 300); };
['isi','jenis','tahun','status','kat','ada'].forEach(id => $(id).onchange = () => load(true));
</script></body></html>"""


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)  # hanya bisa diakses dari laptop ini
    print(f"Viewer: http://127.0.0.1:{PORT}  (Ctrl+C untuk berhenti)")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
