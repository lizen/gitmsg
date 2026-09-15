import io
import json
import os
import socket
import sys
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gitmsg

URL = "http://127.0.0.1:8080"
MESSAGES = [{"role": "user", "content": "hi"}]
FAKE_KEY = "sk-test-do-not-leak-12345"

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


class RawResponse:
    """FakeResponse처럼 흉내내지만 이미 인코딩된 바이트를 그대로 돌려준다."""

    def __init__(self, raw_bytes):
        self._data = raw_bytes

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ClientTestCase(unittest.TestCase):
    def setUp(self):
        self._original = gitmsg.urlopen

    def tearDown(self):
        gitmsg.urlopen = self._original

    def respond_with(self, payload, captured=None):
        def fake_urlopen(request, timeout=None):
            if captured is not None:
                captured["url"] = request.full_url
                captured["timeout"] = timeout
                captured["method"] = request.get_method()
                captured["auth"] = request.get_header("Authorization")
                if request.data:
                    captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(payload)
        gitmsg.urlopen = fake_urlopen

    def raise_with(self, error):
        def fake_urlopen(request, timeout=None):
            raise error
        gitmsg.urlopen = fake_urlopen

    def respond_with_raw(self, raw_bytes):
        def fake_urlopen(request, timeout=None):
            return RawResponse(raw_bytes)
        gitmsg.urlopen = fake_urlopen


class ListModelsTest(ClientTestCase):
    def test_returns_ids_in_order(self):
        self.respond_with({"data": [
            {"id": "mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit"},
            {"id": "mlx-community/Qwen3-VL-30B-A3B-Instruct-4bit"},
        ]})
        self.assertEqual(
            gitmsg.list_models(URL),
            ["mlx-community/KAT-Coder-V2.5-Dev-OptiQ-4bit",
             "mlx-community/Qwen3-VL-30B-A3B-Instruct-4bit"],
        )

    def test_hits_v1_models(self):
        captured = {}
        self.respond_with({"data": []}, captured)
        gitmsg.list_models(URL)
        self.assertEqual(captured["url"], URL + "/v1/models")
        self.assertEqual(captured["method"], "GET")

    def test_trailing_slash_no_double_slash(self):
        captured = {}
        self.respond_with({"data": []}, captured)
        gitmsg.list_models(URL + "/")
        self.assertEqual(captured["url"], URL + "/v1/models")

    def test_empty_list(self):
        self.respond_with({"data": []})
        self.assertEqual(gitmsg.list_models(URL), [])

    def test_sends_bearer_token_when_key_given(self):
        captured = {}
        self.respond_with({"data": []}, captured)
        gitmsg.list_models(URL, api_key="test-key")
        self.assertEqual(captured["auth"], "Bearer test-key")

    def test_sends_no_auth_header_without_key(self):
        captured = {}
        self.respond_with({"data": []}, captured)
        gitmsg.list_models(URL)
        self.assertIsNone(captured["auth"])


class PickModelTest(ClientTestCase):
    def test_explicit_model_skips_lookup(self):
        self.raise_with(AssertionError("호출되면 안 된다"))
        self.assertEqual(gitmsg.pick_model(URL, explicit="my-model"), "my-model")

    def test_picks_first_available(self):
        self.respond_with({"data": [{"id": "first"}, {"id": "second"}]})
        self.assertEqual(gitmsg.pick_model(URL), "first")

    def test_no_models_raises(self):
        self.respond_with({"data": []})
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.pick_model(URL)
        self.assertIn("모델이 로드되지 않았습니다", str(ctx.exception))

    def test_passes_api_key_through(self):
        captured = {}
        self.respond_with({"data": [{"id": "first"}]}, captured)
        gitmsg.pick_model(URL, api_key="test-key")
        self.assertEqual(captured["auth"], "Bearer test-key")


class MalformedResponseTest(ClientTestCase):
    def test_malformed_json_raises_native_error(self):
        self.respond_with_raw(b"not valid json{")
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.list_models(URL)
        self.assertIn("해석할 수 없습니다", str(ctx.exception))

    def test_non_dict_top_level_raises_native_error(self):
        self.respond_with([1, 2, 3])
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.list_models(URL)
        self.assertIn("해석할 수 없습니다", str(ctx.exception))


class CompleteTest(ClientTestCase):
    def test_sends_expected_request(self):
        captured = {}
        self.respond_with({"choices": [{"message": {"content": "ABC-1 수정"}}]}, captured)
        gitmsg.complete(URL, "m1", MESSAGES)

        self.assertEqual(captured["url"], URL + "/v1/chat/completions")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], gitmsg.DEFAULT_TIMEOUT)
        body = captured["body"]
        self.assertEqual(body["model"], "m1")
        self.assertEqual(body["messages"], MESSAGES)
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["max_tokens"], 512)
        self.assertFalse(body["stream"])

    def test_parses_content(self):
        self.respond_with({"choices": [{"message": {"content": "ABC-1 수정"}}]})
        self.assertEqual(gitmsg.complete(URL, "m1", MESSAGES), "ABC-1 수정")

    def test_missing_choices_raises(self):
        self.respond_with({"choices": []})
        with self.assertRaises(gitmsg.NativError):
            gitmsg.complete(URL, "m1", MESSAGES)

    def test_connection_refused_explains_server_is_off(self):
        self.raise_with(URLError(ConnectionRefusedError(61, "Connection refused")))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES)
        message = str(ctx.exception)
        self.assertIn("꺼져 있습니다", message)
        self.assertIn(URL, message)

    def test_timeout_message(self):
        self.raise_with(socket.timeout())
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES)
        self.assertIn("응답이", str(ctx.exception))

    def test_url_error_wrapped_timeout_message(self):
        # 연결(SYN) 단계에서 타임아웃하면 urlopen이 socket.timeout을
        # URLError로 감싸서 던지기도 한다. bare socket.timeout과 같은
        # 안내 메시지를 내야 한다.
        self.raise_with(URLError(socket.timeout()))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES)
        self.assertIn("응답이", str(ctx.exception))

    def test_http_error_includes_status(self):
        self.raise_with(HTTPError(URL, 500, "Internal Server Error", {}, None))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES)
        self.assertIn("500", str(ctx.exception))

    def test_unauthorized_points_at_the_api_key(self):
        self.raise_with(HTTPError(URL, 401, "Unauthorized", {}, None))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES)
        message = str(ctx.exception)
        self.assertIn("NATIV_API_KEY", message)
        self.assertIn("올바르지 않습니다", message)

    def test_sends_bearer_token(self):
        captured = {}
        self.respond_with({"choices": [{"message": {"content": "x"}}]}, captured)
        gitmsg.complete(URL, "m1", MESSAGES, api_key="test-key")
        self.assertEqual(captured["auth"], "Bearer test-key")

    def test_key_redacted_from_error_body(self):
        # 서버가 디버그 트레이스에 요청 헤더를 반사하는 최악의 경우를
        # 가정한다. 본문에 키가 그대로 담겨 있어도 메시지에는 남으면 안 된다.
        body = (
            '{"detail":"debug trace - Authorization: Bearer %s"}' % FAKE_KEY
        ).encode("utf-8")
        self.raise_with(HTTPError(URL, 500, "Internal Server Error", {}, io.BytesIO(body)))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES, api_key=FAKE_KEY)
        message = str(ctx.exception)
        self.assertNotIn(FAKE_KEY, message)
        self.assertIn("***", message)

    def test_api_key_never_leaks_in_error_messages(self):
        errors = [
            HTTPError(URL, 401, "Unauthorized", {}, None),
            HTTPError(URL, 500, "Internal Server Error", {}, None),
            URLError(ConnectionRefusedError(61, "Connection refused")),
            socket.timeout(),
            URLError(socket.timeout()),
        ]
        for error in errors:
            self.raise_with(error)
            with self.assertRaises(gitmsg.NativError) as ctx:
                gitmsg.complete(URL, "m1", MESSAGES, api_key=FAKE_KEY)
            self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_key_never_leaks_when_it_straddles_the_200_char_truncation_boundary(self):
        # 200자로 자르기 전에 먼저 마스킹해야 한다. 순서가 바뀌면(자르기 먼저,
        # 마스킹 나중) 200번째 문자 경계에 걸친 키는 .replace()가 찾지 못해
        # 앞부분 조각이 그대로 새어나간다 — --url/GITMSG_URL을 공격자가
        # 제어하면 패딩을 조금씩 밀어가며 키 전체를 복원할 수 있다.
        canary = "sk-test-canary-ABCDEFGHIJKLMNO"  # 30자
        pad = "A" * 180
        body = (pad + canary).encode("utf-8")
        # 자르기를 먼저 하는 버그 버전이라면 body[:200]의 마지막 20글자가 샌다.
        leaked_fragment_if_buggy = canary[:200 - len(pad)]

        self.raise_with(HTTPError(URL, 500, "Internal Server Error", {}, io.BytesIO(body)))
        with self.assertRaises(gitmsg.NativError) as ctx:
            gitmsg.complete(URL, "m1", MESSAGES, api_key=canary)
        message = str(ctx.exception)
        self.assertNotIn(canary, message)
        self.assertNotIn(leaked_fragment_if_buggy, message)
        self.assertIn("***", message)


if __name__ == "__main__":
    unittest.main()
