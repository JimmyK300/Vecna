import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin, urlparse

from fastapi import FastAPI, Request
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



web_dir = Path.cwd() / constant.FRONTEND_DIST_DIR
if not (web_dir / "dist").exists():
    for candidate in [
        Path.cwd() / "workspace" / constant.FRONTEND_DIST_DIR,
        Path(__file__).resolve().parents[4] / "workspace" / constant.FRONTEND_DIST_DIR,
    ]:
        if (candidate / "dist").exists():
            web_dir = candidate
            break

if (web_dir / "dist").exists():
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
