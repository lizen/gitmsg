import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


def setUpModule():
    # 이 기계의 로케일이나 앞서 실행된 테스트에 결과가 좌우되지 않도록 고정한다.
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
        # 따옴표가 안쪽에도 있으면 바깥쪽을 벗기지 않는다
        text = '"경로" 처리 수정 "완료"'
        self.assertEqual(gitmsg.clean_response(text), text)

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(gitmsg.clean_response("\n\n  ABC-1 수정  \n\n"), "ABC-1 수정")

    def test_empty_input(self):
        self.assertEqual(gitmsg.clean_response(""), "")

    def test_quotes_wrapping_fence(self):
        # 펜스가 따옴표로 감싸인 경우 둘 다 벗겨야 한다
        self.assertEqual(
            gitmsg.clean_response('"```\nX\n```"'),
            "X",
        )

    def test_quotes_wrapping_prefix(self):
        # 프리픽스가 따옴표로 감싸인 경우 둘 다 벗겨야 한다
        self.assertEqual(
            gitmsg.clean_response('"커밋 메시지: X"'),
            "X",
        )

    def test_four_backtick_fence(self):
        # 4틱 이상의 펜스도 인식해야 한다
        self.assertEqual(
            gitmsg.clean_response("````\nX\n````"),
            "X",
        )

    def test_unterminated_fence(self):
        # 종료되지 않은 펜스는 펜스 줄을 떼어내고 내용만 둔다
        self.assertEqual(
            gitmsg.clean_response("```\nX"),
            "X",
        )

    def test_two_fences_unchanged(self):
        # 두 개의 펜스가 있으면 어느 것이 메시지인지 모르므로 그대로 둔다
        text = "```\nA\n```\n\n```\nB\n```"
        self.assertEqual(
            gitmsg.clean_response(text),
            text,
        )

    def test_six_backtick_fence(self):
        # 6틱 펜스도 정확히 인식해야 한다 (str.count() 오버카운팅 회피)
        self.assertEqual(
            gitmsg.clean_response("``````\nX\n``````"),
            "X",
        )

    def test_unterminated_six_backtick_fence(self):
        # 미종료 6틱 펜스도 처리해야 한다
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
        # ABC-1은 ABC-18에 포함되지만, 다른 키이므로 삽입해야 한다
        message = "ABC-18 무언가 수정"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "ABC-1", "prefix"),
            "ABC-1 ABC-18 무언가 수정",
        )

    def test_key_with_bracket_already_present(self):
        # 브라켓 형태로 이미 있으면 중복하지 않는다
        message = "[DEF-119] 갭분석 지원"
        self.assertEqual(
            gitmsg.enforce_issue_key(message, "DEF-119", "prefix"),
            message,
        )


if __name__ == "__main__":
    unittest.main()
