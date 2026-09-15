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
    # 이 기계의 로케일이나 앞서 실행된 테스트에 결과가 좌우되지 않도록 고정한다.
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

    def tearDown(self):
        gitmsg.urlopen = self._urlopen
        gitmsg.run_commit = self._run_commit
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("GITMSG_URL", None)
        os.environ.pop("NATIV_API_KEY", None)

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
        """디코딩이 관대해졌으니 EUC-KR 내용이 섞여도 정상 흐름을 그대로
        타야 한다 — 대체 문자가 섞인 diff라도 커밋 메시지 생성까지 이어진다."""
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
        """build_prompt에 넘기는 8개 위치 인자가 뒤바뀌면 렌더링된 각 자리가
        어긋난다는 것을 확인한다. 인접한 두 인자를 바꿔치기해도 예외 없이
        조용히 잘못된 프롬프트를 만들 수 있으므로, 값이 "어딘가에 있는지"가
        아니라 "제 자리에 있는지"를 확인해야 한다."""
        helpers.git(self.repo, "checkout", "-q", "-b", "hotfix/ABC-7")
        # subjects 슬롯과 full_examples 슬롯을 구분하기 위한 커밋 두 개.
        # 하나는 본문 없이 제목만 있고(subjects 전용), 하나는 본문에만 있는
        # 문구를 담는다(full_examples 전용). 두 문구는 서로 부분 문자열이
        # 아니라서 자리가 바뀌면 반드시 엉뚱한 구역에서 검출된다.
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

        # 브랜치 슬롯: 브랜치 전체 경로 형태로만 나온다 (이슈 키 슬롯과 겹치지 않는 문자열)
        self.assertIn("브랜치: hotfix/ABC-7", user)
        # 이슈 키 슬롯: 키와 스타일 힌트(백틱 포함)로만 나온다
        self.assertIn(
            "이슈 키: ABC-7 — 제목 맨 앞에 `ABC-7 ` 형태로 넣어라.", user
        )
        # mode 슬롯: 이번 변경이 staged 라는 라벨이 그대로 나온다
        self.assertIn(gitmsg._t("lbl_target") + gitmsg.mode_label("staged"), user)
        # kept 파일: 경로와 diff 본문이 함께 있어야 한다
        self.assertIn("- M a.txt", user)
        self.assertIn("+two", user)
        # dropped 파일: 경로만, "(diff 생략)" 마커와 함께 나와야 한다
        self.assertIn("- A yarn.lock (diff 생략)", user)

        # subjects 슬롯과 full_examples 슬롯: "어딘가에 있다"가 아니라
        # "제 구역에만 있다"를 확인해야 서로 바뀌치기된 경우를 잡아낸다.
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
    """run_commit이 실제로 subprocess.call에 넘기는 argv를 검증한다.

    run_commit 자체를 monkeypatch하는 다른 테스트들은 이 함수 내부의
    subprocess.call 호출문을 전혀 실행하지 않는다. -e는 이 프로젝트의
    핵심 안전장치(확인 없이 커밋되는 경로를 막는 것)이므로, 그 인자가
    실제로 나가는지 여기서 직접 확인한다.
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
