import unittest

from starlette.requests import Request

from aic51.packages.webui.backend.core import _public_redirect_url
from aic51.packages.webui.backend.utils import process_frame_info


def make_request(path: str, host: str = "100.92.155.118:6900") -> Request:
    host_name, port = host.rsplit(":", 1)
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": (host_name, int(port)),
            "client": ("127.0.0.1", 50000),
            "method": "GET",
            "path": path,
            "query_string": b"q=tail+gate",
            "headers": [(b"host", host.encode())],
        }
    )


class WebUiRemoteTests(unittest.TestCase):
    def test_internal_search_redirect_uses_public_request_host(self):
        request = make_request("/api/search_multimodal")

        result = _public_redirect_url(
            request,
            "http://127.0.0.1:1337/api/health?q=tail+gate",
        )

        self.assertEqual(
            result,
            "http://100.92.155.118:1337/api/search_multimodal?q=tail+gate",
        )

    def test_internal_video_uri_is_rewritten_to_request_origin(self):
        request = make_request("/api/search_multimodal")
        frame = {"video_uri": "http://127.0.0.1:4200/api/files/L21_V002"}

        process_frame_info(request, frame)

        self.assertEqual(
            frame["video_uri"],
            "http://100.92.155.118:6900/api/files/L21_V002",
        )


if __name__ == "__main__":
    unittest.main()
