"""Offline unit tests for the scan and audit scripts (no network, no GPU).

    python3 -m unittest discover -s tests -p 'test_*.py'
"""
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_host_syncs  # noqa: E402
import audit_platform_gates  # noqa: E402
import check_framework_skills  # noqa: E402
import latest_image  # noqa: E402
import post_queue  # noqa: E402
import propose_knowledge  # noqa: E402
import run_lock  # noqa: E402
import scan_ci  # noqa: E402
import scan_issues  # noqa: E402
import scan_upstream  # noqa: E402


class CheckFrameworkSkillsTest(unittest.TestCase):
    INDEX = textwrap.dedent("""\
        | Role | Phase | Skills | When to read |
        |---|---|---|---|
        | implementer | implement | `write-sglang-test`, `gone-skill` | a `not-a-skill` flag in this column is ignored |
        | investigator | investigate | `debug-cuda-crash` | crashes |

        Not used by Petra: `cookbook-migrate-model`.
        """)

    def test_drift(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in (".agents/skills/write-sglang-test", ".agents/skills/debug-cuda-crash",
                        ".agents/skills/cookbook-migrate-model", ".agents/skills/new-skill",
                        "python/sglang/multimodal_gen/.agents/skills/sglang-diffusion-add-model"):
                Path(d, rel).mkdir(parents=True)
                Path(d, rel, "SKILL.md").write_text("---\nname: x\n---\n")
            Path(d, ".agents/skills/no-skill-md").mkdir(parents=True)
            self.assertEqual(check_framework_skills.table_names(self.INDEX),
                             ["debug-cuda-crash", "gone-skill", "write-sglang-test"])
            r = check_framework_skills.check(self.INDEX, d)
            self.assertEqual(r["missing"], ["gone-skill"])
            self.assertEqual(r["unindexed"], ["new-skill", "sglang-diffusion-add-model"])
            self.assertEqual(r["present"], 5)


class LatestImageTest(unittest.TestCase):
    TAGS = [  # as Docker Hub lists them, newest push first
        {"name": "v0.5.23-rocm720-mi30x-20261104", "last_updated": "2026-11-04T12:40:00Z"},
        {"name": "miles-rocm10-mi35x", "last_updated": "2026-11-04T11:31:00Z"},
        {"name": "miles-rocm10-mi35x-20261104", "last_updated": "2026-11-04T11:30:58Z"},
        {"name": "v0.5.23-rocm10-mi35x-20261103", "last_updated": "2026-11-03T12:00:52Z"},
        {"name": "v0.5.23-rocm10-mi30x-20261103", "last_updated": "2026-11-03T11:44:58Z"},
        {"name": "v0.5.22-rocm10-mi35x-20261021", "last_updated": "2026-11-03T09:00:00Z"},  # re-pushed
        {"name": "v0.5.22.post1-rocm10-mi35x-20261103", "last_updated": "2026-11-03T08:00:00Z"},
        {"name": "v0.5.23-rocm10-mi35x-20261103-debug", "last_updated": "2026-11-03T13:00:00Z"},
    ]

    def test_newest_daily_build_of_the_variant(self):
        self.assertEqual(latest_image.pick(self.TAGS, "rocm10-mi35x"), "v0.5.23-rocm10-mi35x-20261103")
        self.assertEqual(latest_image.pick(self.TAGS, "rocm10-mi30x"), "v0.5.23-rocm10-mi30x-20261103")
        self.assertEqual(latest_image.pick(self.TAGS, "rocm720-mi30x"), "v0.5.23-rocm720-mi30x-20261104")

    def test_miles_and_other_tags_never_count(self):
        miles = [t for t in self.TAGS if t["name"].startswith("miles")]
        self.assertEqual(latest_image.pick(miles, "rocm10-mi35x"), "")
        self.assertIsNone(latest_image.daily_key("v0.5.23-rocm10-mi35x-20261103-debug", "rocm10-mi35x"))
        self.assertIsNone(latest_image.daily_key("v0.5.23-rocm10-mi35xx-20261103", "rocm10-mi35x"))
        self.assertEqual(latest_image.daily_key("v0.5.22.post1-rocm10-mi35x-20261103", "rocm10-mi35x"),
                         ("20261103", (0, 5, 22)))


class PostQueueTest(unittest.TestCase):
    """The daily queue issue in Petra's own repository; the GitHub API is faked."""

    def queue(self, number, date, state="open"):
        return {"number": number, "title": post_queue.title(date), "state": state,
                "html_url": "https://github.com/At1a8/Petra/issues/%d" % number, "body": "q\n" + post_queue.MARKER}

    def test_repo_from_url(self):
        for url in ("https://github.com/At1a8/Petra.git", "git@github.com:At1a8/Petra.git", "https://github.com/At1a8/Petra"):
            self.assertEqual(post_queue.repo_from_url(url), "At1a8/Petra")
        self.assertEqual(post_queue.repo_from_url("https://gitlab.com/a/b.git"), "")

    def test_a_private_detail_stops_the_post(self):
        body = "| 1 | fix X | see rocm.docs.amd.com |\nlocal models `/data/models/some-model`\nhost gpu-node-7\nsee confluence"
        self.assertEqual([l.split(":")[0] for l in post_queue.leaks(body, "gpu-node-7")], ["2", "3", "4"])
        self.assertEqual(post_queue.leaks("| 1 | GLM crashes with --dcp-size 8 | #41299 |", "gpu-node-7"), [])

    def test_one_issue_a_day(self):
        old, today = self.queue(3, "2026-11-05"), self.queue(5, "2026-11-06")
        self.assertEqual(post_queue.plan([old, today], "2026-11-06"), {"action": "update", "number": 5, "close": [3]})
        self.assertEqual(post_queue.plan([old], "2026-11-07"), {"action": "create", "number": None, "close": [3]})

    def test_post_creates_and_supersedes(self):
        calls = []

        def fake(method, path, token="", data=None):
            calls.append((method, path, data))
            if method == "GET":
                return [self.queue(3, "2026-11-05"), {"number": 4, "title": "a PR", "pull_request": {}, "body": post_queue.MARKER},
                        {"number": 2, "title": "a bug", "body": "unrelated"}]
            return {"number": 7, "html_url": "https://github.com/At1a8/Petra/issues/7"}

        with mock.patch.object(post_queue, "api", side_effect=fake):
            out = post_queue.post("At1a8/Petra", "| 1 | task |", "2026-11-06", "t")
        self.assertEqual((out["action"], out["number"], out["closed"]), ("created", 7, [3]))
        self.assertEqual([(m, p) for m, p, _ in calls[1:]], [("POST", "/repos/At1a8/Petra/issues"),
                                                           ("POST", "/repos/At1a8/Petra/issues/3/comments"),
                                                           ("PATCH", "/repos/At1a8/Petra/issues/3")])
        self.assertEqual(calls[1][2]["title"], "Task queue 2026-11-06")
        self.assertTrue(calls[1][2]["body"].endswith(post_queue.MARKER + "\n"))

    def test_nothing_is_posted_without_the_token_or_with_a_leak(self):
        with tempfile.TemporaryDirectory() as d:
            clean, leaky = Path(d) / "clean.md", Path(d) / "leaky.md"
            clean.write_text("| 1 | task |\n")
            leaky.write_text("weights in /data/models/x\n")
            env = {k: v for k, v in os.environ.items() if k != "PETRA_REPO_TOKEN"}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(post_queue, "api") as api, \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(post_queue.main(["--body", str(clean), "--repo", "At1a8/Petra"]), 2)
                self.assertEqual(post_queue.main(["--body", str(leaky), "--repo", "At1a8/Petra"]), 3)
            api.assert_not_called()

    def test_latest(self):
        items = [{"number": 9, "title": "a bug", "body": ""}, self.queue(8, "2026-11-06"), self.queue(6, "2026-11-05", "closed")]
        with mock.patch.object(post_queue, "api", return_value=items):
            got = post_queue.latest("At1a8/Petra")
        self.assertEqual((got["date"], got["number"], got["state"]), ("2026-11-06", 8, "open"))
        with mock.patch.object(post_queue, "api", return_value=[]):
            self.assertEqual(post_queue.latest("At1a8/Petra"), {})


def git(*args, cwd=None):
    import subprocess
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class ProposeKnowledgeTest(unittest.TestCase):
    """The curator's knowledge/ changes as a pull request; a local bare repository stands in for GitHub."""

    def setUp(self):
        import subprocess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.origin, seed, self.petra = root / "origin.git", root / "seed", root / "Petra"
        git("init", "-q", "--bare", str(self.origin))
        git("clone", "-q", str(self.origin), str(seed))
        (seed / "knowledge").mkdir()
        (seed / "knowledge" / "known_issues.md").write_text("# Known issues\n")
        (seed / "petra.js").write_text("// petra\n")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "seed", cwd=seed)
        git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=seed)
        git("clone", "-q", "-b", "main", str(self.origin), str(self.petra))
        self.run = root / "exp" / "issue_41299-glm-dcp_20261106-071502Z"
        self.run.mkdir(parents=True)
        self.body = self.run / "knowledge_pr.md"
        self.body.write_text("KI-001: GLM-5.3 with --dcp-size 8 on MI300X, from issue #41299.\n")
        self.show = lambda ref: subprocess.run(["git", "--git-dir", str(self.origin), "show", ref],
                                               capture_output=True, text=True).stdout

    def propose(self, token="t", api=None):
        env = {k: v for k, v in os.environ.items() if k != "PETRA_REPO_TOKEN"}
        if token:
            env["PETRA_REPO_TOKEN"] = token
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()) as out, \
                redirect_stderr(io.StringIO()) as err, mock.patch.object(propose_knowledge, "api", side_effect=api):
            rc = propose_knowledge.main(["--run-dir", str(self.run), "--body", str(self.body), "--repo", "At1a8/Petra",
                                         "--petra-dir", str(self.petra), "--push-url", str(self.origin)])
        return rc, out.getvalue(), err.getvalue()

    def test_only_knowledge_goes_to_its_branch_and_the_checkout_reads_main_again(self):
        (self.petra / "knowledge" / "known_issues.md").write_text("# Known issues\nKI-001 GLM-5.3 dcp 8\n")
        (self.petra / "knowledge" / "feature_skills" / "dcp").mkdir(parents=True)
        (self.petra / "knowledge" / "feature_skills" / "dcp" / "SKILL.md").write_text("draft\n")
        (self.petra / "petra.js").write_text("// a local change that is not knowledge\n")
        calls = []

        def fake(method, path, token="", data=None):
            calls.append((method, path, data))
            return [] if method == "GET" else {"number": 12, "html_url": "https://github.com/At1a8/Petra/pull/12"}

        rc, out, err = self.propose(api=fake)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)["url"], "https://github.com/At1a8/Petra/pull/12")
        branch = "petra/knowledge/" + self.run.name
        self.assertIn("KI-001", self.show(branch + ":knowledge/known_issues.md"))
        self.assertEqual(self.show(branch + ":knowledge/feature_skills/dcp/SKILL.md"), "draft\n")
        self.assertEqual(self.show(branch + ":petra.js"), "// petra\n")
        self.assertEqual(self.show("main:knowledge/known_issues.md"), "# Known issues\n", "main is never pushed")
        self.assertEqual((calls[1][0], calls[1][2]["head"], calls[1][2]["base"]), ("POST", branch, "main"))
        self.assertEqual((self.petra / "knowledge" / "known_issues.md").read_text(), "# Known issues\n")
        self.assertFalse((self.petra / "knowledge" / "feature_skills").exists())
        self.assertIn("a local change", (self.petra / "petra.js").read_text())

    def test_nothing_leaves_without_a_token_with_a_leak_or_without_changes(self):
        self.assertEqual(self.propose()[0:2], (0, '{"action": "none", "reason": "no changes under knowledge/"}\n'))
        (self.petra / "knowledge" / "known_issues.md").write_text("# Known issues\nKI-001 GLM-5.3 dcp 8\n")
        self.assertEqual(self.propose(token="")[0], 2)
        (self.petra / "knowledge" / "known_issues.md").write_text("# Known issues\nweights in /data/models/x\n")
        self.assertEqual(self.propose()[0], 3)
        self.assertIn("/data/models/x", (self.petra / "knowledge" / "known_issues.md").read_text(), "left as it was")
        self.assertEqual(self.show("petra/knowledge/" + self.run.name), "", "no branch was pushed")


class RunLockTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.lock = str(self.root / "petra-run.lock")
        self.a, self.b = str(self.root / "run_a"), str(self.root / "run_b")
        Path(self.a).mkdir()

    def test_one_task_at_a_time(self):
        self.assertEqual(run_lock.status(self.lock)["status"], "free")
        self.assertEqual(run_lock.acquire(self.lock, self.a, "issue 41299", "issue")["status"], "acquired")
        self.assertEqual(run_lock.acquire(self.lock, self.a)["status"], "acquired")  # a retry of the same run
        busy = run_lock.acquire(self.lock, self.b, "scan", "scan")
        self.assertEqual((busy["status"], busy["holder"]["run_dir"], busy["holder"]["task"]), ("busy", self.a, "issue 41299"))
        self.assertEqual(run_lock.release(self.lock, self.b)["status"], "held")
        self.assertEqual(run_lock.release(self.lock, self.a)["status"], "released")
        self.assertEqual(run_lock.acquire(self.lock, self.b)["status"], "acquired")

    def test_a_finished_or_silent_run_is_taken_over(self):
        t0 = 1_000_000.0
        run_lock.acquire(self.lock, self.a, idle_hours=12, now=t0)
        (Path(self.a) / "run_report.md").write_text("done")
        os.utime(Path(self.a) / "run_report.md", (t0 + 60, t0 + 60))
        took = run_lock.acquire(self.lock, self.b, now=t0 + 120)
        self.assertEqual((took["status"], took["took_over"]["reason"]), ("acquired", "its run finished"))
        Path(self.b).mkdir()
        os.utime(self.b, (t0 + 120, t0 + 120))
        self.assertEqual(run_lock.acquire(self.lock, self.a, now=t0 + 11 * 3600)["status"], "busy")
        late = run_lock.acquire(self.lock, self.a, now=t0 + 13 * 3600)
        self.assertEqual((late["status"], late["took_over"]["reason"]), ("acquired", "its run wrote nothing for 12 h"))

    def test_an_old_report_does_not_free_a_resumed_run(self):
        (Path(self.a) / "run_report.md").write_text("stopped at Design")
        os.utime(Path(self.a) / "run_report.md", (1000.0, 1000.0))
        run_lock.acquire(self.lock, self.a, now=2000.0)
        os.utime(self.a, (2000.0, 2000.0))
        self.assertEqual(run_lock.acquire(self.lock, self.b, now=2100.0)["status"], "busy")

    def test_a_run_in_another_container_is_not_taken_over_for_silence(self):
        """Its run directory is in that container: invisible here, so silence proves nothing."""
        other = str(self.root / "elsewhere" / "issue_41299-glm-dcp_20261106-071502Z")
        run_lock.acquire(self.lock, other, idle_hours=12, now=1000.0)
        self.assertEqual(run_lock.acquire(self.lock, self.a, now=1000.0 + 48 * 3600)["status"], "busy")
        self.assertEqual(run_lock.release(self.lock, force=True)["status"], "released")
        self.assertEqual(run_lock.acquire(self.lock, self.a)["status"], "acquired")

    def test_force_release_and_the_command_line(self):
        run_lock.acquire(self.lock, self.a)
        self.assertEqual(run_lock.release(self.lock, force=True)["status"], "released")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(run_lock.main(["--lock", self.lock, "acquire", "--run-dir", self.a]), 0)
            self.assertEqual(run_lock.main(["--lock", self.lock, "acquire", "--run-dir", self.b]), 1)
            self.assertEqual(run_lock.main(["--lock", self.lock, "status"]), 0)
        self.assertIn('"status": "busy"', out.getvalue())


class ScanCiTest(unittest.TestCase):
    ENTRIES = {
        "test/a.py::A.setUpClass": {"cluster": "ImportError: _check removed", "status": "recurring (new regression since 2026-10-21)",
                                    "error": "ImportError: cannot import name '_check'", "first_seen": "2026-10-22", "last_seen": "2026-10-23",
                                    "job_url": "https://ci/1"},
        "test/b.py::B.test_x": {"cluster": "ImportError: _check removed", "status": "never-passed (rocm720 lane, since 2026-10-20)",
                                "error": "ImportError", "first_seen": "2026-10-22", "last_seen": "2026-10-25"},
        "test/c.py::C.test_y": {"cluster": "runner lost communication", "status": "flaky", "first_seen": "2026-10-24", "last_seen": "2026-10-24"},
    }

    def body(self, state):
        return "## Tracker\nsome table\n<!-- ci-failure-tracker-state: " + json.dumps(state) + " -->\ntrailing text"

    def test_parse_state_direct_and_wrapped(self):
        self.assertEqual(scan_ci.parse_state(self.body(self.ENTRIES)), self.ENTRIES)
        self.assertEqual(scan_ci.parse_state(self.body({"entries": self.ENTRIES})), self.ENTRIES)
        self.assertEqual(scan_ci.parse_state("no state here"), {})
        self.assertEqual(scan_ci.parse_state("<!-- ci-failure-tracker-state: {broken -->"), {})

    def test_aggregate(self):
        clusters = scan_ci.aggregate(self.ENTRIES)
        top = clusters[0]
        self.assertEqual(top["cluster"], "ImportError: _check removed")
        self.assertEqual(top["n_tests"], 2)
        self.assertEqual(top["since"], "2026-10-20")
        self.assertEqual((top["first_seen"], top["last_seen"]), ("2026-10-22", "2026-10-25"))
        self.assertEqual(top["statuses"], {"recurring": 1, "never-passed": 1})
        self.assertEqual(clusters[1]["statuses"], {"flaky": 1})


class ScanIssuesTest(unittest.TestCase):
    def test_classify_kind(self):
        self.assertEqual(scan_issues.classify_kind("AMD Development Roadmap (2026 Q4)", []), "roadmap")
        self.assertEqual(scan_issues.classify_kind("[Failure Tracker] PR Test (AMD)", []), "tracker")
        self.assertEqual(scan_issues.classify_kind("anything", ["ci-failure-tracker"]), "tracker")
        self.assertEqual(scan_issues.classify_kind("[AITER-Upgrade] PR readiness", []), "internal")
        self.assertEqual(scan_issues.classify_kind("[Bug] GLM 5.3 segfault on MI300", []), "user")

    def test_cites_issue(self):
        self.assertTrue(scan_issues.cites_issue("Fixes #38849", 38849))
        self.assertTrue(scan_issues.cites_issue("see https://github.com/sgl-project/sglang/issues/38849.", 38849))
        self.assertTrue(scan_issues.cites_issue("related to issue 38849", 38849))
        self.assertFalse(scan_issues.cites_issue("bumps #388490 and port 38849", 38849))

    def test_projected_auto_close(self):
        self.assertEqual(scan_issues.projected_auto_close("2026-09-09T10:00:00Z"), "2026-11-09")
        self.assertEqual(scan_issues.projected_auto_close("2026-09-09T00:00:00Z"), "2026-11-08")

    def test_reply_status(self):
        rep = "alice"
        self.assertTrue(scan_issues.reply_status([{"user": {"login": "alice"}}], rep)["only_reporter_or_bots"])
        bot = [{"user": {"login": "github-actions[bot]"}, "author_association": "CONTRIBUTOR"}]
        self.assertEqual(scan_issues.reply_status(bot, rep)["replies_from_others"], 0)
        maint = [{"user": {"login": "bob"}, "author_association": "COLLABORATOR"}]
        s = scan_issues.reply_status(maint, rep)
        self.assertEqual((s["replies_from_others"], s["maintainer_replied"]), (1, True))


GIT_LOG = (
    "\x1eaaaa1111\x1f2026-11-02T10:00:00+08:00\x1fdev\x1f[Perf] kda: Batch FlashInfer prefill copies (#47651)\n"
    "diff --git a/python/sglang/srt/layers/kda.py b/python/sglang/srt/layers/kda.py\n"
    "--- a/python/sglang/srt/layers/kda.py\n"
    "+++ b/python/sglang/srt/layers/kda.py\n"
    "@@ -10,0 +11,3 @@\n"
    "+from flashinfer import prefill\n"
    "+if _is_cuda and x.is_cuda:\n"
    "+    y = t.is_cuda\n"
    "\x1ebbbb2222\x1f2026-11-02T11:00:00+08:00\x1fdev\x1f[Fix] [AMD] aiter: guard import (#47700)\n"
    "diff --git a/python/sglang/srt/x.py b/python/sglang/srt/x.py\n"
    "--- a/python/sglang/srt/x.py\n"
    "+++ b/python/sglang/srt/x.py\n"
    "@@ -1,0 +2,1 @@\n"
    "+if _is_cuda:\n"
    "\x1ecccc3333\x1f2026-11-02T12:00:00+08:00\x1fdev\x1f[Feat] [XPU] graph: Add full prefill graph (#30980)\n"
    "diff --git a/python/sglang/srt/g.py b/python/sglang/srt/g.py\n"
    "--- a/python/sglang/srt/g.py\n"
    "+++ b/python/sglang/srt/g.py\n"
    "@@ -1,0 +2,1 @@\n"
    "+from flashinfer import x\n"
    "\x1edddd4444\x1f2026-11-02T13:00:00+08:00\x1fdev\x1f[Feat] diffusion/model: support HiDream-O1-Image (#39682)\n"
    "diff --git a/python/sglang/multimodal_gen/runtime/models/dits/hidream.py b/python/sglang/multimodal_gen/runtime/models/dits/hidream.py\n"
    "--- /dev/null\n"
    "+++ b/python/sglang/multimodal_gen/runtime/models/dits/hidream.py\n"
    "@@ -0,0 +1,1 @@\n"
    "+class HiDream: pass\n"
)


class ScanUpstreamTest(unittest.TestCase):
    def test_parse_and_candidates(self):
        commits = scan_upstream.parse_log(GIT_LOG)
        self.assertEqual(len(commits), 4)
        first = commits[0]
        self.assertEqual(first["pr"], 47651)
        self.assertEqual([g["line"] for g in first["gates"]], [12])  # `t.is_cuda` (line 13) is not a gate
        self.assertIn("flashinfer", first["cuda_deps"])
        cands = {c["pr"]: c["kinds"] for c in scan_upstream.candidates(commits)}
        self.assertEqual(cands[47651], ["new_cuda_gate", "cuda_first_feature"])
        self.assertNotIn(47700, cands)   # AMD work
        self.assertNotIn(30980, cands)   # another platform
        self.assertEqual(cands[39682], ["new_model"])

    def test_untagged_subject(self):
        self.assertTrue(scan_upstream.parse_subject("srt: Support FooModel (#1)")["is_feature"])
        self.assertFalse(scan_upstream.parse_subject("[Fix] srt: Add a guard (#2)")["is_feature"])


class AuditPlatformGatesTest(unittest.TestCase):
    def test_python_rules(self):
        src = textwrap.dedent("""\
            if _is_cuda:
                pass
            ok = t.is_cuda
            if not _is_hip:
                pass
            raise ValueError("CUDA only")
            default = "trtllm" if major >= 10 else "fa3"
            if is_gfx95_supported():
                pass
            """)
        cats = {e["line"]: e for e in audit_platform_gates.scan_text("x.py", src, audit_platform_gates.PY_RULES)}
        self.assertEqual(cats[1]["category"], "cuda_gate")
        self.assertNotIn(3, cats)
        self.assertEqual(cats[4]["category"], "hip_excluded")
        self.assertEqual(cats[6]["category"], "unsupported_note")
        self.assertEqual(cats[7]["category"], "capability_check")
        self.assertIn("gfx1250", cats[7]["note"])
        self.assertEqual(cats[8]["category"], "arch_gate")

    def test_device_rules(self):
        src = "v += __shfl_xor_sync(0xffffffffu, v, 16);\nconstexpr int kWarpSize = 32;\nok();\n"
        hip = audit_platform_gates.scan_text("jit/csrc/norm_rope.cuh", src, audit_platform_gates.DEVICE_RULES)
        self.assertEqual([e["line"] for e in hip], [1, 2])
        self.assertTrue(hip[0]["note"].startswith("built for HIP"))
        nv = audit_platform_gates.scan_text("csrc/cutlass_ext/x.cuh", src, audit_platform_gates.DEVICE_RULES)
        self.assertEqual(nv[0]["note"], "NVIDIA-only file?")


class AuditHostSyncsTest(unittest.TestCase):
    SRC = textwrap.dedent("""\
        import torch

        class Backend:
            def __init__(self, x):
                self.n = int(x.max().item())

            def init_forward_metadata(self, batch):
                total = int(batch.seq_lens.sum().item())
                host = batch.seq_lens_cpu.max().item()
                idx = batch.page_indptr.to(self.device)
                fast = batch.page_indptr.to(self.device, non_blocking=True)
                t = torch.tensor([1, 2], device=self.device)
                return total, host, idx, fast, t

            def init_cuda_graph_state(self, x):
                return x.tolist()

            def forward_extend(self, q):
                torch.cuda.synchronize()
                return q
        """)

    def test_findings(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "backend.py"
            p.write_text(self.SRC)
            found = audit_host_syncs.scan([p])
        by_line = {f["line"]: f for f in found}
        self.assertEqual(by_line[5]["temperature"], "cold")                 # __init__
        self.assertEqual((by_line[8]["kind"], by_line[8]["temperature"]), ("sync", "warm"))
        self.assertEqual(by_line[9]["kind"], "host_side")                   # seq_lens_cpu
        self.assertEqual(by_line[10]["kind"], "copy")                       # blocking .to(device)
        self.assertNotIn(11, by_line)                                       # non_blocking=True
        self.assertEqual(by_line[12]["call"], "torch.tensor(..., device=)")
        self.assertEqual(by_line[16]["temperature"], "cold")                # init_cuda_graph_state
        self.assertEqual((by_line[19]["call"], by_line[19]["temperature"]), (".synchronize()", "warm"))


if __name__ == "__main__":
    unittest.main()
