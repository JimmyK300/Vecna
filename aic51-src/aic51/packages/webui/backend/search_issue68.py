"""Issue #68 promotion layer for the existing Vecna search FastAPI app.

Imports the normal search app unchanged, then registers one explicit pure-ASR
operator endpoint. Normal multimodal/image routes and defaults are untouched.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.search.asr_operator import search_asr_operator

from .search import app, internal
from .utils import process_search_results, process_searcher_results


@app.get("/api/search_asr_operator")
async def search_asr_operator_endpoint(
    request: Request,
    q: str,
    sentence_level: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    nprobe: int = Query(default=32, ge=1),
    include_videos: str = "",
    exclude_videos: str = "",
):
    """Pure ASR BM25 operator search with optional sentence grouping.

    sentence_level=False is intentionally the default. The grouped arm is an
    explicit operator opt-in and never calls/changes search_multimodal.
    """
    searcher = internal.get("searcher")
    if searcher is None:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )
    if not getattr(searcher, "support_asr", False):
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder({constant.MESSAGE_KEY: "ASR search is not enabled"}),
        )

    try:
        searcher_res = await asyncio.to_thread(
            search_asr_operator,
            searcher,
            q,
            sentence_level=sentence_level,
            offset=offset,
            limit=limit,
            nprobe=nprobe,
            include_videos=include_videos,
            exclude_videos=exclude_videos,
        )
    except Exception as exc:
        logger.exception(exc)
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_asr_operator errors"}),
        )

    collection_name = GlobalConfig.get("backends", "search", "collection") or "milvus"
    asr_field = searcher_res.get("asr_field") or getattr(searcher, "_asr_name", None)
    response = process_searcher_results(
        searcher_res,
        include_traceability=True,
        work_dir=Path.cwd(),
        traceability_collection=collection_name,
        traceability_features=[asr_field] if asr_field else [],
    )
    response = process_search_results(request, response)

    for frame, record in zip(response.get("frames", []), searcher_res.get("results", [])):
        group = record.get("sentence_group")
        if group:
            frame["sentence_group"] = group

    response[constant.RESULT_PARAMS_KEY] = {
        "operator": "asr",
        "sentence_level": bool(sentence_level),
        "nprobe": nprobe,
        "include_videos": include_videos,
        "exclude_videos": exclude_videos,
        "exposure_depth": searcher_res.get("exposure_depth"),
        "asr_field": asr_field,
    }
    response["operator_mode"] = "sentence" if sentence_level else "raw"
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({constant.MESSAGE_KEY: "success", **response}),
    )
