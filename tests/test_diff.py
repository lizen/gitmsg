import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


def setUpModule():
    # 이 기계의 로케일이나 앞서 실행된 테스트에 결과가 좌우되지 않도록 고정한다.
    gitmsg.set_lang("ko")

def make_file(path, body="@@ -1 +1 @@\n+x\n", status="M"):
    return {"path": path, "status": status, "body": body, "truncated": False}


class FilterNoiseFilesTest(unittest.TestCase):
    def test_drops_lock_files(self):
        files = [make_file("src/app.py"), make_file("package-lock.json"),
                 make_file("yarn.lock"), make_file("pnpm-lock.yaml")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["src/app.py"])
        self.assertEqual(len(dropped), 3)

    def test_drops_build_output_directories(self):
        files = [make_file("src/app.py"), make_file("dist/bundle.js"),
                 make_file("target/classes/A.class"), make_file("node_modules/x/index.js"),
                 make_file("build/out.txt")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["src/app.py"])
        self.assertEqual(len(dropped), 4)

    def test_drops_editor_and_os_files(self):
        files = [make_file("src/app.py"), make_file(".idea/workspace.xml"),
                 make_file(".DS_Store")]
        kept, _ = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["src/app.py"])

    def test_drops_minified_assets(self):
        files = [make_file("web/app.min.js"), make_file("web/app.min.css"),
                 make_file("web/app.js")]
        kept, _ = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["web/app.js"])

    def test_drops_binary_diffs(self):
        binary = make_file("docs/logo.png",
                           body="diff --git a/docs/logo.png b/docs/logo.png\n"
                                "Binary files a/docs/logo.png and b/docs/logo.png differ\n")
        kept, dropped = gitmsg.filter_noise_files([make_file("src/app.py"), binary])
        self.assertEqual([f["path"] for f in kept], ["src/app.py"])
        self.assertEqual([f["path"] for f in dropped], ["docs/logo.png"])

    def test_keeps_sql_files(self):
        # example 계열에서는 쿼리 변경이 커밋의 핵심인 경우가 많다
        files = [make_file("migration/001_alter.sql")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["migration/001_alter.sql"])
        self.assertEqual(dropped, [])

    def test_dropped_entries_keep_path_and_status(self):
        files = [make_file("yarn.lock", status="M")]
        _, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual(dropped[0]["path"], "yarn.lock")
        self.assertEqual(dropped[0]["status"], "M")

    def test_file_named_build_is_not_noise(self):
        # 파일명이 build/dist/target이지만 디렉터리가 아님
        files = [make_file("build")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["build"])
        self.assertEqual(dropped, [])

    def test_file_inside_build_dir_is_noise(self):
        # src/build/x.js는 여전히 노이즈
        files = [make_file("src/build/x.js")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)


class ApplyBudgetTest(unittest.TestCase):
    def test_leaves_small_files_untouched(self):
        files = [make_file("a.py", "x" * 100), make_file("b.py", "y" * 200)]
        result = gitmsg.apply_budget(files)
        self.assertEqual(len(result[0]["body"]), 100)
        self.assertFalse(result[0]["truncated"])
        self.assertFalse(result[1]["truncated"])

    def test_truncates_per_file_cap(self):
        files = [make_file("big.py", "line\n" * 3000)]  # 15,000자
        result = gitmsg.apply_budget(files, per_file=6000, total=48000)
        self.assertLessEqual(len(result[0]["body"]), 6000)
        self.assertTrue(result[0]["truncated"])
        self.assertIn("생략", result[0]["body"])

    def test_truncates_largest_first_until_total_fits(self):
        files = [make_file("small.py", "s" * 500),
                 make_file("big1.py", "a" * 6000),
                 make_file("big2.py", "b" * 6000)]
        result = gitmsg.apply_budget(files, per_file=6000, total=8000)
        by_path = {f["path"]: f for f in result}
        self.assertEqual(len(by_path["small.py"]["body"]), 500)
        self.assertFalse(by_path["small.py"]["truncated"])
        self.assertLessEqual(sum(len(f["body"]) for f in result), 8000)

    def test_preserves_file_order(self):
        files = [make_file("a.py", "a" * 6000), make_file("b.py", "b" * 100)]
        result = gitmsg.apply_budget(files, per_file=6000, total=3000)
        self.assertEqual([f["path"] for f in result], ["a.py", "b.py"])

    def test_empty_input(self):
        self.assertEqual(gitmsg.apply_budget([]), [])

    def test_many_files_respects_budget(self):
        # 회귀 테스트: 2000개 파일로도 예산을 지켜야 함
        files = [make_file("f%d.py" % i, "x" * 201) for i in range(2000)]
        result = gitmsg.apply_budget(files, per_file=6000, total=48000)
        total_size = sum(len(f["body"]) for f in result)
        self.assertLessEqual(total_size, 48000)

    def test_truncate_respects_limit(self):
        # 6001자를 6000으로 자르면 6000 이하
        body = "x" * 6001
        result = gitmsg.apply_budget([make_file("a.py", body)], per_file=6000, total=48000)
        self.assertLessEqual(len(result[0]["body"]), 6000)

    def test_omitted_line_count_accuracy(self):
        # 보고된 생략 줄 수가 실제 생략된 줄 수와 정확히 일치해야 함
        # 이는 경계에서 +1 오류를 감지하는 회귀 테스트
        import re
        body = "line\n" * 2000  # 2000개 완전한 줄
        total_lines = body.count("\n")  # 2000

        # 생략을 강제하기 위해 per_file을 작게 설정
        result = gitmsg.apply_budget([make_file("a.py", body)], per_file=3000, total=48000)
        truncated = result[0]["body"]

        # 마커에서 보고된 생략 줄 수 추출
        match = re.search(r'\.\.\..*?(\d+)줄 생략', truncated)
        self.assertIsNotNone(match, "생략 마커를 찾을 수 없음")
        reported_omitted = int(match.group(1))

        # 실제 생략된 줄 수 계산
        # 마커 앞의 content를 추출
        head = truncated.split("... (")[0].rstrip("\n")

        # head의 줄 수 = 뉴라인 개수로 정확히 계산
        # rstrip 후 head는 항상 \n으로 끝나지 않으므로
        # tail.count("\n") + tail.endswith("\n") 계산과 대응되도록
        lines_in_head = head.count("\n") if head else 0

        actual_omitted = total_lines - lines_in_head

        # 보고된 것과 실제가 정확히 일치해야 함
        self.assertEqual(reported_omitted, actual_omitted,
            f"보고: {reported_omitted}줄, 실제: {actual_omitted}줄")


if __name__ == "__main__":
    unittest.main()
