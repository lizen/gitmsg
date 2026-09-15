import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg


def setUpModule():
    gitmsg.set_lang("ko")


def build(lang, **overrides):
    gitmsg.set_lang(lang)
    args = {
        "subjects": ["ABC-1 첫 커밋"],
        "full_examples": [],
        "branch": "feature/ABC-2",
        "issue_key": "ABC-2",
        "key_style": "prefix",
        "mode": "staged",
        "kept": [{"path": "a.py", "status": "M",
                  "body": "@@ -1 +1 @@\n+x\n", "truncated": False}],
        "dropped": [{"path": "yarn.lock", "status": "M",
                     "body": "", "truncated": False}],
    }
    args.update(overrides)
    return gitmsg.build_prompt(**args)


class LangTestCase(unittest.TestCase):
    def setUp(self):
        for name in ("GITMSG_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
            os.environ.pop(name, None)

    def tearDown(self):
        for name in ("GITMSG_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
            os.environ.pop(name, None)
        gitmsg.set_lang("ko")


class ResolveLangTest(LangTestCase):
    def test_default_is_auto(self):
        self.assertEqual(gitmsg.resolve_lang(None), "auto")

    def test_env_is_used(self):
        os.environ["GITMSG_LANG"] = "en"
        self.assertEqual(gitmsg.resolve_lang(None), "en")

    def test_flag_beats_env(self):
        os.environ["GITMSG_LANG"] = "en"
        self.assertEqual(gitmsg.resolve_lang("ko"), "ko")

    def test_case_and_space_tolerated(self):
        self.assertEqual(gitmsg.resolve_lang("  KO "), "ko")

    def test_unknown_value_raises_with_supported_list(self):
        with self.assertRaises(ValueError) as ctx:
            gitmsg.resolve_lang("jp")
        message = str(ctx.exception)
        self.assertIn("jp", message)
        for supported in gitmsg.SUPPORTED_LANGS:
            self.assertIn(supported, message)


class UiLanguageTest(LangTestCase):
    def test_auto_follows_locale(self):
        os.environ["LANG"] = "ko_KR.UTF-8"
        gitmsg.set_lang("auto")
        self.assertEqual(gitmsg._UI_LANG, "ko")
        os.environ["LANG"] = "en_US.UTF-8"
        gitmsg.set_lang("auto")
        self.assertEqual(gitmsg._UI_LANG, "en")

    def test_auto_falls_back_to_en_for_unknown_locale(self):
        os.environ["LANG"] = "fr_FR.UTF-8"
        gitmsg.set_lang("auto")
        self.assertEqual(gitmsg._UI_LANG, "en")

    def test_explicit_lang_ignores_locale(self):
        os.environ["LANG"] = "en_US.UTF-8"
        gitmsg.set_lang("ko")
        self.assertEqual(gitmsg._UI_LANG, "ko")

    def test_runtime_message_follows_ui_language(self):
        gitmsg.set_lang("ko")
        self.assertIn("변경", gitmsg._t("no_changes"))
        gitmsg.set_lang("en")
        self.assertIn("No staged changes", gitmsg._t("no_changes"))


class CatalogTest(LangTestCase):
    def test_both_languages_have_the_same_keys(self):
        # 한쪽에만 키가 있으면 그 언어에서 KeyError 로 죽는다.
        self.assertEqual(
            sorted(gitmsg.MESSAGES["ko"]), sorted(gitmsg.MESSAGES["en"])
        )

    def test_every_catalog_key_is_reachable(self):
        for lang in ("ko", "en"):
            gitmsg.set_lang(lang)
            for key in gitmsg.MESSAGES[lang]:
                self.assertIsInstance(gitmsg._t(key), str)

    def test_format_specifiers_match_across_languages(self):
        import re
        spec = re.compile(r"%[sd]")
        for key, ko_text in gitmsg.MESSAGES["ko"].items():
            en_text = gitmsg.MESSAGES["en"][key]
            self.assertEqual(spec.findall(ko_text), spec.findall(en_text),
                             "형식 지정자가 어긋난 키: " + key)


class PromptLanguageTest(LangTestCase):
    def test_auto_tells_model_to_follow_history(self):
        # auto 는 UI 언어를 로케일에서 가져오므로 로케일을 명시해 결정적으로 만든다.
        os.environ["LANG"] = "ko_KR.UTF-8"
        system = build("auto")[0]["content"]
        self.assertIn("같은 언어", system)
        self.assertNotIn("반드시 한국어", system)

    def test_auto_in_english_locale_still_follows_history(self):
        os.environ["LANG"] = "en_US.UTF-8"
        system = build("auto")[0]["content"]
        self.assertIn("same language as this repository", system)
        self.assertNotIn("Write in English, even if", system)

    def test_ko_pins_korean(self):
        system = build("ko")[0]["content"]
        self.assertIn("반드시 한국어", system)

    def test_en_pins_english_and_writes_prompt_in_english(self):
        messages = build("en")
        system, user = messages[0]["content"], messages[1]["content"]
        self.assertIn("Write in English", system)
        self.assertIn("## Recent commit subjects", user)
        self.assertIn("branch: ", user)
        self.assertIn("(diff omitted)", user)

    def test_ko_writes_prompt_in_korean(self):
        user = build("ko")[1]["content"]
        self.assertIn("## 이 저장소의 최근 커밋 제목", user)
        self.assertIn("브랜치: ", user)
        self.assertIn("(diff 생략)", user)

    def test_truncation_marker_follows_language(self):
        gitmsg.set_lang("en")
        self.assertIn("lines omitted", gitmsg._truncate("x" * 500, 100))
        gitmsg.set_lang("ko")
        self.assertIn("줄 생략", gitmsg._truncate("x" * 500, 100))


if __name__ == "__main__":
    unittest.main()
