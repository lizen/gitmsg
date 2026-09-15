import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


class ExtractIssueKeyTest(unittest.TestCase):
    def test_bare_key_branch(self):
        self.assertEqual(gitmsg.extract_issue_key("ABC7-24"), "ABC7-24")
        self.assertEqual(gitmsg.extract_issue_key("ABC-1858"), "ABC-1858")

    def test_prefixed_branch(self):
        self.assertEqual(gitmsg.extract_issue_key("hotfix/JKL-4146"), "JKL-4146")
        self.assertEqual(gitmsg.extract_issue_key("feature/DEF-119"), "DEF-119")

    def test_long_project_code(self):
        self.assertEqual(gitmsg.extract_issue_key("JKLMNO-3405"), "JKLMNO-3405")

    def test_branches_without_key(self):
        for branch in ["dev", "master", "main", "develop",
                       "release-adv", "fetchUserProfile", ""]:
            self.assertIsNone(gitmsg.extract_issue_key(branch), branch)

    def test_first_match_wins(self):
        self.assertEqual(gitmsg.extract_issue_key("feature/ABC-1-and-DEF-2"), "ABC-1")


class DetectKeyStyleTest(unittest.TestCase):
    def test_bracket_style(self):
        subjects = [
            "[XYZ-248] fix: 결재 역할 팝업창 중복 제거",
            "[ABC-1858] 갭분석 지원",
        ]
        self.assertEqual(gitmsg.detect_key_style(subjects), "bracket")

    def test_prefix_style(self):
        subjects = [
            "ABC-1858 Teradata 갭분석 마이그레이션 정비",
            "XYZ-186 Ext API 인증 적용 및 Swagger 문서 개선",
        ]
        self.assertEqual(gitmsg.detect_key_style(subjects), "prefix")

    def test_suffix_style(self):
        subjects = [
            "fix(quality): 프로파일링 삭제 시 스키마 단위 격리 보정 (DEF-119)",
            "feat(quality): 프로파일링 테이블 단위 수행 지원 (DEF-119)",
        ]
        self.assertEqual(gitmsg.detect_key_style(subjects), "suffix")

    def test_defaults_to_prefix_when_no_key_present(self):
        subjects = [
            "pg db업그레이드에 따른 쿼리문 변경",
            "메일링 local 환경설정일때 발송 안되게 처리",
        ]
        self.assertEqual(gitmsg.detect_key_style(subjects), "prefix")

    def test_unclassifiable_position_is_ignored(self):
        # "[DQ] DEF-166 ..." 은 키가 대괄호 안도, 괄호 접미도, 문장 맨 앞도 아니다.
        # 세지 않고 넘어가므로 나머지 하나가 결과를 정한다.
        subjects = [
            "[DQ] DEF-166 샘플링 적용 안되는 오류 수정",
            "ABC-1858 갭분석 지원",
        ]
        self.assertEqual(gitmsg.detect_key_style(subjects), "prefix")

    def test_empty_list_defaults_to_prefix(self):
        self.assertEqual(gitmsg.detect_key_style([]), "prefix")


if __name__ == "__main__":
    unittest.main()
