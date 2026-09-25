import asyncio
import logging
import json
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin, urlparse

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import requests

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger

from .request import CRequestPool, GetRequest
from .utils import create_app

SEARCH_SERVERS = GlobalConfig.get("backends", "core", "search_proxy", "servers") or []
SEARCH_REQUEST_TIMEOUT = GlobalConfig.get("backends", "core", "search_proxy", "request_timeout")
SEARCH_MAX_CREQUESTS = int(GlobalConfig.get("backends", "core", "search_proxy", "max_concurrent_requests") or 1)

FILE_SERVERS = GlobalConfig.get("backends", "core", "file_proxy", "servers") or []
FILE_REQUEST_TIMEOUT = GlobalConfig.get("backends", "core", "search_proxy", "request_timeout")
FILE_MAX_REQUESTS = int(GlobalConfig.get("backends", "core", "file_proxy", "max_concurrent_requests") or 1)

TARGET_FEATURES_SYNC_INTEVAL = int(GlobalConfig.get("backends", "core", "search_proxy", "sync_interval") or 15)

internal = {}
target_features_lock = asyncio.Lock()


async def sync_target_features():
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=5, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    def _fetch_target_features(url: str, timeout):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.ok:
                return resp.json()
        except Exception:
            return None
        return None

    while True:
        logger.info("CORE: Syncing target_features")
        async with target_features_lock:
            target_features = set()
            try:
                for ss in SEARCH_SERVERS:
                    endpoint = urljoin(ss["host"], constant.TARGET_FEATURES_ENDPOINT)
                    data = await asyncio.to_thread(_fetch_target_features, endpoint, SEARCH_REQUEST_TIMEOUT)
                    if data and constant.TARGET_FEATURES_KEY in data:
                        target_features.update(data[constant.TARGET_FEATURES_KEY])
            except Exception as e:
                logger.exception(e)
                target_features = set()

            internal["target_features"] = list(target_features)

        await asyncio.sleep(TARGET_FEATURES_SYNC_INTEVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = asyncio.ensure_future(sync_target_features())

    yield

    sync_task.cancel()


app = create_app(lifespan=lifespan)


@app.get(constant.SEARCH_MULTIMODAL_ENDPOINT)
async def search_multimodal(
    request: Request,
):
    if len(SEARCH_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search function is not supported"}),
        )

    crequest = CRequestPool(SEARCH_MAX_CREQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], constant.HEALTH_ENDPOINT), params=request.query_params, timeout=SEARCH_REQUEST_TIMEOUT
        )
        for ss in SEARCH_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_multimodal errors"}),
        )


@app.get(constant.SEARCH_IMAGE_ENDPOINT)
async def search_image(
    request: Request,
):
    if len(SEARCH_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search function is not supported"}),
        )

    crequest = CRequestPool(SEARCH_MAX_CREQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], constant.HEALTH_ENDPOINT), params=request.query_params, timeout=SEARCH_REQUEST_TIMEOUT
        )
        for ss in SEARCH_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_image errors"}),
        )


# === (THÊM MỚI) Proxy cho API expand_query bằng Groq LLM ===
@app.post(constant.EXPAND_QUERY_ENDPOINT)
async def expand_query_proxy(request: Request):
    if len(SEARCH_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search function is not supported"}),
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    import requests as sync_requests

    for ss in SEARCH_SERVERS:
        try:
            target_url = urljoin(ss["host"], constant.EXPAND_QUERY_ENDPOINT)
            resp = sync_requests.post(
                target_url,
                json=body,
                timeout=SEARCH_REQUEST_TIMEOUT,
            )
            if resp.ok:
                return JSONResponse(status_code=resp.status_code, content=resp.json())
        except Exception:
            continue

    return JSONResponse(
        status_code=500,
        content=jsonable_encoder({constant.MESSAGE_KEY: "expand_query errors"}),
    )


@app.post(constant.CANCEL_SEARCH_ENDPOINT)
@app.get(constant.CANCEL_SEARCH_ENDPOINT)
async def cancel_search_proxy(request: Request):
    if len(SEARCH_SERVERS) == 0:
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({constant.MESSAGE_KEY: "no search servers"}),
        )

    import requests as sync_requests

    for ss in SEARCH_SERVERS:
        try:
            target_url = urljoin(ss["host"], constant.CANCEL_SEARCH_ENDPOINT)
            sync_requests.post(target_url, timeout=2.0)
        except Exception:
            continue

    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.MESSAGE_KEY: "search cancel signal sent"}),
    )


@app.get(constant.TARGET_FEATURES_ENDPOINT)
async def target_features():
    async with target_features_lock:
        if len(SEARCH_SERVERS) == 0:
            return JSONResponse(
                status_code=404,
                content=jsonable_encoder({constant.MESSAGE_KEY: "search function is not supported"}),
            )

        return JSONResponse(
            status_code=200,
            content=jsonable_encoder(
                {constant.MESSAGE_KEY: "success", constant.TARGET_FEATURES_KEY: internal["target_features"]}
            ),
        )


@app.get("/api/collections")
async def collections():
    collections_cfg = GlobalConfig.get("backends", "search", "collections") or {}
    items = []
    if isinstance(collections_cfg, dict):
        for alias, col_name in collections_cfg.items():
            is_b1 = ("1" in alias or "col1" in alias or ("workspace" in alias and "2" not in alias))
            label = "Batch 1 (L, S, M)" if is_b1 else "Batch 2 (N)"
            items.append({"alias": alias, "collection_name": col_name, "label": label})
    elif isinstance(collections_cfg, list):
        for col_name in collections_cfg:
            items.append({"alias": col_name, "collection_name": col_name, "label": col_name})
    else:
        col_name = GlobalConfig.get("backends", "search", "collection") or "milvus"
        items.append({"alias": col_name, "collection_name": col_name, "label": col_name})
    return JSONResponse(status_code=200, content={"collections": items, "default": items[0]["alias"] if items else "testcol1"})


@app.get(constant.FILE_INFO_ENDPOINT + "/{video_id}/{frame_id}")
async def frame_info(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"{constant.HEALTH_ENDPOINT}/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "frame_info errors"}),
        )


@app.get(constant.FILE_ENDPOINT + "/{video_id}/{frame_id}")
async def get_frame(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"{constant.HEALTH_ENDPOINT}/{video_id}/{frame_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_frame errors"}),
        )


@app.get("/api/keyframes/{video_id}/{frame_id}")
async def get_keyframe(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"{constant.HEALTH_ENDPOINT}/{video_id}/{frame_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_keyframe errors"}),
        )


@app.get("/api/thumbnails/{video_id}/{frame_id}")
async def get_thumbnail(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/thumbnails/{video_id}/{frame_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_thumbnail errors"}),
        )


CHUNK_SIZE = 1024 * 1024


@app.get(constant.FILE_ENDPOINT + "/{video_id}")
async def get_video(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"{constant.HEALTH_ENDPOINT}/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video errors"}),
        )


@app.get("/api/video/transcript/{video_id}")
async def get_video_transcript(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/transcript/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_transcript errors"}),
        )
    return JSONResponse(status_code=200, content=[])


@app.get("/api/video/keyframes/{video_id}")
async def get_video_keyframes(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/keyframes/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_keyframes errors"}),
        )
    return JSONResponse(status_code=200, content=[])


@app.get("/api/video/thumbnails/{video_id}")
async def get_video_thumbnails(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/thumbnails/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_thumbnails errors"}),
        )
    return JSONResponse(status_code=200, content=[])


@app.get("/api/frame/ocr/{video_id}/{frame_id}")
async def get_frame_ocr(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/frame/ocr/{video_id}/{frame_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_frame_ocr errors"}),
        )


@app.get("/api/video/map-keyframes/{video_id}")
async def get_video_map_keyframes(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/map-keyframes/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_map_keyframes errors"}),
        )


@app.get("/api/video/max-frame/{video_id}")
async def get_video_max_frame(request: Request, video_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/max-frame/{video_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_max_frame errors"}),
        )


@app.get("/api/video/map-keyframes-around/{video_id}/{frame_id}")
async def get_video_map_keyframes_around(request: Request, video_id: str, frame_id: str):
    if len(FILE_SERVERS) == 0:
        return JSONResponse(
            status_code=404,
            content=jsonable_encoder({constant.MESSAGE_KEY: "file function is not supported"}),
        )

    crequest = CRequestPool(FILE_MAX_REQUESTS)
    health_requests = [
        GetRequest(
            urljoin(ss["host"], f"/api/video/map-keyframes-around/{video_id}/{frame_id}"),
            params=request.query_params,
            timeout=FILE_MAX_REQUESTS,
        )
        for ss in FILE_SERVERS
    ]
    crequest.map(health_requests)

    try:
        for future in crequest.as_completed():
            res = future.result()
            if res and res.ok:
                crequest.cancel_all()

                parsed_url = urlparse(res.url)
                redirected_url = parsed_url._replace(path=request.url.path).geturl()
                return RedirectResponse(redirected_url)
    except:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "get_video_map_keyframes_around errors"}),
        )


@app.api_route("/api/dres-proxy/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def dres_proxy(request: Request, path: str):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    target_server = request.headers.get("x-dres-server-url") or request.query_params.get("dres_server") or "https://eventretrieval.one"
    target_server = str(target_server).rstrip("/")
    target_url = f"{target_server}/{path.lstrip('/')}"

    query_params = dict(request.query_params)
    query_params.pop("dres_server", None)
    if query_params:
        target_url = f"{target_url}?{urllib.parse.urlencode(query_params)}"

    body = await request.body()
    headers = {
        "User-Agent": "VECNA-DRES-Proxy/1.0",
    }
    if "content-type" in request.headers:
        headers["Content-Type"] = request.headers["content-type"]

    def _do_request():
        try:
            resp = requests.request(
                method=request.method,
                url=target_url,
                data=body if body else None,
                headers=headers,
                timeout=15,
            )
            return resp.status_code, resp.content, resp.headers.get("Content-Type", "application/json")
        except Exception as e:
            err_data = json.dumps({"status": False, "description": f"Proxy Error: {str(e)}"}).encode()
            return 502, err_data, "application/json"

    status_code, content, content_type = await asyncio.to_thread(_do_request)
    return Response(
        content=content,
        status_code=status_code,
        media_type=content_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


web_dir = Path.cwd() / constant.FRONTEND_DIST_DIR

if web_dir.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=web_dir / "dist/assets"),
        "assets",
    )
    app.mount(
        "/icon",
        StaticFiles(directory=web_dir / "dist/icon"),
        "icon",
    )

    @app.get("/{rest_of_path:path}")
    async def client_app():
        response = FileResponse(web_dir / "dist/index.html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
