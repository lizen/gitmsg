import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg
import helpers

def setUpModule():
    # Pin the language so results do not depend on tests that ran earlier.
    gitmsg.set_lang("ko")


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = helpers.make_repo(os.path.join(self.tmp, "repo"))
        helpers.write(self.repo, "a.txt", "one\n")
        helpers.commit(self.repo, "ABC-100 첫 커밋")
        self._urlopen = gitmsg.urlopen
        self._run_commit = gitmsg.run_commit
        os.environ.pop("GITMSG_URL", None)
        os.environ.pop("NATIV_API_KEY", None)
        # main() resets the language from GITMSG_LANG. Pin it, since these tests check Korean text.
        os.environ["GITMSG_LANG"] = "ko"

    def tearDown(self):
        gitmsg.urlopen = self._urlopen
        gitmsg.run_commit = self._run_commit
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("GITMSG_URL", None)
        os.environ.pop("NATIV_API_KEY", None)
        os.environ.pop("GITMSG_LANG", None)
        gitmsg.set_lang("ko")

    def stage_a_change(self):
        helpers.write(self.repo, "a.txt", "one\ntwo\n")
        helpers.git(self.repo, "add", "a.txt")

    def answer(self, content):
        def fake_urlopen(request, timeout=None):
            if request.full_url.endswith("/v1/models"):
                return FakeResponse({"data": [{"id": "test-model"}]})
            return FakeResponse({"choices": [{"message": {"content": content}}]})
        gitmsg.urlopen = fake_urlopen

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gitmsg.main(argv)
        return code, out.getvalue(), err.getvalue()


class ParseArgsTest(unittest.TestCase):
    def test_defaults(self):
        args = gitmsg.parse_args([])
        self.assertEqual(args.path, ".")
        self.assertFalse(args.edit)
        self.assertIsNone(args.model)
        self.assertIsNone(args.url)
        self.assertIsNone(args.api_key)
        self.assertFalse(args.print_prompt)

    def test_all_options(self):
        args = gitmsg.parse_args(
            ["/tmp/repo", "-e", "--model", "m1", "--url", "http://x:1",
             "--api-key", "test-key", "--print-prompt"]
        )
        self.assertEqual(args.path, "/tmp/repo")
        self.assertTrue(args.edit)
        self.assertEqual(args.model, "m1")
        self.assertEqual(args.url, "http://x:1")
        self.assertEqual(args.api_key, "test-key")
        self.assertTrue(args.print_prompt)


class ResolveUrlTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("GITMSG_URL", None)

    def test_explicit_wins(self):
        os.environ["GITMSG_URL"] = "http://env:1"
        self.assertEqual(gitmsg.resolve_url("http://flag:2"), "http://flag:2")

    def test_env_is_second(self):
        os.environ["GITMSG_URL"] = "http://env:1"
        self.assertEqual(gitmsg.resolve_url(None), "http://env:1")

    def test_default_is_last(self):
        self.assertEqual(gitmsg.resolve_url(None), gitmsg.DEFAULT_URL)


class ResolveApiKeyTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("NATIV_API_KEY", None)

    def test_explicit_wins(self):
        os.environ["NATIV_API_KEY"] = "from-env"
        self.assertEqual(gitmsg.resolve_api_key("from-flag"), "from-flag")

    def test_env_is_second(self):
        os.environ["NATIV_API_KEY"] = "from-env"
        self.assertEqual(gitmsg.resolve_api_key(None), "from-env")

    def test_no_key_returns_none(self):
        os.environ.pop("NATIV_API_KEY", None)
        self.assertIsNone(gitmsg.resolve_api_key(None))


class MainTest(CliTestCase):
    def test_not_a_repo_exits_1(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        code, _, err = self.run_main([plain])
        self.assertEqual(code, 1)
        self.assertIn("git 저장소를 읽을 수 없습니다", err)

    def test_repo_without_commits_exits_1(self):
        empty = helpers.make_repo(os.path.join(self.tmp, "empty"))
        helpers.write(empty, "x.txt", "hi\n")
        helpers.git(empty, "add", "-A")
        code, _, err = self.run_main([empty])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_euckr_staged_file_does_not_crash_the_cli(self):
        """Decoding is lenient now, so EUC-KR content must still go through the
        normal flow: a diff with replacement characters still yields a commit message."""
        path = os.path.join(self.repo, "Legacy.java")
        with open(path, "wb") as fh:
            fh.write("사용자 정보 처리 및 예외 클래스 정의".encode("euc-kr"))
        helpers.git(self.repo, "add", "Legacy.java")
        self.answer("레거시 파일 추가")
        code, out, err = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.strip(), "레거시 파일 추가")

    def test_git_binary_missing_exits_1_with_korean_message_not_traceback(self):
        original_run = gitmsg.subprocess.run

        def fake_run(argv, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "git")

        gitmsg.subprocess.run = fake_run
        try:
            code, _, err = self.run_main([self.repo])
        finally:
            gitmsg.subprocess.run = original_run
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("git 저장소를 읽을 수 없습니다", err)

    def test_no_changes_exits_1(self):
        code, _, err = self.run_main([self.repo])
        self.assertEqual(code, 1)
        self.assertIn("변경도", err)

    def test_prints_message_to_stdout(self):
        self.stage_a_change()
        self.answer("두 번째 줄 추가")
        code, out, _ = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "두 번째 줄 추가")

    def test_shows_progress_and_result_header_on_stderr(self):
        """Progress notices must go to stderr only, so piping (gitmsg | pbcopy) keeps working."""
        self.stage_a_change()
        self.answer("두 번째 줄 추가")
        code, out, err = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertIn(gitmsg.resolve_repo(self.repo), err)
        self.assertIn("분석하는 중", err)
        self.assertIn("권장 커밋 메시지", err)
        self.assertEqual(out.strip(), "두 번째 줄 추가")

    def test_default_output_is_english(self):
        os.environ.pop("GITMSG_LANG", None)
        self.stage_a_change()
        self.answer("Add second line")
        code, out, err = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertIn("Project: ", err)
        self.assertIn("Suggested commit message:", err)
        self.assertEqual(out.strip(), "Add second line")

    def test_lang_flag_switches_output_to_korean(self):
        os.environ.pop("GITMSG_LANG", None)
        self.stage_a_change()
        self.answer("두 번째 줄 추가")
        code, _, err = self.run_main([self.repo, "--lang", "ko"])
        self.assertEqual(code, 0)
        self.assertIn("권장 커밋 메시지", err)

    def test_enforces_issue_key_from_branch(self):
        helpers.git(self.repo, "checkout", "-q", "-b", "feature/DEF-119")
        self.stage_a_change()
        self.answer("두 번째 줄 추가")
        code, out, _ = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "DEF-119 두 번째 줄 추가")

    def test_strips_code_fence_from_model_output(self):
        self.stage_a_change()
        self.answer("```\n두 번째 줄 추가\n```")
        code, out, _ = self.run_main([self.repo])
        self.assertEqual(out.strip(), "두 번째 줄 추가")

    def test_print_prompt_skips_the_model_call(self):
        self.stage_a_change()

        def explode(request, timeout=None):
            raise AssertionError("호출되면 안 된다")
        gitmsg.urlopen = explode

        code, out, _ = self.run_main([self.repo, "--print-prompt"])
        self.assertEqual(code, 0)
        self.assertIn("=== system ===", out)
        self.assertIn("=== user ===", out)
        self.assertIn("+two", out)

    def test_print_prompt_places_each_value_in_its_slot(self):
        """If two of the 8 positional arguments to build_prompt get swapped, each
        rendered slot ends up in the wrong place. Swapping adjacent arguments
        can silently produce a wrong prompt without raising, so check that each
        value is "in its own slot", not merely "somewhere"."""
        helpers.git(self.repo, "checkout", "-q", "-b", "hotfix/ABC-7")
        # Two commits to tell the subjects slot from the full_examples slot.
        # One has only a subject (subjects only); the other carries a phrase
        # only in its body (full_examples only). Neither phrase is a substring
        # of the other, so a swap always shows up in the wrong section.
        helpers.write(self.repo, "subject_marker.txt", "hi\n")
        helpers.commit(self.repo, "SUBJECT-ONLY-MARKER 커밋")
        helpers.write(self.repo, "body_marker.txt", "hi\n")
        helpers.commit(self.repo, "일반 커밋 제목\n\nBODY-ONLY-MARKER 상세 설명")
        self.stage_a_change()
        helpers.write(self.repo, "yarn.lock", "{}\n")
        helpers.git(self.repo, "add", "yarn.lock")

        def explode(request, timeout=None):
            raise AssertionError("호출되면 안 된다")
        gitmsg.urlopen = explode

        code, out, _ = self.run_main([self.repo, "--print-prompt"])
        self.assertEqual(code, 0)
        user = out.split("=== user ===\n", 1)[1]

        # Branch slot: appears only as the full branch path (a string that does not overlap the issue-key slot)
        self.assertIn("브랜치: hotfix/ABC-7", user)
        # Issue-key slot: appears only as the key plus the style hint (with backticks)
        self.assertIn(
            "이슈 키: ABC-7 — 제목 맨 앞에 `ABC-7 ` 형태로 넣어라.", user
        )
        # mode slot: the label saying this change is staged appears verbatim
        self.assertIn(gitmsg._t("lbl_target") + gitmsg.mode_label("staged"), user)
        # kept file: path and diff body must both be present
        self.assertIn("- M a.txt", user)
        self.assertIn("+two", user)
        # dropped file: path only, together with the "(diff 생략)" marker
        self.assertIn("- A yarn.lock (diff 생략)", user)

        # subjects and full_examples slots: checking "only in its own section"
        # rather than "somewhere" is what catches the two being swapped.
        subjects_section = user.split("## 이 저장소의 최근 커밋 제목", 1)[1]
        subjects_section = subjects_section.split("## 본문이 있는 최근 커밋", 1)[0]
        body_section = user.split("## 본문이 있는 최근 커밋", 1)[1]
        body_section = body_section.split("## 이번 변경", 1)[0]

        self.assertIn("- SUBJECT-ONLY-MARKER 커밋", subjects_section)
        self.assertNotIn("BODY-ONLY-MARKER", subjects_section)
        self.assertIn("BODY-ONLY-MARKER 상세 설명", body_section)
        self.assertNotIn("SUBJECT-ONLY-MARKER", body_section)

    def test_nativ_down_exits_2(self):
        self.stage_a_change()

        def refuse(request, timeout=None):
            raise URLError(ConnectionRefusedError(61, "Connection refused"))
        gitmsg.urlopen = refuse

        code, _, err = self.run_main([self.repo])
        self.assertEqual(code, 2)
        self.assertIn("꺼져 있습니다", err)

    def test_edit_flag_calls_git_commit(self):
        self.stage_a_change()
        self.answer("두 번째 줄 추가")
        captured = {}

        def fake_run_commit(repo, message):
            captured["repo"] = repo
            captured["message"] = message
            return 0

        gitmsg.run_commit = fake_run_commit
        code, out, _ = self.run_main([self.repo, "-e"])
        self.assertEqual(code, 0)
        self.assertEqual(captured["message"], "두 번째 줄 추가")
        self.assertEqual(out, "")

    def test_unauthorized_exits_2(self):
        self.stage_a_change()

        def unauthorized(request, timeout=None):
            raise HTTPError("http://127.0.0.1:8080", 401, "Unauthorized", {}, None)
        gitmsg.urlopen = unauthorized

        code, _, err = self.run_main([self.repo])
        self.assertEqual(code, 2)
        self.assertIn("NATIV_API_KEY", err)

    def test_falls_back_to_worktree_changes(self):
        helpers.write(self.repo, "a.txt", "one\nunstaged\n")
        self.answer("추적 중인 변경 반영")
        code, out, _ = self.run_main([self.repo])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "추적 중인 변경 반영")


class RunCommitTest(unittest.TestCase):
    """Verify the argv that run_commit actually passes to subprocess.call.

    Other tests that monkeypatch run_commit never execute the
    subprocess.call inside it. -e is this project's key safeguard (no path
    commits without confirmation), so check here that the flag really goes out.
    """

    def setUp(self):
        self._call = gitmsg.subprocess.call

    def tearDown(self):
        gitmsg.subprocess.call = self._call

    def test_argv_contains_edit_flag_and_message_and_repo(self):
        captured = {}

        def fake_call(argv):
            captured["argv"] = argv
            return 7

        gitmsg.subprocess.call = fake_call
        result = gitmsg.run_commit("/some/repo", "커밋 메시지")

        argv = captured["argv"]
        self.assertIn("-e", argv)
        self.assertIn("-m", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "커밋 메시지")
        self.assertIn("-C", argv)
        self.assertEqual(argv[argv.index("-C") + 1], "/some/repo")
        self.assertEqual(result, 7)


if __name__ == "__main__":
    unittest.main()
