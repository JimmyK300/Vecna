import importlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx


search_api = importlib.import_module("aic51.packages.webui.backend.search")
file_api = importlib.import_module("aic51.packages.webui.backend.file")
core_api = importlib.import_module("aic51.packages.webui.backend.core")


class BackendEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, method, path, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    async def test_cancel_search_endpoint_sets_active_event(self):
        event = search_api.begin_search_session()
        self.addCleanup(setattr, search_api, "current_search_cancel_event", None)
        response = await self.request(search_api.app, "POST", "/api/cancel_search")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(event.is_set())

    async def test_new_search_supersedes_previous_one(self):
        previous = search_api.begin_search_session()
        current = search_api.begin_search_session()
        self.addCleanup(setattr, search_api, "current_search_cancel_event", None)
        self.assertTrue(previous.is_set())
        self.assertFalse(current.is_set())

    async def test_collection_aliases_route_to_matching_searcher(self):
        first = Mock()
        second = Mock()
        for searcher in (first, second):
            searcher.search_multimodal.return_value = {"results": [], "total": 0, "offset": 0}
            searcher.target_features = []
            searcher.support_ocr = False
            searcher.support_asr = False
        old_internal = search_api.internal.copy()
        search_api.internal.update(searchers={"workspace": first, "workspace2": second}, searcher=first)
        self.addCleanup(search_api.internal.clear)
        self.addCleanup(search_api.internal.update, old_internal)
        self.addCleanup(setattr, search_api, "current_search_cancel_event", None)
        with patch.object(search_api, "process_searcher_results", return_value={"frames": [], "total": 0}), \
             patch.object(search_api, "process_search_results", side_effect=lambda _request, result: result), \
             patch.object(search_api, "build_search_trace", return_value={}):
            for alias, expected, other in (("testcol1", first, second), ("testcol2", second, first)):
                expected.search_multimodal.reset_mock()
                other.search_multimodal.reset_mock()
                response = await self.request(search_api.app, "GET", "/api/search_multimodal", params={"q": "car", "collection": alias})
                self.assertEqual(response.status_code, 200, response.text)
                expected.search_multimodal.assert_called_once()
                other.search_multimodal.assert_not_called()

    async def test_map_keyframes_endpoint_uses_pts_and_raw_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "V001.csv"
            csv_path.write_text("n,pts_time,fps,frame_idx\n1,1.25,25,25\n2,2.50,25,50\n", encoding="utf-8")
            with patch.object(file_api, "_get_map_keyframes_path", return_value=csv_path):
                response = await self.request(file_api.app, "GET", "/api/video/map-keyframes/V001")
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item["raw_idx"] for item in response.json()["keyframes"]], [25, 50])
                self.assertEqual(response.json()["keyframes"][1]["pts_time"], 2.5)
                maximum = await self.request(file_api.app, "GET", "/api/video/max-frame/V001")
                self.assertEqual(maximum.json()["max_frame"], 50)

    async def test_map_keyframes_cache_refreshes_after_csv_update(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "V001.csv"
            csv_path.write_text("n,pts_time,fps,frame_idx\n1,1.25,25,25\n", encoding="utf-8")
            with patch.object(file_api, "_get_map_keyframes_path", return_value=csv_path):
                self.assertEqual(file_api._load_map_keyframes_data("V001")[0]["raw_idx"], 25)
                csv_path.write_text("n,pts_time,fps,frame_idx\n1,2.50,25,50\n", encoding="utf-8")
                stat = csv_path.stat()
                os.utime(csv_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
                self.assertEqual(file_api._load_map_keyframes_data("V001")[0]["raw_idx"], 50)

    async def test_transcript_cache_is_bounded_and_lru(self):
        previous = file_api._TRANSCRIPT_CACHE.copy()
        self.addCleanup(file_api._TRANSCRIPT_CACHE.clear)
        self.addCleanup(file_api._TRANSCRIPT_CACHE.update, previous)
        file_api._TRANSCRIPT_CACHE.clear()
        for index in range(file_api._TRANSCRIPT_CACHE_MAXSIZE):
            file_api._cache_transcript(f"V{index}", [{"text": str(index)}])
        # A recent read keeps the oldest key in cache.
        file_api._TRANSCRIPT_CACHE.move_to_end("V0")
        file_api._cache_transcript("new", [])
        self.assertEqual(len(file_api._TRANSCRIPT_CACHE), file_api._TRANSCRIPT_CACHE_MAXSIZE)
        self.assertIn("V0", file_api._TRANSCRIPT_CACHE)
        self.assertNotIn("V1", file_api._TRANSCRIPT_CACHE)

    async def test_dres_proxy_preserves_upstream_error_status(self):
        for status in (401, 429, 502):
            upstream = SimpleNamespace(status_code=status, content=b'{"description":"failure"}', headers={"Content-Type": "application/json"})
            with patch.object(core_api.requests, "request", return_value=upstream) as request_mock:
                response = await self.request(core_api.app, "GET", "/api/dres-proxy/api/v2/user?session=sample", headers={"x-dres-server-url": "http://localhost:9999"})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["description"], "failure")
                request_mock.assert_called_once()
                self.assertEqual(request_mock.call_args.kwargs["url"], "http://localhost:9999/api/v2/user?session=sample")


if __name__ == "__main__":
    unittest.main()
