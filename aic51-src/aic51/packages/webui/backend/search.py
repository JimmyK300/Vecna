from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.search import Searcher
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    internal["searcher"] = setup_searcher()

    yield


app = create_app(lifespan=lifespan)


@app.get(constant.HEALTH_ENDPOINT)
async def health():
    if "searcher" in internal:
        return JSONResponse(status_code=200, content=jsonable_encoder({constant.MESSAGE_KEY: "alive"}))
    else:
        return JSONResponse(status_code=500, content=jsonable_encoder({constant.MESSAGE_KEY: "dead"}))


@app.get(constant.SEARCH_MULTIMODAL_ENDPOINT)
async def search_multimodal(
    request: Request,
    q: str,
    offset: int = 0,
    limit: int = 50,
    target_features: str = "",
    nprobe: int = 32,
    temporal_k: int = 10000,
    ocr_weight: float = 0.5,
    asr_weight: float = 0,
    max_interval: int = 1000,
    selected: str | None = None,
    auto_translate: bool = False,
    en_to_vi_translate: bool = False,
):
    if "searcher" not in internal:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )

    searcher = internal["searcher"]
    target_features_list = target_features.split(",")

    try:
        searcher_res = searcher.search_multimodal(
            q,
            offset,
            limit,
            target_features_list,
            nprobe=nprobe,
            temporal_k=temporal_k,
            ocr_weight=ocr_weight,
            asr_weight=asr_weight,
            max_interval=max_interval,
            selected=selected,
            auto_translate=auto_translate,
            en_to_vi_translate=en_to_vi_translate,
        )
    except Exception as e:
        logger.exception(e)

        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_multimodal errors"}),
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
    if query_mode != "browse" and searcher.support_asr and trace_asr_weight > 0:
        traceability_features.append(GlobalConfig.get("searcher", "asr", "asr_field") or "asr")
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
        "max_interval": max_interval,
        "auto_translate": auto_translate,
        "en_to_vi_translate": en_to_vi_translate,
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
    temporal_k: int = 10000,
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

    try:
        searcher_res = searcher.search_image(
            id,
            offset,
            limit,
            target_features_list,
            nprobe=nprobe,
        )
    except Exception as e:
        logger.exception(e)

        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_image errors"}),
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
