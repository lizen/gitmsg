import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


def setUpModule():
    # Pin the language so results do not depend on tests that ran earlier.
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
        # In example-style projects, the query change is often the point of the commit
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
        # Named build/dist/target, but not a directory
        files = [make_file("build")]
        kept, dropped = gitmsg.filter_noise_files(files)
        self.assertEqual([f["path"] for f in kept], ["build"])
        self.assertEqual(dropped, [])

    def test_file_inside_build_dir_is_noise(self):
        # src/build/x.js is still noise
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
        files = [make_file("big.py", "line\n" * 3000)]  # 15,000 chars
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
        # Regression test: the budget must hold even with 2000 files
        files = [make_file("f%d.py" % i, "x" * 201) for i in range(2000)]
        result = gitmsg.apply_budget(files, per_file=6000, total=48000)
        total_size = sum(len(f["body"]) for f in result)
        self.assertLessEqual(total_size, 48000)

    def test_truncate_respects_limit(self):
        # Truncating 6001 chars to 6000 leaves at most 6000
        body = "x" * 6001
        result = gitmsg.apply_budget([make_file("a.py", body)], per_file=6000, total=48000)
        self.assertLessEqual(len(result[0]["body"]), 6000)

    def test_omitted_line_count_accuracy(self):
        # The reported omitted line count must match the actual count exactly.
        # Regression test for an off-by-one at the boundary.
        import re
        body = "line\n" * 2000  # 2000 complete lines
        total_lines = body.count("\n")  # 2000

        # Keep per_file small to force omission
        result = gitmsg.apply_budget([make_file("a.py", body)], per_file=3000, total=48000)
        truncated = result[0]["body"]

        # Extract the omitted line count reported in the marker
        match = re.search(r'\.\.\..*?(\d+)줄 생략', truncated)
        self.assertIsNotNone(match, "생략 마커를 찾을 수 없음")
        reported_omitted = int(match.group(1))

        # Count the lines actually omitted
        # Take the content before the marker
        head = truncated.split("... (")[0].rstrip("\n")

        # Count head lines exactly as the number of newlines.
        # After rstrip, head never ends with \n, which mirrors
        # the tail.count("\n") + tail.endswith("\n") calculation
        lines_in_head = head.count("\n") if head else 0

        actual_omitted = total_lines - lines_in_head

        # Reported and actual must match exactly
        self.assertEqual(reported_omitted, actual_omitted,
            f"보고: {reported_omitted}줄, 실제: {actual_omitted}줄")


if __name__ == "__main__":
    unittest.main()
