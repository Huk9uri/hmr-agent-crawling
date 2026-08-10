import unittest

import requests

from hmr_order_collection.http import HttpClient, HttpResponseError, parse_json


_SECRET_URL = "https://api-user:api-password@example.test/orders?access_token=top-secret#fragment"


class _FailingSession:
    def request(self, *args, **kwargs):
        raise requests.ConnectionError(f"connection refused: {_SECRET_URL}")


class HttpErrorSafetyTests(unittest.TestCase):
    def test_request_exception_redacts_query_fragment_and_user_info(self):
        client = HttpClient(session=_FailingSession(), max_attempts=1)

        with self.assertRaises(HttpResponseError) as context:
            client.request("GET", _SECRET_URL)

        self.assertNotIn("top-secret", str(context.exception))
        self.assertNotIn("api-user", str(context.exception))
        self.assertNotIn("fragment", str(context.exception))
        self.assertIsNone(context.exception.__cause__)

    def test_json_parse_error_redacts_query_fragment_and_user_info(self):
        response = requests.Response()
        response.url = _SECRET_URL
        response._content = b"not-json"

        with self.assertRaises(HttpResponseError) as context:
            parse_json(response)

        self.assertNotIn("top-secret", str(context.exception))
        self.assertNotIn("api-user", str(context.exception))
        self.assertNotIn("fragment", str(context.exception))


if __name__ == "__main__":
    unittest.main()
