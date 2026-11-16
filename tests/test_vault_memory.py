"""End-to-end tests: install into a throwaway HOME, feed fake transcripts, run the worker with a fake LLM.

Run: python3 -m unittest discover -s tests -v
Nothing here touches the real ~/.claude, ~/.vault-memory or launchd/systemd.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FAKE_AGENT = textwrap.dedent(r'''
    import re, sys
    prompt = sys.stdin.read()
    m = re.search(r"^- (?:Session file|Oturum dosyası): (.+)$", prompt, re.M)
    hhmm = re.search(r"`## (\d\d:\d\d) — ", prompt).group(1)
    tr = "Oturum dosyası" in prompt
    vault = __import__("os").environ["TEST_VAULT"]
    with open(vault + "/" + m.group(1).strip(), "a", encoding="utf-8") as f:
        if tr:
            f.write("\n## %s — Giriş hatası düzeltildi\n\n**İstek:** girişi düzelt\n**Yapılanlar:** auth.py değişti\n"
                    "- testler eklendi\n**Kararlar:** oturum süresi 1 saat\n" % hhmm)
        else:
            f.write("\n## %s — Fixed the login bug\n\n**Request:** fix login\n**Done:** changed auth.py\n"
                    "- added tests\n**Decisions:** sessions last 1 hour\n" % hhmm)
''')


def transcript(path, cwd, start, n=10, step_min=2, session_id="s1"):
    lines = []
    for i in range(n):
        ts = (start + timedelta(minutes=i * step_min)).isoformat().replace("+00:00", "Z")
        if i % 2 == 0:
            msg = {"role": "user", "content": "please fix the login bug, step %d" % i}
            kind = "user"
        else:
            msg = {"role": "assistant", "content": [{"type": "text", "text": "done step %d" % i},
                                                    {"type": "tool_use", "name": "Edit", "input": {"file_path": cwd + "/auth.py"}}]}
            kind = "assistant"
        lines.append(json.dumps({"type": kind, "timestamp": ts, "cwd": cwd, "sessionId": session_id, "message": msg}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (n - 1) * step_min


class VaultMemoryTest(unittest.TestCase):
    lang = "en"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vm-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.vault = self.home / "Vault"
        self.env = dict(os.environ)
        for k in ("VAULT_MEMORY_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "VAULT_MEMORY_WORKER"):
            self.env.pop(k, None)
        self.env.update({
            "HOME": str(self.home), "TEST_VAULT": str(self.vault),
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"),
        })
        (self.tmp / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
        self.agent = self.tmp / "agent.py"
        self.agent.write_text(FAKE_AGENT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cmd(self, *args, check=True, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        p = subprocess.run([str(a) for a in args], env=env, capture_output=True, text=True, timeout=120)
        if check and p.returncode != 0:
            self.fail("command failed: %s\nstdout:\n%s\nstderr:\n%s" % (args, p.stdout, p.stderr))
        return p

    def vm(self, *args, **kw):
        return self.run_cmd(self.vault / "99-Meta/System/bin/vm", *args, **kw)

    def install(self):
        self.run_cmd("bash", REPO / "install.sh", "--vault", self.vault, "--lang", self.lang, "--machine", "laptop")

    def fake_llm(self, mode="1"):
        return {"VAULT_MEMORY_FAKE_LLM": mode, "VAULT_MEMORY_FAKE_LLM_HOOK": "%s %s" % (sys.executable, self.agent)}

    # ------------------------------------------------------------------

    def test_end_to_end(self):
        unit, general = ("min", "general") if self.lang == "en" else ("dk", "genel")
        self.install()
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertIn(".vault-memory/bin/vm", json.dumps(settings["hooks"]))
        skill = "vault-memory" if self.lang == "en" else "vault-hafiza"
        self.assertTrue((self.home / ".claude/skills" / skill / "SKILL.md").exists())
        shared = json.loads((self.vault / "99-Meta/System/config.json").read_text())
        self.assertEqual(shared["language"], self.lang)
        self.assertTrue((self.vault / "index.md").exists())
        self.assertNotIn("{{date}}", (self.vault / "log.md").read_text())

        project = self.home / "Projects" / "acme-api"
        project.mkdir(parents=True)
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        minutes = transcript(self.home / ".claude/projects/-acme/11111111-1111-1111-1111-111111111111.jsonl",
                             str(project), start)
        other = self.home / "scratch"
        other.mkdir()
        transcript(self.home / ".claude/projects/-scratch/22222222-2222-2222-2222-222222222222.jsonl",
                   str(other), start + timedelta(minutes=30), n=4, step_min=1, session_id="s2")

        self.vm("worker", "--now", extra_env=self.fake_llm())
        sessions = list((self.vault / "02-Projects/PRJ-acme-api/sessions").glob("*.md"))
        self.assertEqual(len(sessions), 1)
        text = sessions[0].read_text()
        self.assertRegex(text, r"(?m)^minutes: %d$" % minutes)
        self.assertRegex(text, r"(?m)^## \d\d:\d\d — .+ \(%d %s · claude-code\)$" % (minutes, unit))
        page = (self.vault / "02-Projects/PRJ-acme-api/PRJ-acme-api.md").read_text()
        self.assertIn("## Summary" if self.lang == "en" else "## Özet", page)
        self.assertIn("Sessions.base" if self.lang == "en" else "Oturumlar.base", page)
        self.assertIn("| PRJ-acme-api | test entry", (self.vault / "log.md").read_text())
        self.assertIn("[[PRJ-acme-api]]", (self.vault / "index.md").read_text())
        gen = list((self.vault / "05-Raw/sessions").rglob("* %s laptop.md" % general))
        self.assertEqual(len(gen), 1)
        log = self.run_cmd("git", "-C", self.vault, "log", "--format=%s").stdout
        self.assertIn("PRJ-acme-api — test entry", log)

        report = json.loads(self.vm("report", "--days", "2", "--json").stdout)
        self.assertEqual(report["totals"]["PRJ-acme-api"], minutes)
        text_report = self.vm("report", "--days", "2").stdout
        self.assertIn("PRJ-acme-api", text_report)

        status = json.loads(self.vm("status", "--json").stdout)
        self.assertEqual(status["pending"], 0)
        self.assertEqual(status["language"], self.lang)

        dump = json.loads(self.run_cmd(sys.executable, self.vault / "99-Meta/System/dashboard/server.py", "--dump").stdout)
        self.assertEqual(dump["lang"], self.lang)
        acme = [s for s in dump["sessions"] if s["project"] == "PRJ-acme-api"]
        self.assertEqual(len(acme), 1)
        self.assertEqual(acme[0]["minutes"], minutes)
        self.assertTrue(acme[0]["request"])
        self.assertEqual(len(acme[0]["done"]), 2)
        self.assertTrue(any(s["project"] == "_none" for s in dump["sessions"]))
        self.assertEqual(sum(d["minutes"] for d in dump["days"]),
                         sum(s["minutes"] for s in dump["sessions"]))

        ctx = self.vm("context", "--cwd", project).stdout
        self.assertIn("PRJ-acme-api", ctx)
        self.assertIn("<vault-memory>" if self.lang == "en" else "<vault-hafiza>", ctx)

        self.vm("lint")
        self.assertTrue(list((self.vault / "99-Meta/Lint").glob("*.md")))

        # A second install is an upgrade: it must not reset the vault or duplicate hooks.
        self.install()
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertEqual(json.dumps(settings["hooks"]).count("hook session-start"), 1)
        self.assertEqual(len(list((self.vault / "02-Projects/PRJ-acme-api/sessions").glob("*.md"))), 1)

        self.vm("uninstall")
        settings = json.loads((self.home / ".claude/settings.json").read_text())
        self.assertNotIn(".vault-memory/bin/vm", json.dumps(settings))
        self.assertFalse((self.home / ".claude/skills" / skill).exists())
        self.assertTrue(self.vault.exists())

    def test_quota_is_retried_not_failed(self):
        self.install()
        project = self.home / "Projects" / "acme-api"
        project.mkdir(parents=True)
        transcript(self.home / ".claude/projects/-acme/33333333-3333-3333-3333-333333333333.jsonl", str(project),
                   datetime.now(timezone.utc) - timedelta(hours=2))
        self.vm("worker", "--now", extra_env=self.fake_llm("quota"))
        status = json.loads(self.vm("status", "--json").stdout)
        self.assertEqual(status["pending"], 1)
        state = json.loads((self.home / ".vault-memory/state.json").read_text())
        self.assertEqual(state["fail"], {})


class TurkishVaultTest(VaultMemoryTest):
    lang = "tr"


class UnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vault_memory", str(REPO / "system/bin/vault_memory.py"))
        cls.vm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.vm)

    def test_limit_regex(self):
        for text in ("You've hit your usage limit · resets 5pm", "HTTP 429 Too Many Requests", "Overloaded"):
            self.assertTrue(self.vm.LIMIT_RE.search(text), text)
        self.assertFalse(self.vm.LIMIT_RE.search("syntax error in file"))

    def test_redaction(self):
        self.vm.set_language("en")
        out = self.vm.redact("key sk-ant-" + "a" * 30 + " and password=hunter22 and https://u:pw123@host/x")
        self.assertNotIn("hunter22", out)
        self.assertNotIn("pw123", out)
        self.assertNotIn("sk-ant-", out)
        self.assertIn("[REDACTED]", out)

    def test_entry_regex_accepts_both_units(self):
        body = "## 10:00 — A (12 min · claude-code)\n- 11:00 · 3 dk · codex · kısa oturum\n## 12:00 — B (5 dk · codex)\n"
        self.assertEqual(sorted(int(a or b) for a, b in self.vm.ENTRY_RE.findall(body)), [3, 5, 12])

    def test_legacy_turkish_vault_detected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "99-Meta/Bases").mkdir(parents=True)
            (Path(d) / "99-Meta/Bases/Oturumlar.base").write_text("")
            self.assertEqual(self.vm.detect_language(d), "tr")
            self.assertEqual(self.vm.detect_language(tempfile.gettempdir()), "en")

    def test_slugify(self):
        self.vm.set_language("en")
        self.assertEqual(self.vm.slugify("AcmeApi"), "acme-api")
        self.assertEqual(self.vm.slugify("Çalışma Notları"), "calisma-notlari")

    def test_messages_complete(self):
        for key, pair in self.vm.MESSAGES.items():
            self.assertEqual(len(pair), 2, key)
            self.assertEqual(pair[0].count("%"), pair[1].count("%"), key)


if __name__ == "__main__":
    unittest.main()
