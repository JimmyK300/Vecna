import io
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from PIL import Image

import aic51.packages.constant as constant
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger
from aic51.packages.search import Searcher
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
    temporal_k: int = 2000,
    ocr_weight: float = 0.5,
    asr_weight: float = 0,
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
            include_videos=include_videos,
            exclude_videos=exclude_videos,
        )
    except Exception as e:
        logger.exception(e)

        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_multimodal errors"}),
        )

    response = process_searcher_results(searcher_res)
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
        "include_videos": include_videos,
        "exclude_videos": exclude_videos,
    }
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


# === (THÊM MỚI) API tìm kiếm bằng ảnh upload + YOLO auto-crop ===
@app.post(constant.SEARCH_UPLOAD_IMAGE_ENDPOINT)
async def search_upload_image(
    request: Request,
    file: UploadFile = File(...),
    auto_crop: bool = Form(True),
    target_features: str = Form(""),
    offset: int = Form(0),
    limit: int = Form(50),
    nprobe: int = Form(32),
):
    if "searcher" not in internal:
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "searcher was not initialized"}),
        )

    searcher = internal["searcher"]

    if target_features:
        target_features_list = [t.strip() for t in target_features.split(",") if t.strip()]
    else:
        target_features_list = [f for f in searcher.target_features if f.startswith("image_")]

    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        searcher_res = searcher.search_by_image_upload(
            image,
            offset,
            limit,
            target_features_list,
            nprobe=nprobe,
            auto_crop=auto_crop,
        )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder({constant.MESSAGE_KEY: "search_upload_image errors"}),
        )

    response = process_searcher_results(searcher_res)
    response = process_search_results(request, response)

    response[constant.RESULT_PARAMS_KEY] = {
        "limit": limit,
        "target_features": target_features,
        "nprobe": nprobe,
        "auto_crop": auto_crop,
    }

    if "crop_meta" in searcher_res:
        response["crop_meta"] = searcher_res["crop_meta"]

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
