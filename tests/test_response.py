import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


def setUpModule():
    # Pin the language so results do not depend on tests that ran earlier.
    gitmsg.set_lang("ko")

class CleanResponseTest(unittest.TestCase):
    def test_strips_plain_code_fence(self):
        self.assertEqual(
            gitmsg.clean_response("```\nABC-1 수집 오류 수정\n```"),
            "ABC-1 수집 오류 수정",
        )

    def test_strips_language_tagged_fence(self):
        self.assertEqual(
            gitmsg.clean_response("```text\nABC-1 수집 오류 수정\n```"),
            "ABC-1 수집 오류 수정",
        )

    def test_keeps_body_inside_fence(self):
        cleaned = gitmsg.clean_response("```\n제목 줄\n\n본문 줄\n```")
        self.assertEqual(cleaned, "제목 줄\n\n본문 줄")

    def test_strips_korean_prefix(self):
        self.assertEqual(
            gitmsg.clean_response("커밋 메시지: ABC-1 수집 오류 수정"),
            "ABC-1 수집 오류 수정",
        )

    def test_strips_english_prefix(self):
        self.assertEqual(
            gitmsg.clean_response("Commit message: ABC-1 수집 오류 수정"),
            "ABC-1 수집 오류 수정",
        )

    def test_strips_matching_outer_quotes(self):
        self.assertEqual(gitmsg.clean_response('"ABC-1 수집 오류 수정"'),
                         "ABC-1 수집 오류 수정")

    def test_keeps_inner_quotes(self):
        # If the quote also appears inside, the outer quotes are not stripped
        text = '"경로" 처리 수정 "완료"'
        self.assertEqual(gitmsg.clean_response(text), text)

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(gitmsg.clean_response("\n\n  ABC-1 수정  \n\n"), "ABC-1 수정")

    def test_empty_input(self):
        self.assertEqual(gitmsg.clean_response(""), "")

    def test_quotes_wrapping_fence(self):
        # A fence wrapped in quotes: strip both
        self.assertEqual(
            gitmsg.clean_response('"```\nX\n```"'),
            "X",
        )

    def test_quotes_wrapping_prefix(self):
        # A prefix wrapped in quotes: strip both
        self.assertEqual(
            gitmsg.clean_response('"커밋 메시지: X"'),
            "X",
        )

    def test_four_backtick_fence(self):
        # Fences of four or more backticks must be recognized too
        self.assertEqual(
            gitmsg.clean_response("````\nX\n````"),
            "X",
        )

    def test_unterminated_fence(self):
        # An unterminated fence: drop the fence line and keep the content
        self.assertEqual(
            gitmsg.clean_response("```\nX"),
            "X",
        )

    def test_two_fences_unchanged(self):
        # With two fences it is unclear which one is the message, so leave it as is
        text = "```\nA\n```\n\n```\nB\n```"
        self.assertEqual(
            gitmsg.clean_response(text),
            text,
        )

    def test_six_backtick_fence(self):
        # Six-backtick fences must be recognized exactly (avoids str.count() overcounting)
        self.assertEqual(
            gitmsg.clean_response("``````\nX\n``````"),
            "X",
        )

    def test_unterminated_six_backtick_fence(self):
        # Unterminated six-backtick fences must be handled too
        self.assertEqual(
            gitmsg.clean_response("``````\nX"),
            "X",
        )


class EnforceIssueKeyTest(unittest.TestCase):
    def test_none_key_leaves_message_alone(self):
        self.assertEqual(
            gitmsg.enforce_issue_key("수집 오류 수정", None, "prefix"),
            "수집 오류 수정",
        )

    def test_existing_key_is_not_duplicated(self):
        message = "ABC-1858 갭분석 지원"
        self.assertEqual(gitmsg.enforce_issue_key(message, "ABC-1858", "prefix"), message)

    def test_inserts_prefix_style(self):
        self.assertEqual(
            gitmsg.enforce_issue_key("갭분석 지원", "ABC-1858", "prefix"),
            "ABC-1858 갭분석 지원",
        )

    def test_inserts_bracket_style(self):
        self.assertEqual(
            gitmsg.enforce_issue_key("갭분석 지원", "ABC-1858", "bracket"),
            "[ABC-1858] 갭분석 지원",
        )

    def test_inserts_suffix_style(self):
        self.assertEqual(
            gitmsg.enforce_issue_key("갭분석 지원", "ABC-1858", "suffix"),
            "갭분석 지원 (ABC-1858)",
        )

    def test_only_subject_line_is_touched(self):
        message = "갭분석 지원\n\n본문은 그대로 둔다"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "ABC-1858", "prefix"),
            "ABC-1858 갭분석 지원\n\n본문은 그대로 둔다",
        )

    def test_key_present_only_in_body_still_inserted_in_subject(self):
        message = "갭분석 지원\n\nABC-1858 관련"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "ABC-1858", "prefix"),
            "ABC-1858 갭분석 지원\n\nABC-1858 관련",
        )

    def test_key_substring_false_match(self):
        # ABC-1 appears inside ABC-18, but it is a different key, so insert it
        message = "ABC-18 무언가 수정"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "ABC-1", "prefix"),
            "ABC-1 ABC-18 무언가 수정",
        )

    def test_key_with_bracket_already_present(self):
        # Already present in bracket form, so do not duplicate it
        message = "[DEF-119] 갭분석 지원"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "DEF-119", "prefix"),
            message,
        )


if __name__ == "__main__":
    unittest.main()
