#!/usr/bin/env python3
"""Vault Memory dashboard: a local, read-only view of the session records in the vault.

It reads the vault path and the frontmatter parser from vault_memory.py, so the numbers come
from the same files as `vm report`.

Run:     python3 server.py [--port 4747] [--open]      (or: vm dashboard)
Demo:    python3 server.py --demo [--lang tr]          (synthetic data, no vault needed)
Env:     VM_DASHBOARD_HOST, VM_DASHBOARD_PORT, VAULT_MEMORY_HOME
"""
import argparse
import errno
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
VM_HOME = Path(os.environ.get("VAULT_MEMORY_HOME", str(Path.home() / ".vault-memory")))
NONE_ID = "_none"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

_vm = None


def vm_candidates():
    return [HERE.parent / "bin" / "vault_memory.py", VM_HOME / "bin" / "vault_memory.py"]


def get_vm():
    """Imports vault_memory.py once: next to this folder first, then $VAULT_MEMORY_HOME/bin."""
    global _vm
    if _vm is None:
        path = next((p for p in vm_candidates() if p.exists()), None)
        if path is None:
            sys.exit("vault_memory.py not found (looked in: %s). Install Vault Memory first, or run with --demo."
                     % ", ".join(str(p) for p in vm_candidates()))
        spec = importlib.util.spec_from_file_location("vault_memory", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.__dashboard_path__ = path
        _vm = mod
    return _vm


# ------------------------------------------------------------------ session file parsing

HEAD_RE = re.compile(r"^## (\d{1,2}):(\d{2}) — (.+?) \((\d+) (?:min|dk) · ([^)]+)\)\s*$")
SHORT_RE = re.compile(r"^- (\d\d):(\d\d) · (\d+) (?:min|dk) · ([^·]+?) · (.*)$")
SECTION_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
SECTIONS = {
    "request": "request", "done": "done", "decisions": "decisions", "open items": "open",
    "istek": "request", "i̇stek": "request", "yapılanlar": "done", "kararlar": "decisions", "açık işler": "open",
}


def section_key(label):
    return SECTIONS.get(label.strip().lower(), "other")


def new_session(start, title, minutes, tool):
    return {"start": start, "title": title, "minutes": minutes, "tool": tool,
            "request": "", "done": [], "decisions": [], "open": [], "other": []}


def parse_sessions(body):
    """Splits the body of a daily session file into entries (headed sections and short lines)."""
    out, cur, sec = [], None, None
    for line in body.splitlines():
        m = HEAD_RE.match(line)
        if m:
            cur = new_session("%02d:%s" % (int(m.group(1)), m.group(2)), m.group(3).strip(), int(m.group(4)),
                              m.group(5).strip())
            out.append(cur)
            sec = None
            continue
        s = SHORT_RE.match(line)
        if s:
            out.append(new_session("%s:%s" % (s.group(1), s.group(2)), s.group(5).strip() or "—", int(s.group(3)),
                                   s.group(4).strip()))
            cur, sec = None, None
            continue
        if cur is None:
            continue
        if line.startswith("## "):
            cur, sec = None, None
            continue
        s = SECTION_RE.match(line)
        if s:
            sec = section_key(s.group(1))
            rest = s.group(2).strip()
            if rest:
                if sec == "request":
                    cur["request"] = rest
                else:
                    cur[sec].append(rest if sec != "other" else "%s: %s" % (s.group(1).strip(), rest))
            elif sec == "other":
                cur["other"].append(s.group(1).strip())
            continue
        text = line.strip()
        if not text or sec is None:
            continue
        if sec == "request":
            cur["request"] = (cur["request"] + " " + text).strip()
        elif text.startswith(("- ", "* ")):
            cur[sec].append(text[2:].strip())
        elif cur[sec]:
            cur[sec][-1] += " " + text
        else:
            cur[sec].append(text)
    return out


def clean_project(value):
    return re.sub(r"[\[\]\"]", "", value or "").strip() or NONE_ID


def read_projects(vm, vault):
    projects = {}
    base = vault / "02-Projects"
    if not base.is_dir():
        return projects
    for d in sorted(base.iterdir()):
        page = d / (d.name + ".md")
        if not (d.is_dir() and d.name.startswith("PRJ-") and page.exists()):
            continue
        fm, _ = vm.read_page(page)
        projects[d.name] = {
            "id": d.name,
            "title": vm.fm_str(fm, "title") or d.name,
            "description": "" if vm.fm_str(fm, "description").startswith("TODO") else vm.fm_str(fm, "description"),
            "status": vm.fm_str(fm, "status"),
            "updated": vm.fm_str(fm, "updated"),
            "repos": vm.fm_list(fm, "repos"),
        }
    return projects


def session_paths(vault):
    return sorted(list((vault / "02-Projects").glob("PRJ-*/sessions/*.md"))
                  + list((vault / "05-Raw" / "sessions").rglob("*.md")))


def blank_project(pid):
    return {"id": pid, "title": "" if pid == NONE_ID else pid, "description": "", "status": "", "updated": "", "repos": []}


def build_data(vm, cfg):
    vault = Path(cfg["vault"])
    projects = read_projects(vm, vault)
    days, sessions, warnings = [], [], []
    for p in session_paths(vault):
        fm, body = vm.read_page(p)
        if vm.fm_str(fm, "type") != "session":
            continue
        date_s = vm.fm_str(fm, "date")
        project = clean_project(vm.fm_str(fm, "project"))
        machine = vm.fm_str(fm, "machine") or "?"
        try:
            fm_minutes = int(float(vm.fm_str(fm, "minutes", "0")))
            fm_sessions = int(float(vm.fm_str(fm, "sessions", "0")))
        except ValueError:
            fm_minutes, fm_sessions = 0, 0
        rel = p.relative_to(vault).as_posix()
        parsed = parse_sessions(body)
        if not parsed and fm_minutes:
            parsed = [new_session("", "", fm_minutes, ", ".join(vm.fm_list(fm, "tools")) or "?")]
        total = sum(s["minutes"] for s in parsed)
        if parsed and total != fm_minutes:
            # Entry headings are rounded per session; keep the file total equal to `vm report`
            # by moving the difference onto the longest entry.
            diff = fm_minutes - total
            longest = max(parsed, key=lambda s: s["minutes"])
            longest["minutes"] = max(0, longest["minutes"] + diff)
            if abs(diff) > 15:
                warnings.append({"file": rel, "entries": total, "frontmatter": fm_minutes})
        days.append({"date": date_s, "project": project, "machine": machine,
                     "minutes": fm_minutes, "sessions": fm_sessions, "file": rel})
        for i, s in enumerate(parsed):
            s.update({"id": "%s#%d" % (rel, i), "date": date_s, "project": project, "machine": machine, "file": rel})
            sessions.append(s)
        if project not in projects:
            projects[project] = blank_project(project)
    sessions.sort(key=lambda s: (s["date"], s["start"]), reverse=True)
    return {"vault": str(vault), "vault_name": vault.name, "lang": cfg.get("language") or "en",
            "generated": datetime.now().isoformat(timespec="seconds"),
            "gap_cap_minutes": cfg.get("gap_cap_minutes", 5),
            "projects": projects, "days": days, "sessions": sessions, "warnings": warnings}


# ------------------------------------------------------------------ demo data

DEMO_PROJECTS = [
    # id, weight, status, {lang: (title, description)}
    ("acme-api", 9, "active", {
        "en": ("Acme API", "REST and webhook backend for the Acme ordering app, Python and Postgres."),
        "tr": ("Acme API", "Acme sipariş uygulamasının REST ve webhook arka ucu; Python ve Postgres."),
    }),
    ("mobile-app", 7, "active", {
        "en": ("Mobile app", "SwiftUI client for iPhone and iPad with offline sync."),
        "tr": ("Mobil uygulama", "Çevrimdışı eşitlemeli iPhone ve iPad SwiftUI istemcisi."),
    }),
    ("data-pipeline", 5, "active", {
        "en": ("Data pipeline", "Nightly ETL that loads events into the warehouse and builds reports."),
        "tr": ("Veri hattı", "Olayları ambara yükleyip rapor üreten gece ETL işi."),
    }),
    ("docs-site", 3, "active", {
        "en": ("Docs site", "Static documentation site with versioned guides and API reference."),
        "tr": ("Doküman sitesi", "Sürümlü rehberler ve API referansı içeren statik doküman sitesi."),
    }),
    ("landing-page", 2, "paused", {
        "en": ("Landing page", "Marketing page with pricing, waitlist form and analytics."),
        "tr": ("Tanıtım sayfası", "Fiyatlandırma, bekleme listesi formu ve analitik içeren tanıtım sayfası."),
    }),
    ("infra", 2, "active", {
        "en": ("Infrastructure", "Server setup, backups, CI runners and monitoring."),
        "tr": ("Altyapı", "Sunucu kurulumu, yedekler, CI çalıştırıcıları ve izleme."),
    }),
]
DEMO_PROJECT_STATUS_TR = {"active": "aktif", "paused": "beklemede", "done": "bitti"}

DEMO_WORK = {
    "en": {
        "acme-api": [
            ("Webhook retries with backoff", "Make failed webhooks retry instead of dropping them.",
             ["Added an exponential backoff queue for webhook delivery", "Covered retry limits with tests"],
             ["Retries stop after 6 attempts; failures go to a dead-letter table"], ["Expose the dead-letter table in admin"]),
            ("Order export endpoint", "Add a CSV export for orders filtered by date.",
             ["New `/orders/export` endpoint streaming CSV", "Pagination-free streaming to keep memory flat"],
             [], ["Add a rate limit for exports"]),
            ("Fix N+1 queries in order list", "The order list is slow for large accounts.",
             ["Replaced per-row lookups with a joined query", "p95 dropped from 1.8 s to 220 ms"],
             ["Keep the ORM, add explicit prefetch helpers"], []),
            ("Auth token rotation", "Rotate API tokens without downtime.",
             ["Two active signing keys during rotation", "Migration and docs for the new key id header"],
             ["Old key stays valid for 24 h after rotation"], ["Schedule the first production rotation"]),
        ],
        "mobile-app": [
            ("Offline sync conflict handling", "Edits made offline overwrite newer server changes.",
             ["Added per-field timestamps and a merge step", "UI badge for items with conflicts"],
             ["Last writer wins per field, not per record"], ["Test with two devices on a flaky network"]),
            ("Onboarding screens", "Build the three onboarding screens from the design.",
             ["Paged onboarding with skip and progress dots", "Dynamic Type and VoiceOver labels"],
             [], ["Localize onboarding copy"]),
            ("Crash on iPad split view", "App crashes when resized in split view.",
             ["Fixed a layout loop in the sidebar", "Added a UI test for compact width"], [], []),
        ],
        "data-pipeline": [
            ("Backfill missing events", "Two days of events never reached the warehouse.",
             ["Replayed raw files for the missing window", "Added a row-count check after each load"],
             ["Loads are idempotent by event id"], ["Alert when daily counts drop by more than 30%"]),
            ("Weekly revenue report", "Automate the weekly revenue summary.",
             ["SQL model for weekly revenue by plan", "Report emailed every Monday 08:00"], [], []),
        ],
        "docs-site": [
            ("Versioned API reference", "Readers need docs for older API versions.",
             ["Version switcher in the header", "Build keeps the last three major versions"], [], ["Redirect old URLs"]),
            ("Search across guides", "Add full-text search to the docs.",
             ["Client-side search index generated at build time"], ["No external search service"], []),
        ],
        "landing-page": [
            ("Pricing table refresh", "Update plans and add yearly pricing.",
             ["Monthly/yearly toggle", "Updated plan limits"], [], ["Check copy with the team"]),
        ],
        "infra": [
            ("Nightly database backups", "Backups were manual.",
             ["Cron job with encrypted uploads to object storage", "Restore drill documented"],
             ["Keep 14 daily and 8 weekly backups"], []),
            ("CI runner upgrade", "CI builds are slow and flaky.",
             ["Moved builds to a larger runner with cache", "Build time from 14 to 6 minutes"], [], []),
        ],
        NONE_ID: [
            ("Shell alias cleanup", "Tidy up dotfiles.", ["Removed unused aliases", "Documented the rest"], [], []),
            ("Question about regex lookbehind", "How do lookbehinds work in Python?", ["Explained fixed-width lookbehind"], [], []),
            ("Draft blog post outline", "Outline a post about agent memory.", ["Outline with five sections"], [], ["Write the intro"]),
        ],
    },
    "tr": {
        "acme-api": [
            ("Webhook yeniden denemesi ve bekleme", "Başarısız webhook'lar düşmesin, yeniden denensin.",
             ["Webhook gönderimi için artan beklemeli kuyruk eklendi", "Deneme sınırı testlerle kapsandı"],
             ["6 denemeden sonra durur; başarısızlar ayrı tabloya düşer"], ["Başarısızlar tablosunu yönetim paneline ekle"]),
            ("Sipariş dışa aktarma ucu", "Tarihe göre süzülmüş siparişler CSV olarak indirilebilsin.",
             ["Akış halinde CSV dönen `/orders/export` ucu", "Bellek sabit kalsın diye sayfalamasız akış"],
             [], ["Dışa aktarmaya hız sınırı ekle"]),
            ("Sipariş listesinde N+1 sorgu düzeltmesi", "Büyük hesaplarda sipariş listesi yavaş.",
             ["Satır başı sorgular tek birleşik sorguya indirildi", "p95 1,8 sn'den 220 ms'ye düştü"],
             ["ORM kalıyor, açık ön yükleme yardımcıları eklendi"], []),
            ("Anahtar döndürme", "API anahtarları kesintisiz döndürülebilsin.",
             ["Döndürme sırasında iki imza anahtarı geçerli", "Yeni anahtar başlığı için geçiş ve doküman"],
             ["Eski anahtar döndürmeden sonra 24 saat geçerli"], ["İlk canlı döndürmeyi planla"]),
        ],
        "mobile-app": [
            ("Çevrimdışı eşitleme çakışmaları", "Çevrimdışı düzenlemeler sunucudaki yeni değişiklikleri eziyor.",
             ["Alan bazında zaman damgası ve birleştirme adımı", "Çakışan öğeler için arayüz rozeti"],
             ["Kayıt değil alan bazında son yazan kazanır"], ["İki cihazla kötü ağda dene"]),
            ("Karşılama ekranları", "Tasarımdaki üç karşılama ekranını yap.",
             ["Atla düğmeli, ilerleme noktalı sayfalı karşılama", "Dynamic Type ve VoiceOver etiketleri"],
             [], ["Karşılama metinlerini çevir"]),
            ("iPad bölünmüş ekranda çökme", "Bölünmüş ekranda boyut değişince uygulama çöküyor.",
             ["Kenar çubuğundaki yerleşim döngüsü düzeltildi", "Dar genişlik için arayüz testi eklendi"], [], []),
        ],
        "data-pipeline": [
            ("Eksik olayların geri doldurulması", "İki günlük olay ambara hiç ulaşmamış.",
             ["Eksik aralığın ham dosyaları yeniden işlendi", "Her yüklemeden sonra satır sayısı kontrolü"],
             ["Yüklemeler olay kimliğiyle tekrarlanabilir"], ["Günlük sayı %30'dan fazla düşerse uyar"]),
            ("Haftalık gelir raporu", "Haftalık gelir özeti elle hazırlanmasın.",
             ["Plana göre haftalık gelir SQL modeli", "Rapor her pazartesi 08:00'de e-postayla gider"], [], []),
        ],
        "docs-site": [
            ("Sürümlü API referansı", "Okurlar eski API sürümlerinin dokümanına ihtiyaç duyuyor.",
             ["Başlıkta sürüm seçici", "Son üç ana sürüm derlemede tutuluyor"], [], ["Eski adresleri yönlendir"]),
            ("Rehberlerde arama", "Dokümana tam metin arama ekle.",
             ["Derlemede üretilen istemci tarafı arama dizini"], ["Dış arama servisi kullanılmayacak"], []),
        ],
        "landing-page": [
            ("Fiyat tablosu yenilemesi", "Planları güncelle, yıllık fiyat ekle.",
             ["Aylık/yıllık geçişi", "Plan sınırları güncellendi"], [], ["Metni ekiple kontrol et"]),
        ],
        "infra": [
            ("Gece veritabanı yedekleri", "Yedekler elle alınıyordu.",
             ["Nesne depolamaya şifreli yükleyen zamanlanmış iş", "Geri yükleme tatbikatı belgelendi"],
             ["14 günlük ve 8 haftalık yedek tutulur"], []),
            ("CI çalıştırıcı yükseltmesi", "CI derlemeleri yavaş ve kararsız.",
             ["Derlemeler önbellekli daha büyük çalıştırıcıya taşındı", "Derleme süresi 14 dakikadan 6 dakikaya indi"], [], []),
        ],
        NONE_ID: [
            ("Kabuk takma adlarının temizliği", "Dotfile'ları toparla.", ["Kullanılmayan takma adlar silindi", "Kalanlar belgelendi"], [], []),
            ("Regex lookbehind sorusu", "Python'da lookbehind nasıl çalışır?", ["Sabit genişlikli lookbehind anlatıldı"], [], []),
            ("Blog yazısı taslağı", "Ajan hafızası üzerine yazı taslağı.", ["Beş bölümlü taslak çıkarıldı"], [], ["Girişi yaz"]),
        ],
    },
}


def build_demo(lang="en", days=42, seed=7):
    """Deterministic synthetic data (fictional projects) for screenshots and trying the UI."""
    lang = "tr" if lang == "tr" else "en"
    rng = random.Random(seed)
    today = date.today()
    projects = {}
    weights = []
    for pid, weight, status, names in DEMO_PROJECTS:
        title, desc = names[lang]
        full = "PRJ-" + pid
        projects[full] = {"id": full, "title": title, "description": desc,
                          "status": DEMO_PROJECT_STATUS_TR[status] if lang == "tr" else status,
                          "updated": str(today - timedelta(days=rng.randint(0, 6))),
                          "repos": ["github.com/example/%s" % pid]}
        weights.append((full, weight))
    projects[NONE_ID] = blank_project(NONE_ID)
    weights.append((NONE_ID, 1))
    general = "genel" if lang == "tr" else "general"
    sessions, day_rows = [], {}
    for back in range(days - 1, -1, -1):
        d = today - timedelta(days=back)
        wd = d.weekday()
        n = rng.choice([0, 1, 1, 2]) if wd >= 5 else rng.choice([1, 2, 3, 3, 4, 4])
        if back == 0:
            n = min(n, 2)
        starts = sorted(rng.choice([9, 10, 10, 11, 13, 14, 14, 15, 16, 17, 20, 21, 22]) * 60 + rng.randrange(0, 60, 5)
                        for _ in range(n))
        for start in starts:
            pid = rng.choices([w[0] for w in weights], [w[1] for w in weights])[0]
            key = pid[4:] if pid != NONE_ID else NONE_ID
            title, request, done, decisions, open_ = rng.choice(DEMO_WORK[lang][key])
            minutes = max(3, min(300, int(rng.lognormvariate(3.95, 0.7))))
            if pid == NONE_ID:
                minutes = min(minutes, 40)
            machine = "server" if rng.random() < 0.18 else "laptop"
            tool = "codex" if rng.random() < 0.22 else "claude-code"
            slug = key if pid != NONE_ID else general
            if pid == NONE_ID:
                rel = "05-Raw/sessions/%s/%s/%s %s %s.md" % (d.year, str(d)[:7], d, general, machine)
            else:
                rel = "02-Projects/%s/sessions/%s %s %s.md" % (pid, d, slug, machine)
            short = minutes < 6 and rng.random() < 0.5
            s = new_session("%02d:%02d" % (start // 60, start % 60),
                            ("kısa oturum" if lang == "tr" else "short session") if short else title, minutes, tool)
            if not short:
                s.update({"request": request, "done": list(done), "decisions": list(decisions), "open": list(open_)})
            s.update({"date": str(d), "project": pid, "machine": machine, "file": rel})
            sessions.append(s)
            row = day_rows.setdefault((str(d), pid, machine), {"date": str(d), "project": pid, "machine": machine,
                                                                 "minutes": 0, "sessions": 0, "file": rel})
            row["minutes"] += minutes
            row["sessions"] += 1
    sessions.sort(key=lambda s: (s["date"], s["start"]), reverse=True)
    for i, s in enumerate(sessions):
        s["id"] = "%s#%d" % (s["file"], i)
    return {"vault": "demo", "vault_name": "Demo", "lang": lang, "demo": True,
            "generated": datetime.now().isoformat(timespec="seconds"), "gap_cap_minutes": 5,
            "projects": projects, "days": list(day_rows.values()), "sessions": sessions, "warnings": []}


def demo_status(lang):
    now = datetime.now()
    msg = "işçi bitti: 2 aday, 2 commit, eşitleme: ok" if lang == "tr" else "worker done: 2 candidates, 2 commits, sync: ok"
    return {"vault": "demo", "machine": "laptop", "language": lang, "pending": 1, "ready": 0, "backfill": 0,
            "alert": "", "last_log": "%s %s" % ((now - timedelta(minutes=7)).strftime("%Y-%m-%d %H:%M:%S"), msg),
            "capture": False, "process_remote": False, "demo": True}


# ------------------------------------------------------------------ providers

class VaultSource:
    """Serves the vault; rebuilds the payload only when a session or project file changes."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.key = None
        self.payload = None
        self.status = None
        self.status_at = 0.0

    def data(self):
        vm = get_vm()
        cfg = vm.load_config()
        vault = Path(cfg["vault"])
        files = session_paths(vault) + list((vault / "02-Projects").glob("PRJ-*/PRJ-*.md"))
        stamps = []
        for f in files:
            try:
                stamps.append((str(f), f.stat().st_mtime_ns))
            except OSError:
                pass
        key = (str(vault), cfg.get("language"), tuple(stamps))
        with self.lock:
            if key != self.key:
                self.payload = json.dumps(build_data(vm, cfg), ensure_ascii=False).encode("utf-8")
                self.key = key
            return self.payload

    def status_info(self):
        # One status computation at a time; concurrent requests wait and reuse the result.
        with self.status_lock:
            if self.status is not None and time.time() - self.status_at < 30:
                return self.status
            try:
                vm = get_vm()
                cfg = vm.load_config()
                fn = getattr(vm, "status_info", None)
                if fn is not None:
                    info = fn(cfg)
                else:
                    bin_vm = Path(vm.__dashboard_path__).with_name("vm")
                    p = subprocess.run([str(bin_vm), "status", "--json"], capture_output=True, text=True, timeout=30)
                    info = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else {
                        "error": (p.stderr or p.stdout or "vm status --json failed").strip()[-300:]}
            except Exception as e:  # noqa: BLE001
                info = {"error": "%s: %s" % (type(e).__name__, e)}
            self.status, self.status_at = info, time.time()
            return info


class DemoSource:
    def __init__(self, lang):
        self.lang = lang
        self.day = None
        self.payload = None

    def data(self):
        if self.day != date.today():
            self.payload = json.dumps(build_demo(self.lang), ensure_ascii=False).encode("utf-8")
            self.day = date.today()
        return self.payload

    def status_info(self):
        return demo_status(self.lang)


# ------------------------------------------------------------------ HTTP

def make_handler(source, bound_host, port):
    allowed_hosts = None
    if bound_host in LOOPBACK:
        # Guards against DNS rebinding: a page on another origin cannot read the vault through us.
        allowed_hosts = {"127.0.0.1", "localhost", "[::1]", "::1"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "VaultMemoryDashboard/1"

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self):
            if allowed_hosts is None:
                return True
            host = (self.headers.get("Host") or "").strip().lower()
            name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
            return name in allowed_hosts

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                self._send(403, b"forbidden host", "text/plain; charset=utf-8")
                return
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/", "/index.html"):
                    self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8",
                               {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"})
                elif path == "/api/data":
                    self._send(200, source.data(), "application/json; charset=utf-8")
                elif path == "/api/status":
                    self._json(200, source.status_info())
                else:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})

        def _not_allowed(self):
            self._send(405, b"method not allowed", "text/plain; charset=utf-8", {"Allow": "GET"})

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _not_allowed  # noqa: N815

        def log_message(self, fmt, *args):
            pass

    return Handler


def already_running(url):
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vm dashboard", description="Local Vault Memory dashboard (read-only).")
    ap.add_argument("--host", default=os.environ.get("VM_DASHBOARD_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("VM_DASHBOARD_PORT", "4747")))
    ap.add_argument("--open", action="store_true", help="open the dashboard in the browser once it is listening")
    ap.add_argument("--dump", action="store_true", help="print the /api/data JSON and exit")
    ap.add_argument("--demo", action="store_true", help="serve synthetic data instead of the vault")
    ap.add_argument("--lang", default="en", choices=["en", "tr"], help="language of the --demo data")
    args = ap.parse_args(argv)

    source = DemoSource(args.lang) if args.demo else VaultSource()
    if args.dump:
        sys.stdout.write(source.data().decode("utf-8"))
        return 0
    if not args.demo:
        get_vm()  # fail early with a clear message
    shown_host = "[%s]" % args.host if ":" in args.host else args.host
    url = "http://%s:%d" % (shown_host, args.port)
    try:
        server_cls = ThreadingHTTPServer
        if ":" in args.host:
            import socket

            class V6Server(ThreadingHTTPServer):
                address_family = socket.AF_INET6
            server_cls = V6Server
        srv = server_cls((args.host, args.port), make_handler(source, args.host, args.port))
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            if already_running(url):
                print("Dashboard is already running: %s" % url, flush=True)
                if args.open:
                    webbrowser.open(url)
                return 0
            print("Port %d is in use by another program. Try --port." % args.port, file=sys.stderr)
            return 1
        raise
    if args.host not in LOOPBACK:
        print("Warning: listening on %s makes your vault's session notes readable from the network." % args.host,
              file=sys.stderr)
    print("Vault Memory dashboard%s: %s  (Ctrl+C to stop)" % (" (demo)" if args.demo else "", url), flush=True)
    if args.open:
        threading.Timer(0.4, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
