import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg
import helpers

def setUpModule():
    # Pin the language so results do not depend on tests that ran earlier.
    gitmsg.set_lang("ko")


class GitTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = helpers.make_repo(os.path.join(self.tmp, "repo"))
        helpers.write(self.repo, "a.txt", "one\n")
        helpers.commit(self.repo, "첫 커밋")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ResolveRepoTest(GitTestCase):
    def test_returns_toplevel_from_subdirectory(self):
        sub = os.path.join(self.repo, "sub", "deep")
        os.makedirs(sub)
        self.assertEqual(
            os.path.realpath(gitmsg.resolve_repo(sub)),
            os.path.realpath(self.repo),
        )

    def test_raises_outside_a_repo(self):
        outside = os.path.join(self.tmp, "plain")
        os.makedirs(outside)
        with self.assertRaises(gitmsg.GitError):
            gitmsg.resolve_repo(outside)


class CurrentBranchTest(GitTestCase):
    def test_reads_branch_name(self):
        helpers.git(self.repo, "checkout", "-q", "-b", "feature/DEF-119")
        self.assertEqual(gitmsg.current_branch(self.repo), "feature/DEF-119")

    def test_detached_head_returns_empty(self):
        head = helpers.git(self.repo, "rev-parse", "HEAD").strip()
        helpers.git(self.repo, "checkout", "-q", head)
        self.assertEqual(gitmsg.current_branch(self.repo), "")


class CollectDiffTest(GitTestCase):
    def test_prefers_staged_over_worktree(self):
        helpers.write(self.repo, "b.txt", "base\n")
        helpers.commit(self.repo, "b 추가")

        helpers.write(self.repo, "a.txt", "one\ntwo\n")
        helpers.git(self.repo, "add", "a.txt")
        helpers.write(self.repo, "b.txt", "base\nchanged\n")  # tracked but not staged

        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(mode, "staged")
        self.assertEqual([f["path"] for f in files], ["a.txt"])

    def test_falls_back_to_worktree(self):
        helpers.write(self.repo, "a.txt", "one\nchanged\n")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(mode, "worktree")
        self.assertEqual([f["path"] for f in files], ["a.txt"])

    def test_captures_status(self):
        helpers.write(self.repo, "new.txt", "hi\n")
        helpers.git(self.repo, "add", "new.txt")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(files[0]["status"], "A")

    def test_body_contains_the_hunk(self):
        helpers.write(self.repo, "a.txt", "one\ntwo\n")
        helpers.git(self.repo, "add", "a.txt")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertIn("+two", files[0]["body"])
        self.assertFalse(files[0]["truncated"])

    def test_splits_multiple_files(self):
        helpers.write(self.repo, "a.txt", "one\ntwo\n")
        helpers.write(self.repo, "c.txt", "new file\n")
        helpers.git(self.repo, "add", "-A")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(sorted(f["path"] for f in files), ["a.txt", "c.txt"])

    def test_no_changes_returns_empty_list(self):
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(mode, "worktree")
        self.assertEqual(files, [])

    def test_korean_filename_is_not_corrupted(self):
        helpers.write(self.repo, "한글파일.txt", "hi\n")
        helpers.git(self.repo, "add", "한글파일.txt")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(files[0]["path"], "한글파일.txt")
        self.assertEqual(files[0]["status"], "A")

    def test_rename_reports_new_path_and_status(self):
        helpers.git(self.repo, "mv", "a.txt", "renamed.txt")
        mode, files = gitmsg.collect_diff(self.repo)
        self.assertEqual(files[0]["path"], "renamed.txt")
        self.assertEqual(files[0]["status"], "R")

    def test_euckr_encoded_content_does_not_crash_and_keeps_ascii_structure(self):
        """Legacy Korean repositories mix in sources saved as EUC-KR/CP949.
        Such bytes in a diff must not crash with UnicodeDecodeError. Broken
        bytes become replacement characters, while ASCII structure such as
        paths and +/- markers stays intact so the model can still read the diff."""
        path = os.path.join(self.repo, "Legacy.java")
        with open(path, "wb") as fh:
            fh.write("사용자 정보 처리 및 예외 클래스 정의".encode("euc-kr"))
        helpers.git(self.repo, "add", "Legacy.java")

        mode, files = gitmsg.collect_diff(self.repo)  # fails here if it raises

        self.assertEqual(files[0]["path"], "Legacy.java")
        self.assertIn("+++ b/Legacy.java", files[0]["body"])
        self.assertIn("�", files[0]["body"])  # broken bytes remain as replacement characters


class GitProcessFailureTest(unittest.TestCase):
    """Verify that `_git` turns a failure of subprocess itself (e.g. no git
    executable) into GitError. This is a different failure axis from EUC-KR
    decoding: decoding never raises thanks to errors="replace", whereas this
    covers subprocess.run failing to start the process at all."""

    def setUp(self):
        self._run = gitmsg.subprocess.run

    def tearDown(self):
        gitmsg.subprocess.run = self._run

    def test_missing_git_binary_raises_git_error_not_traceback(self):
        def fake_run(argv, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "git")

        gitmsg.subprocess.run = fake_run
        with self.assertRaises(gitmsg.GitError) as ctx:
            gitmsg._git("/tmp", "status")
        message = str(ctx.exception)
        self.assertTrue(
            any("가" <= ch <= "힣" for ch in message),
            "한국어 메시지가 아님: %r" % message,
        )


class CollectExamplesTest(GitTestCase):
    def test_subjects_newest_first(self):
        helpers.write(self.repo, "a.txt", "two\n")
        helpers.commit(self.repo, "두 번째 커밋")
        subjects, _ = gitmsg.collect_examples(self.repo)
        self.assertEqual(subjects[0], "두 번째 커밋")
        self.assertIn("첫 커밋", subjects)

    def test_drops_initial_commit_label(self):
        helpers.write(self.repo, "b.txt", "x\n")
        helpers.git(self.repo, "add", "-A")
        helpers.git(self.repo, "commit", "-q", "-m", "Initial commit")
        helpers.write(self.repo, "c.txt", "y\n")
        helpers.git(self.repo, "add", "-A")
        helpers.git(self.repo, "commit", "-q", "-m", "Initial commit for parser")
        subjects, _ = gitmsg.collect_examples(self.repo)
        self.assertNotIn("Initial commit", subjects)
        self.assertIn("Initial commit for parser", subjects)

    def test_excludes_merge_commits(self):
        helpers.git(self.repo, "checkout", "-q", "-b", "side")
        helpers.write(self.repo, "s.txt", "side\n")
        helpers.commit(self.repo, "사이드 작업")
        helpers.git(self.repo, "checkout", "-q", "main")
        helpers.write(self.repo, "m.txt", "main\n")
        helpers.commit(self.repo, "메인 작업")
        helpers.git(self.repo, "merge", "-q", "--no-ff",
                    "-m", "Merge branch 'side'\n\n병합 본문 특이한 내용", "side")
        subjects, full = gitmsg.collect_examples(self.repo)
        self.assertNotIn("Merge branch 'side'", subjects)
        self.assertIn("사이드 작업", subjects)
        merge_body = "병합 본문 특이한 내용"
        self.assertFalse(any(merge_body in entry for entry in full))

    def test_respects_limit(self):
        for index in range(30):
            helpers.write(self.repo, "a.txt", "v%d\n" % index)
            helpers.commit(self.repo, "변경 %d" % index)
        subjects, _ = gitmsg.collect_examples(self.repo, n=25)
        self.assertEqual(len(subjects), 25)

    def test_collects_commits_with_body(self):
        helpers.write(self.repo, "c.txt", "x\n")
        helpers.git(self.repo, "add", "-A")
        helpers.git(self.repo, "commit", "-q", "-m", "제목만 있는 커밋")
        helpers.write(self.repo, "d.txt", "y\n")
        helpers.git(self.repo, "add", "-A")
        helpers.git(self.repo, "commit", "-q",
                    "-m", "제목 줄", "-m", "본문 첫 줄\n본문 둘째 줄")
        _, full = gitmsg.collect_examples(self.repo)
        self.assertTrue(any("본문 첫 줄" in entry for entry in full))
        self.assertFalse(any("제목만 있는 커밋" in entry for entry in full))

    def test_full_examples_capped_at_three(self):
        for index in range(5):
            helpers.write(self.repo, "e%d.txt" % index, "x\n")
            helpers.git(self.repo, "add", "-A")
            helpers.git(self.repo, "commit", "-q",
                        "-m", "제목 %d" % index, "-m", "본문 %d" % index)
        _, full = gitmsg.collect_examples(self.repo)
        self.assertEqual(len(full), 3)
        # Verify the three newest are selected, in newest-first order
        self.assertIn("본문 4", full[0])
        self.assertIn("본문 3", full[1])
        self.assertIn("본문 2", full[2])


if __name__ == "__main__":
    unittest.main()
