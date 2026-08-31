import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import aic51.packages.constant as constant
import torch
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.search import Searcher, SearchCancelledException
from aic51.packages.search.traceability import build_search_trace
from aic51.packages.search.utils import Query as ParsedQuery
from aic51.packages.utils import get_device

from .utils import create_app, process_searcher_results, process_search_results


def setup_searcher():
    collection_name = GlobalConfig.get("backends", "search", "collection") or "milvus"
    do_gpu = GlobalConfig.get("backends", "search", "gpu") or False
    device = get_device(do_gpu)
    return Searcher(collection_name, device)


internal = {}
active_search_lock = threading.Lock()
current_search_cancel_event: threading.Event | None = None


def begin_search_session() -> threading.Event:
    global current_search_cancel_event
    with active_search_lock:
        if current_search_cancel_event is not None and not current_search_cancel_event.is_set():
            logger.info("search backend: Superseding / cancelling active previous search.")
            current_search_cancel_event.set()
        cancel_event = threading.Event()
        current_search_cancel_event = cancel_event
        return cancel_event


def cancel_active_search_session():
    global current_search_cancel_event
    with active_search_lock:
        if current_search_cancel_event is not None and not current_search_cancel_event.is_set():
            logger.info("search backend: Received cancel signal, cancelling active search.")
            current_search_cancel_event.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    internal["searcher"] = setup_searcher()
    yield


app = create_app(lifespan=lifespan)


@app.get(constant.HEALTH_ENDPOINT)
async def health():
    if "searcher" in internal:
        return JSONResponse(status_code=200, content=jsonable_encoder({constant.MESSAGE_KEY: "alive"}))
    return JSONResponse(status_code=500, content=jsonable_encoder({constant.MESSAGE_KEY: "dead"}))


@app.post(constant.CANCEL_SEARCH_ENDPOINT)
@app.get(constant.CANCEL_SEARCH_ENDPOINT)
async def cancel_search_endpoint():
    cancel_active_search_session()
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.MESSAGE_KEY: "search cancel signal received"}),
    )


@app.get(constant.SEARCH_MULTIMODAL_ENDPOINT)
async def search_multimodal(
    request: Request,
    q: str,
    offset: int = 0,
    limit: int = 50,
    target_features: str = "",
    nprobe: int = 32,
    temporal_k: int = 2000,
    ocr_weight: float = 0.5,
    asr_weight: float = 0,
    ocr_alpha: float = 0.5,
    asr_alpha: float = 0.5,
    max_interval: int = 1000,
    selected: str | None = None,
    auto_translate: bool = False,
    en_to_vi_translate: bool = False,
    include_videos: str = "",
    exclude_videos: str = "",
):
    if "searcher" not in internal:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )

    searcher = internal["searcher"]
    target_features_list = [f.strip() for f in target_features.split(",") if f.strip()]

    cancel_event = begin_search_session()

    async def monitor_disconnect():
        try:
            while not cancel_event.is_set():
                if await request.is_disconnected():
                    logger.info("search backend: Client disconnected, cancelling search.")
                    cancel_event.set()
                    break
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    monitor_task = asyncio.create_task(monitor_disconnect())

    try:
        searcher_res = await asyncio.to_thread(
            searcher.search_multimodal,
            q,
            offset,
            limit,
            target_features_list,
            nprobe=nprobe,
            temporal_k=temporal_k,
            ocr_weight=ocr_weight,
            asr_weight=asr_weight,
            ocr_alpha=ocr_alpha,
            asr_alpha=asr_alpha,
            max_interval=max_interval,
            selected=selected,
            auto_translate=auto_translate,
            en_to_vi_translate=en_to_vi_translate,
            include_videos=include_videos,
            exclude_videos=exclude_videos,
            cancel_event=cancel_event,
        )
    except SearchCancelledException:
        logger.info("search backend: Search multimodal was cancelled.")
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({
                constant.MESSAGE_KEY: "search cancelled",
                "canceled": True,
                "frames": [],
                "total": 0,
                "offset": offset,
            }),
        )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_multimodal errors"}),
        )
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    if cancel_event.is_set():
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({
                constant.MESSAGE_KEY: "search cancelled",
                "canceled": True,
                "frames": [],
                "total": 0,
                "offset": offset,
            }),
        )

    parsed_query = ParsedQuery(q)
    if parsed_query.simple:
        query_mode = "browse"
    elif parsed_query.temporal:
        query_mode = "temporal"
    else:
        query_mode = "similarity"

    collection_name = GlobalConfig.get("backends", "search", "collection") or "milvus"
    traceability_features = []
    trace_ocr_weight = max(0.0, min(1.0, float(ocr_weight)))
    trace_asr_weight = max(0.0, min(1.0 - trace_ocr_weight, float(asr_weight)))
    trace_visual_weight = 1.0 - trace_ocr_weight - trace_asr_weight
    if query_mode != "browse" and trace_visual_weight > 0:
        traceability_features.extend(
            feature
            for feature in target_features_list
            if feature and feature in searcher.target_features
        )
    if query_mode != "browse" and searcher.support_ocr and trace_ocr_weight > 0:
        traceability_features.append(GlobalConfig.get("searcher", "ocr", "ocr_field") or "ocr")
        ocr_dense_field = GlobalConfig.get("searcher", "ocr", "ocr_dense_field")
        if ocr_dense_field:
            traceability_features.append(ocr_dense_field)
    if query_mode != "browse" and searcher.support_asr and trace_asr_weight > 0:
        traceability_features.append(GlobalConfig.get("searcher", "asr", "asr_field") or "asr")
        asr_dense_field = GlobalConfig.get("searcher", "asr", "asr_dense_field")
        if asr_dense_field:
            traceability_features.append(asr_dense_field)
    traceability_features = sorted(set(traceability_features))

    response = process_searcher_results(
        searcher_res,
        include_traceability=True,
        work_dir=Path.cwd(),
        traceability_collection=collection_name,
        traceability_features=traceability_features,
    )
    response = process_search_results(request, response)

    response[constant.RESULT_PARAMS_KEY] = {
        "limit": limit,
        "target_features": target_features,
        "nprobe": nprobe,
        "temporal_k": temporal_k,
        "ocr_weight": ocr_weight,
        "asr_weight": asr_weight,
        "ocr_alpha": ocr_alpha,
        "asr_alpha": asr_alpha,
        "max_interval": max_interval,
        "auto_translate": auto_translate,
        "en_to_vi_translate": en_to_vi_translate,
        "include_videos": include_videos,
        "exclude_videos": exclude_videos,
    }
    response.update(
        build_search_trace(
            Path.cwd(),
            collection_name=collection_name,
            query_mode=query_mode,
            target_features=target_features_list,
            available_target_features=searcher.target_features,
            nprobe=nprobe,
            temporal_k=temporal_k,
            ocr_weight=ocr_weight,
            asr_weight=asr_weight,
            ocr_alpha=ocr_alpha,
            asr_alpha=asr_alpha,
            max_interval=max_interval,
            auto_translate=auto_translate,
            en_to_vi_translate=en_to_vi_translate,
            support_ocr=searcher.support_ocr,
            support_asr=searcher.support_asr,
        )
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.MESSAGE_KEY: "success", **response}),
    )


@app.get(constant.SEARCH_IMAGE_ENDPOINT)
async def search_image(
    request: Request,
    id: str,
    offset: int = 0,
    limit: int = 50,
    target_features: str = "",
    nprobe: int = 32,
    temporal_k: int = 2000,
    ocr_weight: float = 0.5,
    asr_weight: float = 0,
    max_interval: int = 1000,
):
    if "searcher" not in internal:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )

    searcher = internal["searcher"]
    target_features_list = target_features.split(",")

    cancel_event = begin_search_session()

    async def monitor_disconnect():
        try:
            while not cancel_event.is_set():
                if await request.is_disconnected():
                    logger.info("search backend: Client disconnected, cancelling image search.")
                    cancel_event.set()
                    break
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    monitor_task = asyncio.create_task(monitor_disconnect())

    try:
        searcher_res = await asyncio.to_thread(
            searcher.search_image,
            id,
            offset,
            limit,
            target_features_list,
            nprobe=nprobe,
            cancel_event=cancel_event,
        )
    except SearchCancelledException:
        logger.info("search backend: Search image was cancelled.")
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({
                constant.MESSAGE_KEY: "search cancelled",
                "canceled": True,
                "frames": [],
                "total": 0,
                "offset": offset,
            }),
        )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_image errors"}),
        )
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    if cancel_event.is_set():
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({
                constant.MESSAGE_KEY: "search cancelled",
                "canceled": True,
                "frames": [],
                "total": 0,
                "offset": offset,
            }),
        )

    response = process_searcher_results(searcher_res)
    response = process_search_results(request, response)

    response[constant.RESULT_PARAMS_KEY] = {
        "limit": limit,
        "target_features": target_features,
        "nprobe": nprobe,
        "temporal_k": temporal_k,
        "ocr_weight": ocr_weight,
        "max_interval": max_interval,
    }
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.MESSAGE_KEY: "success", **response}),
    )


# === (THÊM MỚI) API /api/expand_query — sinh 3 biến thể query bằng Groq LLM ===
@app.post(constant.EXPAND_QUERY_ENDPOINT)
async def expand_query_endpoint(request: Request):
    """API sinh 3 biến thể ngữ nghĩa (sát nghĩa / vai trò / nơi chốn) bằng Groq LLM.

    Request JSON: {"query": "cô gái nấu ăn"}
    Response JSON: {"variants": ["con gái nấu", "..."], "error": "..."}
    """
    try:
        data = await request.json()
        query_text = data.get("query", "").strip() if data else ""
        if not query_text:
            return JSONResponse(status_code=200, content={"variants": []})

        searcher = internal.get("searcher")
        if not searcher or not getattr(searcher, "_llm_expander", None) or not searcher._llm_expander.is_available:
            return JSONResponse(
                status_code=200,
                content={
                    "variants": [],
                    "error": "GROQ_API_KEY is not configured in workspace/config.yaml (or GROQ_API_KEY environment variable)",
                },
            )

        detailed = searcher.expand_query_detailed(query_text)
        variants = searcher.expand_query(query_text)
        if not variants:
            return JSONResponse(
                status_code=200,
                content={"variants": [], "detailed": {}, "error": "Groq API did not return valid variants (check API Key)"},
            )

        return JSONResponse(status_code=200, content={"variants": variants, "detailed": detailed})
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=200,
            content={"variants": [], "error": f"LLM Error: {str(e)}"},
        )



@app.get(constant.TARGET_FEATURES_ENDPOINT)
async def target_features():
    if "searcher" not in internal:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )

    searcher = internal["searcher"]
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.TARGET_FEATURES_KEY: searcher.target_features}),
    )
