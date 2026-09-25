import os
import gc
import hashlib
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from typing import Callable, Optional

import numpy as np
from sympy import limit
import torch
from pymilvus import AnnSearchRequest, RRFRanker

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.index import MilvusDatabase
from aic51.packages.logger import logger

from . import constants
from .utils import Query
from sentence_transformers import CrossEncoder
import bisect
import json
from pathlib import Path


class SegmentClustering:
    """Gom các frame trong cùng segment (bản tin) lại, giống OpenCubee2."""
    def __init__(self, path="segment_map.json"):
        p = Path(path)
        if not p.exists():
            script_dir = Path(__file__).resolve().parent
            repo_root = script_dir.parents[3]
            candidates = [
                repo_root / path,
                repo_root / "workspace" / path,
                Path("workspace") / path,
            ]
            for candidate in candidates:
                if candidate.exists():
                    p = candidate
                    break

        self.map = json.load(open(p, encoding="utf-8")) if p.exists() else {}
        if not self.map:
            logger.warning("SegmentClustering: segment_map.json not found - clustering disabled")

    def seg_of(self, vid: str, fid: int) -> int:
        m = self.map.get(vid)
        if not m:
            return -1
        i = bisect.bisect_left(m["fids"], fid)
        if i < len(m["fids"]) and m["fids"][i] == fid:
            return m["segs"][i]
        return -1

    def diversify(self, results: list) -> list:
        """Lấy best frame (first-seen) per segment. Input đã sort theo score."""
        if not self.map:
            return results
        seen = set()
        reps = []
        for r in results:
            fid_full = r["entity"]["frame_id"]
            if "#" not in fid_full:
                continue
            vid, fid_s = fid_full.split("#", 1)
            try:
                fid = int(fid_s)
            except ValueError:
                continue
            segment_id = self.seg_of(vid, fid)
            key = (vid, segment_id if segment_id >= 0 else fid)
            if key in seen:
                continue
            seen.add(key)
            reps.append(r)
        return reps

class SearchCancelledException(Exception):
    """Raised when a search operation is cancelled by the client or superseded by a new search."""
    pass


def _check_cancelled(cancel_event):
    if cancel_event is None:
        return
    if callable(cancel_event):
        if cancel_event():
            raise SearchCancelledException("Search operation cancelled.")
    elif hasattr(cancel_event, "is_set") and cancel_event.is_set():
        raise SearchCancelledException("Search operation cancelled.")


def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


def _build_exact_regex(phrase: str) -> tuple[str, str]:
    """
    Builds compiled regex patterns for exact phrase matching with:
    - Safe escaping of special regex characters.
    - Word boundary checks (?<!\w) ... (?!\w).
    - Flexible spacing between words and between letter-number boundaries (e.g. "cau 3" vs "cau3", "vtv1" vs "vtv 1").
    Returns (pattern_exact, pattern_no_accent).
    """
    norm = re.sub(r"\s+", " ", phrase.strip().lower())
    norm_no_accent = remove_diacritics(norm)

    def _make_pattern(p_str: str) -> str:
        words = [w for w in p_str.split(" ") if w]
        if not words:
            return ""
        escaped_words = [re.escape(w) for w in words]
        pattern = r"\s+".join(escaped_words)
        # Allow optional spacing between letter and digit (e.g. "cau 3" -> "cau\s*3", "vtv1" -> "vtv\s*1")
        pattern = re.sub(r"(\w)\\s\+(\d)", r"\1\\s*\2", pattern)
        pattern = re.sub(r"(\d)\\s\+(\w)", r"\1\\s*\2", pattern)
        pattern = re.sub(r"([a-zA-Z\u00C0-\u024F\u1EA0-\u1EF9])(\d)", r"\1\\s*\2", pattern)
        pattern = re.sub(r"(\d)([a-zA-Z\u00C0-\u024F\u1EA0-\u1EF9])", r"\1\\s*\2", pattern)
        return r"(?<!\w)" + pattern + r"(?!\w)"

    return _make_pattern(norm), _make_pattern(norm_no_accent)


def check_exact_phrases(query_str: str, target_text: str, fallback_query: str = "") -> tuple[bool, int]:
    """
    Extracts double-quoted exact phrases from query_str or fallback_query (e.g. "câu 3").
    Returns (is_valid, phrase_count).
    If exact phrases exist, target_text must match them (case-insensitive, diacritic-insensitive, exact word boundaries).
    """
    phrases = re.findall(r'"([^"]+)"', query_str) if query_str else []
    if not phrases and fallback_query:
        phrases = re.findall(r'"([^"]+)"', fallback_query)

    phrases = [p.strip() for p in phrases if p.strip()]
    if not phrases:
        return True, 0

    if not target_text:
        return False, len(phrases)

    norm_target = re.sub(r"\s+", " ", str(target_text).lower())
    norm_target_no_accent = remove_diacritics(norm_target)

    for phrase in phrases:
        pat_exact, pat_no_accent = _build_exact_regex(phrase)
        if not pat_exact:
            continue
        try:
            matched = bool(
                re.search(pat_exact, norm_target)
                or (pat_no_accent and re.search(pat_no_accent, norm_target_no_accent))
            )
        except Exception:
            p_lower = phrase.lower()
            matched = (p_lower in norm_target) or (remove_diacritics(p_lower) in norm_target_no_accent)

        if not matched:
            return False, len(phrases)

    return True, len(phrases)


class BoundedLRUCache:
    """Thread-safe bounded LRU cache with eviction to prevent memory bloat."""
    def __init__(self, maxsize: int = 20):
        self.maxsize = maxsize
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            if key not in self._cache:
                return default
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def __contains__(self, key):
        with self._lock:
            return key in self._cache

    def __getitem__(self, key):
        with self._lock:
            if key not in self._cache:
                raise KeyError(key)
            self._cache.move_to_end(key)
            return self._cache[key]

    def __setitem__(self, key, value):
        self.set(key, value)

    def __len__(self):
        with self._lock:
            return len(self._cache)

    def clear(self):
        with self._lock:
            self._cache.clear()


_SHARED_EXTRACTORS = {}
_EXTRACTOR_LOCK = threading.Lock()


class Searcher(object):
    cache = BoundedLRUCache(maxsize=20)

    def __init__(self, collection_name: str, device: torch.device = torch.device("cpu")):
        self._database = MilvusDatabase(collection_name)
        try:
            desc = self._database._client.describe_collection(collection_name)
            self._collection_fields = {f.get("name") for f in desc.get("fields", []) if f.get("name")}
        except Exception:
            self._collection_fields = set()
        self._prepare_feature_extractors(device)
        segment_map_path = os.environ.get("SEGMENT_MAP_PATH", "segment_map.json")
        self._clustering = SegmentClustering(segment_map_path)
        try:
            self._single_search_cluster_frame_gap = max(
                0,
                int(os.environ.get("SINGLE_SEARCH_CLUSTER_FRAME_GAP", "150")),
            )
        except ValueError:
            logger.warning(
                "Invalid SINGLE_SEARCH_CLUSTER_FRAME_GAP; falling back to 150 frames"
            )
            self._single_search_cluster_frame_gap = 150
        try:
            self._single_search_cluster_similarity = min(
                1.0,
                max(
                    -1.0,
                    float(os.environ.get("SINGLE_SEARCH_CLUSTER_SIMILARITY", "0.95")),
                ),
            )
        except ValueError:
            logger.warning(
                "Invalid SINGLE_SEARCH_CLUSTER_SIMILARITY; falling back to 0.95"
            )
            self._single_search_cluster_similarity = 0.95

        configured_cluster_field = os.environ.get("SINGLE_SEARCH_CLUSTER_VECTOR_FIELD")
        if configured_cluster_field:
            self._single_search_cluster_vector_field = configured_cluster_field
        else:
            # The temporal branch used legacy CLIP. New collections use
            # SigLIP2, so select the first visual field the collection has.
            compatible_fields = (
                "image_clip_pe_l_14_336",
                "image_siglip2_so400m_378",
                "image_siglip_so400m_384",
                "qwen_vl",
            )
            self._single_search_cluster_vector_field = next(
                (field for field in compatible_fields if field in self._collection_fields),
                compatible_fields[0],
            )
        logger.info(
            "searcher [%s]: single-search visual clustering field=%s "
            "similarity>=%.3f frame_gap<=%d",
            collection_name,
            self._single_search_cluster_vector_field,
            self._single_search_cluster_similarity,
            self._single_search_cluster_frame_gap,
        )

    def to(self, device):
        self._device = torch.device(device)
        for e in self._extractors.values():
            e.to(device)

    def get(self, id):
        return self._database.get(id)

    @property
    def features_extractor(self):
        return list(self._extractors.keys())

    @property
    def target_features(self):
        return [name for name in self._features.keys() if not name.endswith("_dense")]

    @property
    def support_ocr(self):
        return self._ocr_name is not None

    @property
    def support_asr(self):
        return self._asr_name is not None

    def search_multimodal(
        self,
        q: str,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        nprobe: int = 8,
        temporal_k: int = 200,
        ocr_weight: float = 0.0,
        asr_weight: float = 0.0,
        ocr_alpha: float = 0.0,
        asr_alpha: float = 0.0,
        hybrid_alpha: float | None = None,
        max_interval: int = 1000,
        selected: str | None = None,
        auto_translate: bool = False,
        en_to_vi_translate: bool = False,
        include_videos: str = "",
        exclude_videos: str = "",
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        if hybrid_alpha is not None:
            ocr_alpha = hybrid_alpha
            asr_alpha = hybrid_alpha
        start_time = time.time()
        query = Query(
            q,
            auto_translate=auto_translate,
            en_to_vi_translate=en_to_vi_translate,
            include_videos=include_videos,
            exclude_videos=exclude_videos,
        )

        if query.simple:
            logger.info(f"searcher: get include_video_ids={query.include_video_ids}, exclude_video_ids={query.exclude_video_ids}")
            res = self._get_videos(query.include_video_ids, query.exclude_video_ids, offset, limit, selected, cancel_event=cancel_event)
        elif query.advance and not query.temporal:
            logger.info(f"searcher: advance_search query={query.data}")
            res = self._advance_search(
                query,
                offset,
                limit,
                target_features,
                ocr_weight=ocr_weight,
                asr_weight=asr_weight,
                ocr_alpha=ocr_alpha,
                asr_alpha=asr_alpha,
                nprobe=nprobe,
                cancel_event=cancel_event,
            )
        else:
            logger.info(f"searcher: temporal_search query={query.data}")
            res = self._temporal_search(
                query,
                offset,
                limit,
                target_features,
                ocr_weight=ocr_weight,
                asr_weight=asr_weight,
                ocr_alpha=ocr_alpha,
                asr_alpha=asr_alpha,
                nprobe=nprobe,
                temporal_k=temporal_k,
                max_interval=max_interval,
                cancel_event=cancel_event,
            )

        end_time = time.time()
        logger.info(f"searcher: Take {end_time - start_time:.4f} to extract and search")
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        gc.collect()
        return res

    def search_image(
        self,
        id: str,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        nprobe: int = 8,
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        record = self._database.get(id)
        if len(record) == 0:
            return {"results": [], "total": 0, "offset": 0}

        reqs = []
        subquery_limit = offset + limit

        for target_name in target_features:
            _check_cancelled(cancel_event)
            if target_name not in self._features:
                logger.warning(f"searcher: {target_name} is invalid feature")
                continue

            target_param = {
                "nprobe": nprobe,
                "metric_type": "COSINE",
            }

            m = self._features[target_name]
            image_embedding = record[0][self._database.process_field_name(target_name)]

            reqs.append(
                AnnSearchRequest(
                    data=[image_embedding],
                    anns_field=self._database.process_field_name(target_name),
                    param=target_param,
                    limit=subquery_limit,
                )
            )

        ranker = RRFRanker()

        if len(reqs) > 0:
            _check_cancelled(cancel_event)
            results = self._database.hybrid_search(
                reqs,
                ranker,
                offset,
                limit,
            )[0]
        else:
            results = []

        res = {
            "results": results,
            "total": self._database.get_size(),
            "offset": offset,
        }
        return res

    def _get_video_filter(self, include_video_ids: list[str] = []):
        clauses = []
        if include_video_ids and len(include_video_ids) > 0:
            inc_parts = [f'frame_id like "{x.strip()}%"' for x in include_video_ids if x.strip()]
            if len(inc_parts) == 1:
                clauses.append(inc_parts[0])
            elif len(inc_parts) > 1:
                clauses.append(f"({' || '.join(inc_parts)})")

        return " && ".join(clauses) if clauses else ""

    @staticmethod
    def _normalize_scores(score_map: dict) -> dict:
        """Max-scale normalize scores to [0, 1] range relative to the maximum raw score."""
        if not score_map:
            return {}
        scores = list(score_map.values())
        max_s = max(scores)
        if max_s <= 0:
            return {k: 0.0 for k in score_map}
        return {k: v / max_s for k, v in score_map.items()}

    @staticmethod
    def _text_field_from_index_field(field_name: str | None) -> str:
        if not field_name:
            return ""
        if field_name.endswith("_sparse"):
            return field_name.removesuffix("_sparse")
        if field_name.endswith("_dense"):
            return field_name.removesuffix("_dense")
        return field_name

    @staticmethod
    def _extract_query_texts(query_features: dict, feature_key: str) -> tuple[list[str], str]:
        if f"{feature_key}_translated" in query_features:
            query_list = query_features[f"{feature_key}_translated"]
        elif feature_key in query_features:
            query_list = query_features[feature_key]
        elif "text_vi" in query_features:
            query_list = [query_features["text_vi"]]
        elif "text_translated" in query_features:
            query_list = [query_features["text_translated"]]
        elif "text" in query_features:
            query_list = [query_features["text"]]
        else:
            query_list = []

        if isinstance(query_list, str):
            query_list = [query_list]

        raw_query = ""
        if f"{feature_key}_translated" in query_features:
            raw_value = query_features[f"{feature_key}_translated"]
            raw_query = raw_value[0] if isinstance(raw_value, list) and len(raw_value) > 0 else str(raw_value)
        elif feature_key in query_features:
            raw_value = query_features[feature_key]
            raw_query = raw_value[0] if isinstance(raw_value, list) and len(raw_value) > 0 else str(raw_value)
        elif "text_vi" in query_features:
            raw_query = query_features["text_vi"]
        elif "text_translated" in query_features:
            raw_query = query_features["text_translated"]
        elif "text" in query_features:
            raw_query = query_features["text"]

        return query_list, raw_query

    def _search_text_component(
        self,
        query_features: dict,
        feature_key: str,
        sparse_field: str | None,
        dense_field: str | None,
        dense_model_name: str | None,
        video_filter: str,
        subquery_limit: int,
        nprobe: int,
        hybrid_alpha: float,
        cancel_event: threading.Event | Callable = None,
    ) -> tuple[dict, dict]:
        _check_cancelled(cancel_event)
        query_list, raw_query = self._extract_query_texts(query_features, feature_key)
        if len(query_list) == 0:
            return {}, {}

        text_field = self._text_field_from_index_field(sparse_field or dense_field)
        sparse_raw_scores = {}
        dense_raw_scores = {}
        entity_data = {}
        all_frame_ids = set()

        dense_extractor = None
        if hybrid_alpha > 0.0 and dense_model_name and dense_model_name in self._extractors:
            dense_extractor = self._extractors[dense_model_name]["feature_extractor"]

        for query_text in query_list:
            _check_cancelled(cancel_event)
            # 1. Detect xem user có dùng ngoặc kép " " không
            has_exact = bool(re.findall(r'"([^"]+)"', query_text) or re.findall(r'"([^"]+)"', raw_query))
            
            # 2. Mở rộng pool nếu có ngoặc kép
            search_limit = max(subquery_limit * 5, 500) if has_exact else max(subquery_limit * 2, 100)
            
            # 3. BÓC dấu ngoặc kép ra trước khi ném cho Milvus và BGE-M3
            clean_query = re.sub(r'"', ' ', query_text).strip()
            query_input = clean_query if clean_query else query_text

            # === 1. SPARSE SEARCH (BM25) - GIỮ HARD FILTER (Chỉ chạy khi hybrid_alpha < 1.0) ===
            if sparse_field and hybrid_alpha < 1.0:
                _check_cancelled(cancel_event)
                search_results = self._database.search(
                    data=[query_input],
                    filter=video_filter,
                    offset=0,
                    limit=search_limit,
                    anns_field=sparse_field,
                    search_params={"metric_type": "BM25"},
                )
                if search_results and len(search_results) > 0:
                    for hit in search_results[0]:
                        fid = hit["entity"]["frame_id"]
                        doc_text = hit["entity"].get(text_field, "")
                        
                        if has_exact:
                            is_valid, phrase_count = check_exact_phrases(query_text, doc_text, fallback_query=raw_query)
                            if not is_valid:
                                continue # Vứt nếu không khớp exact phrase
                            boost = 1.5 # Boost điểm BM25
                        else:
                            boost = 1.0
                            
                        all_frame_ids.add(fid)
                        sparse_raw_scores[fid] = sparse_raw_scores.get(fid, 0) + hit["distance"] * boost
                        if fid not in entity_data:
                            entity_data[fid] = hit["entity"]

            # === 2. DENSE SEARCH (BGE-M3) (Chỉ chạy khi hybrid_alpha > 0.0) ===
            if dense_field and dense_extractor is not None and hybrid_alpha > 0.0:
                _check_cancelled(cancel_event)
                dense_query = dense_extractor.get_text_features([query_input])
                dense_query = np.asarray(dense_query).reshape(-1).tolist()

                _check_cancelled(cancel_event)
                search_results = self._database.search(
                    data=[dense_query],
                    filter=video_filter,
                    offset=0,
                    limit=search_limit,
                    anns_field=dense_field,
                    search_params={"nprobe": nprobe, "metric_type": "COSINE"},
                )
                if search_results and len(search_results) > 0:
                    for hit in search_results[0]:
                        fid = hit["entity"]["frame_id"]
                        doc_text = hit["entity"].get(text_field, "")
                        
                        if has_exact:
                            is_valid, phrase_count = check_exact_phrases(query_text, doc_text, fallback_query=raw_query)
                            if not is_valid:
                                continue  # Vứt nếu không khớp exact phrase
                            boost = 1.5
                        else:
                            boost = 1.0

                        all_frame_ids.add(fid)
                        dense_raw_scores[fid] = dense_raw_scores.get(fid, 0) + hit["distance"] * boost
                        if fid not in entity_data:
                            entity_data[fid] = hit["entity"]

        # Normalize và tính điểm Hybrid
        _check_cancelled(cancel_event)
        sparse_norm = self._normalize_scores(sparse_raw_scores) if hybrid_alpha < 1.0 else {}
        dense_norm = self._normalize_scores(dense_raw_scores) if hybrid_alpha > 0.0 else {}
        results = []
        for fid in all_frame_ids:
            if hybrid_alpha <= 0.0:
                final_score = sparse_norm.get(fid, 0.0)
            elif hybrid_alpha >= 1.0:
                final_score = dense_norm.get(fid, 0.0)
            else:
                final_score = hybrid_alpha * dense_norm.get(fid, 0.0) + (1.0 - hybrid_alpha) * sparse_norm.get(fid, 0.0)
            results.append(
                {
                    "entity": entity_data[fid],
                    "distance": final_score,
                    "scores": {
                        "final": round(final_score, 6),
                        "dense": round(dense_norm.get(fid, 0.0), 6),
                        "sparse": round(sparse_norm.get(fid, 0.0), 6),
                        "dense_raw": round(dense_raw_scores.get(fid, 0.0), 6),
                        "sparse_raw": round(sparse_raw_scores.get(fid, 0.0), 6),
                    },
                }
            )

        results.sort(key=lambda x: x["distance"], reverse=True)

        # Log top 5 để debug
        top_k = 5
        dense_status = dense_model_name if (hybrid_alpha > 0.0 and dense_field) else "SKIPPED (BM25 only)"
        sparse_status = sparse_field if hybrid_alpha < 1.0 else "SKIPPED (Dense only)"
        logger.info(f"[TOP {top_k}][{feature_key}] alpha={hybrid_alpha} dense_model={dense_status} sparse_field={sparse_status}")
        for i, item in enumerate(results[:top_k], 1):
            fid = item["entity"]["frame_id"]
            s = item["scores"]
            logger.info(
                f"[TOP {top_k}][{feature_key}] {i}. frame={fid} "
                f"final={s['final']} "
                f"dense={s['dense']} "
                f"bm25={s['sparse']} "
            )

        return results, entity_data

    @staticmethod
    def _filter_exclude_videos(results: list[dict], exclude_video_ids: list[str]) -> list[dict]:
        """Post-filtering helper to remove excluded videos from candidate or final search results."""
        if not exclude_video_ids or len(exclude_video_ids) == 0 or not results:
            return results
        excludes = [x.lower().strip() for x in exclude_video_ids if x.strip()]
        if not excludes:
            return results

        filtered_results = []
        for r in results:
            fid = str(r.get("entity", {}).get("frame_id", "")).lower()
            vid = fid.split("#")[0] if "#" in fid else fid
            if any(vid.startswith(ex) or fid.startswith(ex) or ex in vid for ex in excludes):
                continue
            if "time_line" in r and isinstance(r["time_line"], list):
                if any(
                    any(
                        tfid.lower().startswith(ex) or tfid.lower().split("#")[0].startswith(ex) or ex in tfid.lower()
                        for ex in excludes
                    )
                    for tfid in r["time_line"]
                ):
                    continue
            filtered_results.append(r)
        return filtered_results

    def _similarity_search(
        self,
        query_features: dict,
        video_ids: list[str],
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        ocr_weight: float = 0.0,
        asr_weight: float = 0.0,
        ocr_alpha: float = 0.0,
        asr_alpha: float = 0.0,
        hybrid_alpha: float | None = None,
        nprobe: int = 8,
        exclude_video_ids: list[str] = [],
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        if hybrid_alpha is not None:
            ocr_alpha = hybrid_alpha
            asr_alpha = hybrid_alpha
        ocr_weight = max(0, min(1, ocr_weight))
        asr_weight = max(0, min(1 - ocr_weight, asr_weight))
        ocr_alpha = max(0.0, min(1.0, float(ocr_alpha)))
        asr_alpha = max(0.0, min(1.0, float(asr_alpha)))
        video_filter = self._get_video_filter(video_ids)

        subquery_limit = offset + limit
        if exclude_video_ids and len(exclude_video_ids) > 0:
            subquery_limit = max(subquery_limit * 2, 300)

        if isinstance(target_features, list):
            target_features = [f.strip() for f in target_features if f and f.strip()]
        if not target_features:
            target_features = list(self._features.keys())

        # Score maps: frame_id -> raw score (per component)
        clip_raw_scores = {}  # frame_id -> sum of raw CLIP scores
        ocr_raw_scores = {}   # frame_id -> sum of raw OCR scores
        asr_raw_scores = {}   # frame_id -> sum of raw ASR scores
        all_frame_ids = set()
        # Store entity data for each frame_id
        entity_data = {}

        # 1. Visual Search (RRF across OpenCLIP, SigLIP, Qwen-VL)
        clip_weight = 1.0 - ocr_weight - asr_weight
        clip_req_count = 0
        clip_query_text = query_features.get("text_en", query_features.get("text", ""))
        visual_subquery_limit = max(subquery_limit * 2, 200)

        if clip_query_text and clip_weight > 0:
            text_embeddings = {}
            for target_name in target_features:
                _check_cancelled(cancel_event)
                if target_name not in self._features:
                    logger.warning(f"searcher: {target_name} is invalid feature")
                    continue

                m = self._features[target_name]
                if m not in text_embeddings:
                    _check_cancelled(cancel_event)
                    text_embeddings[m] = (
                        self._extractors[m]["feature_extractor"].get_text_features(clip_query_text).tolist()[0]
                    )

                _check_cancelled(cancel_event)
                search_results = self._database.search(
                    data=[text_embeddings[m]],
                    filter=video_filter,
                    offset=0,
                    limit=visual_subquery_limit,
                    anns_field=target_name,
                    search_params={"nprobe": nprobe, "metric_type": "COSINE"},
                )
                clip_req_count += 1

                if search_results and len(search_results) > 0:
                    for rank, hit in enumerate(search_results[0], start=1):
                        fid = hit["entity"]["frame_id"]
                        all_frame_ids.add(fid)
                        # Reciprocal Rank Fusion (RRF) with standard smoothing k=60
                        clip_raw_scores[fid] = clip_raw_scores.get(fid, 0.0) + (1.0 / (60.0 + rank))
                        if fid not in entity_data:
                            entity_data[fid] = hit["entity"]

        # 2. OCR Search (dense + BM25 hybrid)
        if self._ocr_name and ocr_weight > 0:
            _check_cancelled(cancel_event)
            ocr_dense_name = getattr(self, "_ocr_dense_name", None)
            ocr_dense_model = self._features.get(ocr_dense_name) if ocr_dense_name else None
            ocr_results, ocr_entities = self._search_text_component(
                query_features,
                "ocr",
                self._ocr_name,
                ocr_dense_name,
                ocr_dense_model,
                video_filter,
                subquery_limit,
                nprobe,
                ocr_alpha,
                cancel_event=cancel_event,
            )
            for hit in ocr_results:
                fid = hit["entity"]["frame_id"]
                all_frame_ids.add(fid)
                ocr_raw_scores[fid] = hit["distance"]
                entity_data[fid] = ocr_entities[fid]

        # 3. ASR Search (dense + BM25 hybrid)
        if self._asr_name and asr_weight > 0:
            _check_cancelled(cancel_event)
            asr_dense_name = getattr(self, "_asr_dense_name", None)
            asr_dense_model = self._features.get(asr_dense_name) if asr_dense_name else None
            asr_results, asr_entities = self._search_text_component(
                query_features,
                "asr",
                self._asr_name,
                asr_dense_name,
                asr_dense_model,
                video_filter,
                subquery_limit,
                nprobe,
                asr_alpha,
                cancel_event=cancel_event,
            )
            for hit in asr_results:
                fid = hit["entity"]["frame_id"]
                all_frame_ids.add(fid)
                asr_raw_scores[fid] = hit["distance"]
                entity_data[fid] = asr_entities[fid]

        # Normalize scores per component
        _check_cancelled(cancel_event)
        clip_norm = self._normalize_scores(clip_raw_scores)
        ocr_norm = self._normalize_scores(ocr_raw_scores)
        asr_norm = self._normalize_scores(asr_raw_scores)

        # Compute final weighted score for each frame
        results = []
        for fid in all_frame_ids:
            clip_s = clip_norm.get(fid, 0.0)
            ocr_s = ocr_norm.get(fid, 0.0)
            asr_s = asr_norm.get(fid, 0.0)

            final_score = clip_weight * clip_s + ocr_weight * ocr_s + asr_weight * asr_s

            results.append({
                "entity": entity_data[fid],
                "distance": final_score,
                "scores": {
                    "final": round(final_score, 6),
                    "clip": round(clip_s, 6),
                    "ocr": round(ocr_s, 6),
                    "asr": round(asr_s, 6),
                    "clip_raw": round(clip_raw_scores.get(fid, 0.0), 6),
                    "ocr_raw": round(ocr_raw_scores.get(fid, 0.0), 6),
                    "asr_raw": round(asr_raw_scores.get(fid, 0.0), 6),
                },
            })

        # Sort by final score descending
        results.sort(key=lambda x: x["distance"], reverse=True)

        # Fast Python Post-Filtering for Exclude Videos (Hybrid Strategy for Maximum Speed)
        results = self._filter_exclude_videos(results, exclude_video_ids)

        return results

    def _advance_search(
        self,
        query: Query,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        ocr_weight: float = 0.0,
        asr_weight: float = 0.0,
        ocr_alpha: float = 0.0,
        asr_alpha: float = 0.0,
        hybrid_alpha: float | None = None,
        nprobe: int = 8,
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        if hybrid_alpha is not None:
            ocr_alpha = hybrid_alpha
            asr_alpha = hybrid_alpha
        query_features = query.data[0]["features"]
        
        # Lấy raw query text để rerank
        raw_query = ""
        if "text" in query_features:
            val = query_features["text"]
            raw_query = val[0] if isinstance(val, list) and len(val) > 0 else str(val)
        elif "text_translated" in query_features:
            val = query_features["text_translated"]
            raw_query = val[0] if isinstance(val, list) and len(val) > 0 else str(val)

        if len(query.include_video_ids) > 0:
            results = self._similarity_search(
                query_features,
                query.include_video_ids,
                0,
                10000,
                target_features,
                ocr_weight=ocr_weight,
                asr_weight=asr_weight,
                ocr_alpha=ocr_alpha,
                asr_alpha=asr_alpha,
                nprobe=nprobe,
                exclude_video_ids=query.exclude_video_ids,
                cancel_event=cancel_event,
            )
            total = len(results)
        else:
            candidate_limit = (
                max(300, (offset + limit) * 3)
                if len(query.exclude_video_ids) > 0
                else max(200, offset + limit)
            )

            db_size = self._database.get_size()

            while True:
                _check_cancelled(cancel_event)
                results = self._similarity_search(
                    query_features,
                    [],
                    0,
                    candidate_limit,
                    target_features,
                    ocr_weight=ocr_weight,
                    asr_weight=asr_weight,
                    ocr_alpha=ocr_alpha,
                    asr_alpha=asr_alpha,
                    nprobe=nprobe,
                    exclude_video_ids=query.exclude_video_ids,
                    cancel_event=cancel_event,
                )

                if (
                    len(results) >= offset + limit
                    or candidate_limit >= db_size
                    or candidate_limit >= 10000
                ):
                    break

                candidate_limit = min(db_size, candidate_limit * 2)

            total = db_size

       # ====== RERANK Ở ĐÂY ======
        if self._reranker is not None and raw_query:
            _check_cancelled(cancel_event)
            rerank_k = max(limit, self._reranker_top_k)
            results = self._rerank_candidates(raw_query, results, top_k=rerank_k, cancel_event=cancel_event)

        # ====== ONLINE VISUAL DEDUP: same video + nearby + visually similar ======
        TOP_DIVERSE = min(len(results), max(200, (offset + limit) * 4))
        results_top = results[:TOP_DIVERSE]
        results_diverse = self._diversify_single_search_results(
            results_top,
            cancel_event=cancel_event,
        )
        results_remaining = results[TOP_DIVERSE:]
        results = results_diverse + results_remaining

        results = results[offset : offset + limit]
        res = {
            "results": results,
            "total": len(results_diverse) + len(results_remaining),
            "offset": offset,
        }
        return res

    def _diversify_single_search_results(
        self,
        results: list[dict],
        cancel_event: threading.Event | Callable = None,
    ) -> list[dict]:
        """Suppress lower-ranked nearby visual duplicates.

        Frames are compared only within the same video and temporal window.
        Missing vectors and Milvus failures fail open so clustering never
        destroys retrieval recall.
        """
        if not results:
            return []

        _check_cancelled(cancel_event)
        vector_field = self._database.process_field_name(
            self._single_search_cluster_vector_field
        )
        frame_ids = [
            str(result.get("entity", {}).get("frame_id", ""))
            for result in results
        ]
        frame_ids = [frame_id for frame_id in frame_ids if frame_id]

        try:
            rows = self._database.get_many(
                frame_ids,
                output_fields=["frame_id", vector_field],
            )
        except Exception as exc:
            logger.warning(
                "searcher: online single-search clustering disabled for this query; "
                "cannot fetch %s vectors: %s",
                vector_field,
                exc,
            )
            return results

        embeddings = {}
        for row in rows or []:
            frame_id = str(row.get("frame_id", ""))
            vector = row.get(vector_field)
            if not frame_id or vector is None:
                continue
            embedding = np.asarray(vector, dtype=np.float32)
            if embedding.ndim != 1 or embedding.size == 0:
                continue
            norm = float(np.linalg.norm(embedding))
            if not np.isfinite(norm) or norm <= 1e-9:
                continue
            embeddings[frame_id] = embedding / norm

        if not embeddings:
            logger.warning(
                "searcher: online single-search clustering skipped; no %s vectors returned",
                vector_field,
            )
            return results

        kept_by_video = {}
        diversified = []
        suppressed = 0

        # Input is already rank ordered, so the first frame accepted in each
        # visual neighbourhood is its highest-ranked representative.
        for result in results:
            _check_cancelled(cancel_event)
            frame_id = str(result.get("entity", {}).get("frame_id", ""))
            embedding = embeddings.get(frame_id)
            if "#" not in frame_id or embedding is None:
                diversified.append(result)
                continue

            video_id, frame_number_text = frame_id.split("#", 1)
            try:
                frame_number = int(frame_number_text)
            except ValueError:
                diversified.append(result)
                continue

            is_duplicate = False
            for kept_frame_number, kept_embedding in kept_by_video.get(video_id, []):
                if abs(frame_number - kept_frame_number) > self._single_search_cluster_frame_gap:
                    continue
                similarity = float(np.dot(embedding, kept_embedding))
                if similarity >= self._single_search_cluster_similarity:
                    is_duplicate = True
                    break

            if is_duplicate:
                suppressed += 1
                continue

            diversified.append(result)
            kept_by_video.setdefault(video_id, []).append((frame_number, embedding))

        logger.info(
            "searcher: online visual clustering kept=%d suppressed=%d field=%s "
            "similarity>=%.3f frame_gap<=%d",
            len(diversified),
            suppressed,
            vector_field,
            self._single_search_cluster_similarity,
            self._single_search_cluster_frame_gap,
        )
        return diversified

    def _rerank_candidates(self, query_text: str, candidates: list, top_k: int = 50, cancel_event: threading.Event | Callable = None) -> list:
        """
        Rerank only the selected candidate pool using BGE CrossEncoder.

        IMPORTANT:
        - Never mix reranker scores with hybrid scores.
        - Only candidates actually scored by the reranker are reordered.
        - Candidates without reranker scores stay behind the reranked pool.
        """
        _check_cancelled(cancel_event)
        if self._reranker is None or not query_text or not candidates:
            return candidates

        # Number of candidates that will actually be reranked
        rerank_limit = min(
            max(top_k * 2, self._reranker_top_k),
            len(candidates),
        )

        rerank_pool = candidates[:rerank_limit]
        remaining = candidates[rerank_limit:]

        pairs = []
        valid_items = []

        for item in rerank_pool:
            entity = item.get("entity", {})

            # Current schema: ASR + OCR only
            doc_parts = []

            asr = entity.get("asr")
            if isinstance(asr, str) and asr.strip():
                doc_parts.append(asr.strip())

            ocr = entity.get("ocr")
            if isinstance(ocr, str) and ocr.strip():
                doc_parts.append(ocr.strip())

            doc_text = " ".join(doc_parts)

            if not doc_text:
                continue

            pairs.append([query_text, doc_text])
            valid_items.append(item)

        if not pairs:
            return candidates

        _check_cancelled(cancel_event)
        try:
            rerank_scores = self._reranker.predict(
                pairs,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.error(f"searcher: Reranker prediction failed: {e}")
            return candidates

        # Assign reranker score ONLY to items that were actually scored
        for item, score in zip(valid_items, rerank_scores):
            item.setdefault("scores", {})
            item["scores"]["hybrid"] = item["distance"]
            item["scores"]["rerank"] = float(score)

            # distance now means reranker score for this item
            item["distance"] = float(score)

        # Items with no text cannot be reranked.
        # Put them after reranked items.
        valid_ids = {id(item) for item in valid_items}

        reranked_items = [
            item for item in rerank_pool
            if id(item) in valid_ids
        ]

        unrerrankable_items = [
            item for item in rerank_pool
            if id(item) not in valid_ids
        ]

        reranked_items.sort(
            key=lambda x: x["scores"]["rerank"],
            reverse=True
        )

        # IMPORTANT:
        # Do NOT compare rerank score against hybrid score.
        return reranked_items + unrerrankable_items + remaining

    def _temporal_search(
        self,
        query: Query,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        ocr_weight: float = 0.0,
        asr_weight: float = 0.0,
        ocr_alpha: float = 0.0,
        asr_alpha: float = 0.0,
        hybrid_alpha: float | None = None,
        nprobe: int = 8,
        temporal_k: int = 200,
        max_interval: int = 1000,
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        if hybrid_alpha is not None:
            ocr_alpha = hybrid_alpha
            asr_alpha = hybrid_alpha
        params = {
            "query": query.data,
            "video_ids": query.include_video_ids,
            "exclude_video_ids": query.exclude_video_ids,
            "target_features": target_features,
            "ocr_weight": ocr_weight,
            "asr_weight": asr_weight,
            "ocr_alpha": ocr_alpha,
            "asr_alpha": asr_alpha,
            "nprobe": nprobe,
            "temporal_k": temporal_k,
            "max_interval": max_interval,
        }
        query_str = f"{constants.CACHE_TEMPORAL_SEARCH}:{repr(params)}"
        query_hash = hashlib.sha256(query_str.encode("utf-8")).hexdigest()

        if query_hash in self.cache:
            temporal_results = self.cache[query_hash]
        else:
            st = time.time()
            results_list = []
            for q in query.data:
                _check_cancelled(cancel_event)
                results = self._similarity_search(
                    q["features"],
                    query.include_video_ids,
                    0,
                    temporal_k,
                    target_features,
                    ocr_weight=ocr_weight,
                    asr_weight=asr_weight,
                    ocr_alpha=ocr_alpha,
                    asr_alpha=asr_alpha,
                    nprobe=nprobe,
                    exclude_video_ids=query.exclude_video_ids,
                    cancel_event=cancel_event,
                )
                results_list.append(results)

            en = time.time()
            logger.info(f"searcher: Take {en-st:.4f} seconds to search results")

            _check_cancelled(cancel_event)
            st = time.time()
            temporal_results = self._combine_temporal_results(results_list, max_interval, cancel_event=cancel_event)
            temporal_results = self._filter_exclude_videos(temporal_results, query.exclude_video_ids)
            en = time.time()
            logger.info(f"searcher: Take {en-st:.4f} seconds to combine and filter results")

            self.cache[query_hash] = temporal_results

        if temporal_results is not None and offset < len(temporal_results):
            results = temporal_results[offset : offset + limit]
        else:
            results = []

        res = {
            "results": results,
            "total": len(temporal_results or []),
            "offset": offset,
        }
        return res

    def _combine_temporal_results(self, results_list: list, max_interval: int, cancel_event: threading.Event | Callable = None):
        _check_cancelled(cancel_event)
        best = None

        for i in range(len(results_list)):
            res = results_list[i]
            for j in range(len(res)):
                video_id, frame_id = results_list[i][j]["entity"]["frame_id"].split("#")
                results_list[i][j]["_id"] = (video_id, int(frame_id))
                results_list[i][j]["time_line"] = [frame_id]
                results_list[i][j]["time_line_scores"] = [results_list[i][j].get("scores", {})]

        for i, res in enumerate(results_list[::-1]):
            _check_cancelled(cancel_event)
            if best is None:
                best = res[: constant.TEMPORAL_QUEUE_SIZE]
                continue

            tmp = []
            res = sorted(res, key=lambda x: x["_id"])
            best = sorted(best, key=lambda x: x["_id"])
            l = 0
            r = 0
            for cur in res:
                cur_vid, cur_fid = cur["_id"]

                low_id = (cur_vid, cur_fid)
                high_id = (cur_vid, cur_fid + max_interval)

                cur_fid = int(cur_fid)

                while l < len(best):
                    next_id = best[l]["_id"]

                    if next_id > low_id:
                        break
                    else:
                        l += 1

                while r < len(best):
                    next_id = best[r]["_id"]

                    if next_id > high_id:
                        break
                    else:
                        r += 1

                if l < r:
                    for next in best[l:r]:
                        _, cur_fid = cur["_id"]
                        combined_dist = cur["distance"] + next["distance"]
                        cur_scores = cur.get("scores", {})
                        next_scores = next.get("scores", {})

                        combined_scores = {
                            "final": round(combined_dist, 6),
                            "clip": round(cur_scores.get("clip", 0.0) + next_scores.get("clip", 0.0), 6),
                            "ocr": round(cur_scores.get("ocr", 0.0) + next_scores.get("ocr", 0.0), 6),
                            "asr": round(cur_scores.get("asr", 0.0) + next_scores.get("asr", 0.0), 6),
                            "clip_raw": round(cur_scores.get("clip_raw", 0.0) + next_scores.get("clip_raw", 0.0), 6),
                            "ocr_raw": round(cur_scores.get("ocr_raw", 0.0) + next_scores.get("ocr_raw", 0.0), 6),
                            "asr_raw": round(cur_scores.get("asr_raw", 0.0) + next_scores.get("asr_raw", 0.0), 6),
                        }
                        cur_tls = cur.get("time_line_scores", [cur_scores])
                        next_tls = next.get("time_line_scores", [next_scores])
                        tmp.append(
                            {
                                **cur,
                                "distance": combined_dist,
                                "scores": combined_scores,
                                "time_line": [*cur["time_line"], *next["time_line"]],
                                "time_line_scores": [*cur_tls, *next_tls],
                            }
                        )

            tmp = sorted(tmp, key=lambda x: x["distance"], reverse=True)
            best = tmp[: constant.TEMPORAL_QUEUE_SIZE]

        return best

    def _get_videos(
        self,
        include_video_ids: list[str] = [],
        exclude_video_ids: list[str] = [],
        offset: int = 0,
        limit: int = 10000,
        selected: Optional[str] = None,
        cancel_event: threading.Event | Callable = None,
    ):
        _check_cancelled(cancel_event)
        query_str = f"{constants.CACHE_GET_VIDEOS}:{repr(include_video_ids)}:{repr(exclude_video_ids)}"
        query_hash = hashlib.sha256(query_str.encode("utf-8")).hexdigest()

        if query_hash in self.cache:
            videos = self.cache[query_hash]
        elif len(include_video_ids) == 0 and len(exclude_video_ids) == 0:
            videos = []
        else:
            video_filter = self._get_video_filter(include_video_ids)
            query_limit = 10000 if include_video_ids else max(500, (offset + limit) * 5)
            _check_cancelled(cancel_event)
            videos = self._database.query(video_filter, 0, query_limit)
            videos = sorted(videos, key=lambda x: x["frame_id"])
            videos = [{"entity": x} for x in videos]

            videos = self._filter_exclude_videos(videos, exclude_video_ids)

            self.cache[query_hash] = videos

        if selected:
            for i, video in enumerate(videos):
                if selected == video["entity"]["frame_id"]:
                    offset = (i // limit) * limit
                    break
        res = {
            "results": videos[offset : offset + limit],
            "total": len(videos),
            "offset": offset,
        }
        return res

    def _prepare_feature_extractors(self, device: torch.device):
        self._extractors = {}
        self._features = {}
        col_name = getattr(getattr(self, "_database", None), "_collection_name", "unknown")

        has_ocr_feature = bool(GlobalConfig.get("features", "ocr"))
        has_ocr_searcher = bool(GlobalConfig.get("searcher", "ocr"))
        ocr_enabled = has_ocr_feature and (
            GlobalConfig.get("searcher", "ocr", "enable") is True
            or (has_ocr_searcher and GlobalConfig.get("searcher", "ocr", "enable") is not False)
        )
        if ocr_enabled:
            candidate_ocr = GlobalConfig.get("searcher", "ocr", "ocr_field") or "ocr"
            candidate_ocr_dense = GlobalConfig.get("searcher", "ocr", "ocr_dense_field")
            # If collection has fields, ensure OCR is in collection
            if self._collection_fields and not (
                candidate_ocr in self._collection_fields
                or f"{candidate_ocr}_sparse" in self._collection_fields
                or candidate_ocr.replace("_sparse", "") in self._collection_fields
            ):
                self._ocr_name = None
                self._ocr_dense_name = None
            else:
                self._ocr_name = candidate_ocr
                self._ocr_dense_name = candidate_ocr_dense
        else:
            self._ocr_name = None
            self._ocr_dense_name = None

        has_asr_feature = bool(GlobalConfig.get("features", "asr"))
        has_asr_searcher = bool(GlobalConfig.get("searcher", "asr"))
        asr_enabled = has_asr_feature and (
            GlobalConfig.get("searcher", "asr", "enable") is True
            or (has_asr_searcher and GlobalConfig.get("searcher", "asr", "enable") is not False)
        )
        if asr_enabled:
            candidate_asr = GlobalConfig.get("searcher", "asr", "asr_field") or "asr"
            candidate_asr_dense = GlobalConfig.get("searcher", "asr", "asr_dense_field")
            # If collection has fields, ensure ASR is in collection
            if self._collection_fields and not (
                candidate_asr in self._collection_fields
                or f"{candidate_asr}_sparse" in self._collection_fields
                or candidate_asr.replace("_sparse", "") in self._collection_fields
            ):
                self._asr_name = None
                self._asr_dense_name = None
            else:
                self._asr_name = candidate_asr
                self._asr_dense_name = candidate_asr_dense
        else:
            self._asr_name = None
            self._asr_dense_name = None

        language_models = GlobalConfig.get("searcher", "language_models") or {}

        for m in language_models.keys():
            source = GlobalConfig.get("searcher", "language_models", m, "source")
            model_name = GlobalConfig.get("searcher", "language_models", m, "model")
            arch_name = GlobalConfig.get("searcher", "language_models", m, "arch_name")
            pretrained_model = GlobalConfig.get("searcher", "language_models", m, "pretrained_model")
            text_source = GlobalConfig.get("searcher", "language_models", m, "text_source")
            target_features = GlobalConfig.get("searcher", "language_models", m, "target")
            batch_size = 1

            assert model_name is not None

            polite_name = f"{model_name}" + (f' from "{pretrained_model}"' if pretrained_model else "")
            if target_features is None or len(target_features) == 0:
                logger.error(f"searcher [{col_name}]: {polite_name} does not have target features")
                continue

            valid_targets = []
            for t in target_features:
                field_norm = self._database.process_field_name(t)
                if not self._collection_fields or t in self._collection_fields or field_norm in self._collection_fields:
                    valid_targets.append(t)

            if not valid_targets:
                logger.info(f"searcher [{col_name}]: Skipping model '{m}' (targets {target_features} not in collection fields)")
                continue

            feature_extractor_cls = FeatureExtractorFactory.get(model_name)
            if feature_extractor_cls:
                init_kwargs = {
                    "source": source,
                    "arch_name": arch_name,
                    "pretrained_model": pretrained_model,
                    "text_source": text_source,
                    "name": m,
                    "batch_size": batch_size,
                    "device": device,
                }
                if model_name == "text_embedding":
                    init_kwargs["allow_gpu"] = bool(
                        GlobalConfig.get("backends", "search", "gpu")
                    )
                    for key in (
                        "backend",
                        "onnx_provider",
                        "onnx_model_path",
                        "onnx_tokenizer_path",
                        "onnx_max_length",
                        "max_length",
                    ):
                        value = GlobalConfig.get("searcher", "language_models", m, key)
                        if value is not None:
                            init_kwargs[key] = value

                cache_key = (
                    model_name,
                    pretrained_model,
                    arch_name,
                    source,
                    init_kwargs.get("backend"),
                    init_kwargs.get("onnx_model_path"),
                    str(device),
                )
                with _EXTRACTOR_LOCK:
                    if cache_key in _SHARED_EXTRACTORS:
                        feature_extractor = _SHARED_EXTRACTORS[cache_key]
                        logger.info(f"searcher [{col_name}]: [CACHE HIT] Reusing loaded model '{model_name}' ({pretrained_model or arch_name})")
                    else:
                        logger.info(f"searcher [{col_name}]: [LOAD NEW] Loading model '{model_name}' ({pretrained_model or arch_name}) into {device}")
                        feature_extractor = feature_extractor_cls.from_pretrained(**init_kwargs)
                        _SHARED_EXTRACTORS[cache_key] = feature_extractor
            else:
                feature_extractor = None

            if not feature_extractor:
                logger.error(f"searcher [{col_name}]: {polite_name}: invalid feature extractor")
                continue

            for t in valid_targets:
                self._features[t] = m
            self._extractors[m] = {"feature_extractor": feature_extractor, "target_features": valid_targets}

        # --- Reranker Initialization ---
        reranker_enable = GlobalConfig.get("searcher", "reranker", "enable")
        if reranker_enable:
            reranker_model = GlobalConfig.get("searcher", "reranker", "model") or "BAAI/bge-reranker-v2-m3"
            reranker_device = str(device).split(":")[0]  # "cuda:0" -> "cuda"
            cache_key_reranker = ("reranker", reranker_model, reranker_device)
            try:
                with _EXTRACTOR_LOCK:
                    if cache_key_reranker in _SHARED_EXTRACTORS:
                        self._reranker = _SHARED_EXTRACTORS[cache_key_reranker]
                        logger.info(f"searcher [{col_name}]: [CACHE HIT] Reusing Reranker {reranker_model}")
                    else:
                        logger.info(f"searcher [{col_name}]: [LOAD NEW] Loading Reranker model: {reranker_model}")
                        self._reranker = CrossEncoder(reranker_model, device=reranker_device)
                        _SHARED_EXTRACTORS[cache_key_reranker] = self._reranker
                        logger.info(f"searcher: Reranker loaded successfully")
                self._reranker_top_k = int(GlobalConfig.get("searcher", "reranker", "top_k") or 50)
            except Exception as e:
                logger.error(f"searcher [{col_name}]: Failed to load Reranker: {e}")
                self._reranker = None
                self._reranker_top_k = 0
        else:
            self._reranker = None
            self._reranker_top_k = 0

        # --- Khởi tạo LLM Query Expander ---
        self._llm_expander = None
        llm_config = GlobalConfig.get("searcher", "llm") or {}
        llm_enabled = llm_config.get("enable", True)

        if llm_enabled:
            api_key = llm_config.get("api_key")
            provider = llm_config.get("provider", "groq")
            model_name_llm = llm_config.get("model_name", "openai/gpt-oss-120b")
            cache_key_llm = ("llm_expander", provider, model_name_llm)
            try:
                from aic51.packages.search.llm_expander import LLMQueryExpander

                with _EXTRACTOR_LOCK:
                    if cache_key_llm in _SHARED_EXTRACTORS:
                        self._llm_expander = _SHARED_EXTRACTORS[cache_key_llm]
                        logger.info(f"searcher [{col_name}]: [CACHE HIT] Reusing LLMQueryExpander")
                    else:
                        self._llm_expander = LLMQueryExpander(
                            api_key=api_key,
                            model_name=model_name_llm,
                            provider=provider,
                        )
                        _SHARED_EXTRACTORS[cache_key_llm] = self._llm_expander
                        if self._llm_expander.is_available:
                            logger.info("searcher: LLMQueryExpander loaded successfully")
            except Exception as e:
                logger.warning(f"searcher [{col_name}]: Failed to load LLMQueryExpander: {e}")
                self._llm_expander = None

    def expand_query_detailed(self, query_text: str) -> dict:
        """Sinh 3 biến thể Jina AI (HyDE, Sub-queries/Keywords, Paraphrase) từ query gốc."""
        if not self._llm_expander or not self._llm_expander.is_available:
            logger.warning("searcher: expand_query called but LLMQueryExpander is not available")
            return {}
        return self._llm_expander.expand_query_detailed(query_text)

    def expand_query(self, query_text: str) -> list[str]:
        """Sinh 3 biến thể ngữ nghĩa Jina AI từ query gốc bằng LLM.
        Trả về list các biến thể text để người dùng chọn trên giao diện UI.
        """
        if not self._llm_expander or not self._llm_expander.is_available:
            logger.warning("searcher: expand_query called but LLMQueryExpander is not available")
            return []
        return self._llm_expander.expand_query(query_text)
