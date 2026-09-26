import os
import gc
import hashlib
import json
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
    YOLO_RELATION_BOOST = 1.10
    cache = BoundedLRUCache(maxsize=20)

    def __init__(self, collection_name: str, device: torch.device = torch.device("cpu")):
        self._database = MilvusDatabase(collection_name)
        try:
            desc = self._database._client.describe_collection(collection_name)
            self._collection_fields = {f.get("name") for f in desc.get("fields", []) if f.get("name")}
        except Exception:
            self._collection_fields = set()
        self._prepare_feature_extractors(device)
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

        # Single-search shot clustering always compares SigLIP2 vectors.
        # If a collection has no SigLIP2 field, vector retrieval fails open
        # and search results are returned without clustering.
        self._single_search_cluster_vector_field = "image_siglip2_so400m_378"
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

    def _get_relation_filter(self, relation_key: str) -> str:
        if not relation_key:
            return ""
        if "yolo_relations" not in self._collection_fields:
            raise ValueError("This collection does not contain YOLO relations")
        parts = relation_key.split(":")
        valid_relations = {"left_of", "right_of", "above", "below", "near"}
        valid = False
        if len(parts) == 3:
            # object1:relation:object2
            valid = parts[1] in valid_relations
        elif len(parts) == 4:
            # color1:object1:relation:object2 or object1:relation:color2:object2
            valid = parts[2] in valid_relations or parts[1] in valid_relations
        elif len(parts) == 5:
            # color1:object1:relation:color2:object2
            valid = parts[2] in valid_relations

        if not valid or any(not re.fullmatch(r"[a-z0-9_]{1,64}", part) for part in parts):
            raise ValueError("Invalid YOLO relation key")
        return f"ARRAY_CONTAINS(yolo_relations, {json.dumps(relation_key)})"

    @classmethod
    def _apply_yolo_relation_boost(cls, results: list[dict], relation_key: str) -> list[dict]:
        """Apply a small ranking boost to matching candidates without filtering results."""
        if not relation_key:
            return results

        for result in results:
            entity = result.get("entity", {})
            relations = entity.get("yolo_relations", [])
            if isinstance(relations, str):
                relations = [relations]
            if relation_key not in relations:
                continue

            scores = result.setdefault("scores", {})
            base_score = float(result.get("distance", 0.0) or 0.0)

            # Avoid redundant boost on the same stage score
            if scores.get("yolo_relation_boost") and not ("rerank" in scores and not scores.get("rerank_boosted")):
                continue

            boost_delta = max(abs(base_score) * (cls.YOLO_RELATION_BOOST - 1.0), 0.01)
            boosted_score = base_score + boost_delta
            result["distance"] = boosted_score
            scores["pre_yolo_relation"] = round(base_score, 6)
            scores["yolo_relation_boost"] = cls.YOLO_RELATION_BOOST
            scores["final"] = round(boosted_score, 6)
            if "rerank" in scores:
                scores["rerank"] = round(boosted_score, 6)
                scores["rerank_boosted"] = True

        # Keep reranked candidates ahead of candidates without reranker scores;
        # their distance values come from different score scales.
        results.sort(
            key=lambda item: (
                "rerank" in item.get("scores", {}),
                item.get("distance", 0.0),
            ),
            reverse=True,
        )
        return results

    @staticmethod
    def _combine_filters(*filters: str) -> str:
        return " && ".join(f"({filter_expr})" for filter_expr in filters if filter_expr)

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
        yolo_relation: str = "",
        camera_filter: str = "",
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
        if yolo_relation:
            # Reuse validation and ensure this collection has the relation field.
            self._get_relation_filter(yolo_relation)

        if query.simple:
            logger.info(f"searcher: get include_video_ids={query.include_video_ids}, exclude_video_ids={query.exclude_video_ids}")
            browse_filter = self._combine_filters(
                camera_filter,
                self._get_relation_filter(yolo_relation) if yolo_relation else "",
            )
            if browse_filter:
                res = self._get_camera_matches(
                    query.include_video_ids, query.exclude_video_ids, browse_filter,
                    offset, limit, cancel_event=cancel_event,
                )
            else:
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
                yolo_relation=yolo_relation,
                camera_filter=camera_filter,
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
                yolo_relation=yolo_relation,
                camera_filter=camera_filter,
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
        yolo_relation: str = "",
        camera_filter: str = "",
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
        video_filter = self._combine_filters(self._get_video_filter(video_ids), camera_filter)

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

        # 4. Auto OCR Intelligent Boosting (Non-Penalizing)
        # Kích hoạt tự động khi ocr_weight == 0.0 nhưng query có chứa text entities
        auto_text_boosts = {}
        auto_ocr_entities = query_features.get("auto_ocr", [])

        if self._ocr_name and ocr_weight == 0.0 and auto_ocr_entities:
            _check_cancelled(cancel_event)
            text_query_str = " ".join(auto_ocr_entities)
            try:
                auto_search_limit = max(subquery_limit * 2, 200)
                ocr_bm25_res = self._database.search(
                    data=[text_query_str],
                    filter=video_filter,
                    offset=0,
                    limit=auto_search_limit,
                    anns_field=self._ocr_name,
                    search_params={"metric_type": "BM25"},
                )
                if ocr_bm25_res and len(ocr_bm25_res) > 0:
                    text_field = self._text_field_from_index_field(self._ocr_name)
                    max_bm25 = max([hit.get("distance", 0.0) for hit in ocr_bm25_res[0]], default=1.0) or 1.0
                    for hit in ocr_bm25_res[0]:
                        fid = hit["entity"]["frame_id"]
                        doc_text = str(hit["entity"].get(text_field, "")).lower()
                        bm25_score = hit.get("distance", 0.0)
                        norm_bm25 = bm25_score / max_bm25

                        # Check exact match for any entity (min 2 chars)
                        exact_match = any(e.lower() in doc_text for e in auto_ocr_entities if len(e) >= 2)
                        boost = 1.35 if exact_match else (1.0 + 0.20 * norm_bm25)

                        auto_text_boosts[fid] = {
                            "boost": boost,
                            "exact": exact_match,
                            "norm_bm25": norm_bm25,
                            "entity": hit["entity"],
                        }
                        if fid not in entity_data:
                            entity_data[fid] = hit["entity"]
            except Exception as e:
                logger.warning(f"searcher: auto OCR boost search encountered issue: {e}")

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

            base_score = clip_weight * clip_s + ocr_weight * ocr_s + asr_weight * asr_s

            # Non-penalizing boost:
            boost_factor = 1.0
            if fid in auto_text_boosts:
                boost_factor = auto_text_boosts[fid]["boost"]

            final_score = base_score * boost_factor

            results.append({
                "entity": entity_data[fid],
                "distance": final_score,
                "scores": {
                    "final": round(final_score, 6),
                    "base": round(base_score, 6),
                    "clip": round(clip_s, 6),
                    "ocr": round(ocr_s, 6),
                    "asr": round(asr_s, 6),
                    "auto_boost": round(boost_factor, 4),
                    "clip_raw": round(clip_raw_scores.get(fid, 0.0), 6),
                    "ocr_raw": round(ocr_raw_scores.get(fid, 0.0), 6),
                    "asr_raw": round(asr_raw_scores.get(fid, 0.0), 6),
                },
            })

        # Extra safety: If an exact high-confidence OCR match was not in visual top pool,
        # grant it entry with a solid floor score
        for fid, boost_info in auto_text_boosts.items():
            if fid not in all_frame_ids and boost_info["exact"]:
                floor_score = 0.55 * boost_info["boost"]
                results.append({
                    "entity": boost_info["entity"],
                    "distance": floor_score,
                    "scores": {
                        "final": round(floor_score, 6),
                        "base": 0.55,
                        "clip": 0.0,
                        "ocr": round(boost_info["norm_bm25"], 6),
                        "asr": 0.0,
                        "auto_boost": round(boost_info["boost"], 4),
                        "clip_raw": 0.0,
                        "ocr_raw": 0.0,
                        "asr_raw": 0.0,
                    },
                })

        # Sort by final score descending
        results = self._apply_yolo_relation_boost(results, yolo_relation)
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
        yolo_relation: str = "",
        camera_filter: str = "",
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
                yolo_relation=yolo_relation,
                camera_filter=camera_filter,
                cancel_event=cancel_event,
            )
            total = len(results)
        else:
            base_limit = (
                max(300, (offset + limit) * 3)
                if len(query.exclude_video_ids) > 0
                else max(200, offset + limit)
            )
            candidate_limit = max(400 if yolo_relation else 200, base_limit)

            db_size = self._database.count(camera_filter) if camera_filter else self._database.get_size()

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
                    yolo_relation=yolo_relation,
                    camera_filter=camera_filter,
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

        results = self._apply_yolo_relation_boost(results, yolo_relation)

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
        yolo_relation: str = "",
        camera_filter: str = "",
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
            "yolo_relation": yolo_relation,
            "camera_filter": camera_filter,
            "yolo_relation_boost": self.YOLO_RELATION_BOOST,
            # Bump this when temporal candidate/DP semantics change so stale
            # in-memory results are not reused after a backend reload.
            "temporal_algorithm": "frame_dp_no_shot_clustering_v4_relation_boost_clause_quota",
        }
        query_str = f"{constants.CACHE_TEMPORAL_SEARCH}:{repr(params)}"
        query_hash = hashlib.sha256(query_str.encode("utf-8")).hexdigest()

        if query_hash in self.cache:
            temporal_results = self.cache[query_hash]
        else:
            st = time.time()
            temporal_candidate_k = max(int(temporal_k), 1000)
            results_list = []
            for q in query.data:
                _check_cancelled(cancel_event)
                results = self._similarity_search(
                    q["features"],
                    query.include_video_ids,
                    0,
                    temporal_candidate_k,
                    target_features,
                    ocr_weight=ocr_weight,
                    asr_weight=asr_weight,
                    ocr_alpha=ocr_alpha,
                    asr_alpha=asr_alpha,
                    nprobe=nprobe,
                    exclude_video_ids=query.exclude_video_ids,
                    yolo_relation=yolo_relation,
                    camera_filter=camera_filter,
                    cancel_event=cancel_event,
                )
                self._calibrate_temporal_stage_results(results)
                results_list.append(results)

            candidate_videos = self._select_temporal_candidate_videos(
                results_list,
                # Keep the broad video union used by the recall benchmark.
                # Temporal shot clustering is disabled below, so this no
                # longer triggers thousands of vector fetches from Milvus.
                max_videos=max(1000, int(temporal_k)),
                cancel_event=cancel_event,
            )
            if candidate_videos:
                candidate_set = set(candidate_videos)
                results_list = [
                    [
                        result
                        for result in stage_results
                        if self._result_video_id(result) in candidate_set
                    ]
                    for stage_results in results_list
                ]

            en = time.time()
            logger.info(f"searcher: Take {en-st:.4f} seconds to search results")

            _check_cancelled(cancel_event)
            st = time.time()
            temporal_results, temporal_debug = self._combine_temporal_results(
                results_list,
                max_interval,
                allow_relaxed_fallback=True,
                candidate_limit_per_stage=temporal_candidate_k,
                cancel_event=cancel_event,
            )
            temporal_results = self._filter_exclude_videos(temporal_results, query.exclude_video_ids)
            en = time.time()
            logger.info(
                "searcher: Take %.4f seconds to combine and filter results; temporal_debug=%s",
                en - st,
                temporal_debug,
            )

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

    @staticmethod
    def _result_video_id(result: dict) -> str:
        frame_id = str(result.get("entity", {}).get("frame_id", ""))
        return frame_id.split("#", 1)[0] if "#" in frame_id else frame_id

    @staticmethod
    def _calibrate_temporal_stage_results(
        results: list[dict],
        rrf_k: float = 60.0,
    ) -> None:
        """Attach a clause-local reciprocal-rank score to each frame."""
        for rank, result in enumerate(results, 1):
            result["_temporal_rank_score"] = float(rrf_k / (rrf_k + rank))

    def _select_temporal_candidate_videos(
        self,
        results_list: list[list[dict]],
        max_videos: int,
        cancel_event: threading.Event | Callable = None,
    ) -> list[str]:
        """Rank candidate videos by event coverage and clause-local rank."""
        _check_cancelled(cancel_event)
        per_stage_scores = []
        for stage_results in results_list:
            scores = {}
            for result in stage_results:
                video_id = self._result_video_id(result)
                if not video_id:
                    continue
                score = float(result.get("_temporal_rank_score", 0.0) or 0.0)
                scores[video_id] = max(scores.get(video_id, 0.0), score)
            per_stage_scores.append(scores)

        video_ids = set().union(*(scores.keys() for scores in per_stage_scores)) if per_stage_scores else set()
        ranked = []
        stage_count = max(1, len(per_stage_scores))
        for video_id in video_ids:
            _check_cancelled(cancel_event)
            values = [scores[video_id] for scores in per_stage_scores if video_id in scores]
            coverage = len(values) / stage_count
            covered_mean = sum(values) / max(1, len(values))
            ranked.append((0.65 * coverage + 0.35 * covered_mean, coverage, video_id))
        ranked.sort(reverse=True)

        # Reserve a candidate quota from every clause before filling the
        # remaining slots by global coverage. This keeps a difficult clause
        # from disappearing behind candidates from easier/general clauses.
        quota = max(5, max_videos // stage_count)
        guaranteed = set()
        for scores in per_stage_scores:
            guaranteed.update(
                video_id
                for video_id, _ in sorted(
                    scores.items(),
                    key=lambda item: (item[1], item[0]),
                    reverse=True,
                )[:quota]
            )

        rank_lookup = {
            video_id: (score, coverage, video_id)
            for score, coverage, video_id in ranked
        }
        guaranteed_ranked = sorted(
            guaranteed,
            key=lambda video_id: rank_lookup.get(video_id, (0.0, 0.0, video_id)),
            reverse=True,
        )
        remaining_ranked = [
            video_id for _, _, video_id in ranked if video_id not in guaranteed
        ]
        return (guaranteed_ranked + remaining_ranked)[:max_videos]

    @staticmethod
    def _temporal_hit_score(hit: dict) -> float:
        if "_temporal_rank_score" in hit:
            return float(hit.get("_temporal_rank_score") or 0.0)
        scores = hit.get("scores", {}) or {}
        for key in ("rrf_score", "rrf", "final"):
            if key in scores:
                return float(scores[key] or 0.0)
        return float(hit.get("distance", 0.0) or 0.0)

    def _cluster_temporal_stage(
        self,
        results: list[dict],
        cancel_event: threading.Event | Callable = None,
    ) -> tuple[list[dict], int]:
        """Convert temporal hits to singleton DP candidates.

        Temporal search intentionally does not perform online shot clustering:
        fetching thousands of stored vectors and comparing them at query time
        caused a large latency regression. Single-search visual deduplication
        remains enabled in ``_advance_search``.
        """
        clusters = []
        seen_frame_ids = set()
        for hit in results:
            _check_cancelled(cancel_event)
            frame_key = str(hit.get("entity", {}).get("frame_id", ""))
            if "#" not in frame_key or frame_key in seen_frame_ids:
                continue
            seen_frame_ids.add(frame_key)
            video_id, frame_text = frame_key.split("#", 1)
            try:
                frame_id = int(frame_text)
            except ValueError:
                continue
            item = {
                "hit": hit,
                "video_id": video_id,
                "frame_id": frame_id,
                "score": self._temporal_hit_score(hit),
                "raw_score": float(hit.get("distance", 0.0) or 0.0),
            }
            clusters.append(
                {
                    "video_id": video_id,
                    "min_frame_id": frame_id,
                    "max_frame_id": frame_id,
                    "cluster_score": item["score"],
                    "raw_score": item["raw_score"],
                    "best_hit": item,
                    "hits": [item],
                }
            )
        return clusters, len(clusters)

    def _best_ordered_frame_sequence(
        self,
        selected_stages: list[tuple[int, list[dict]]],
        max_interval: int,
        penalty_weight: float,
        cancel_event: threading.Event | Callable = None,
    ) -> dict | None:
        """Use DP to find the best strictly ordered frame path for one video."""
        if not selected_stages or any(not clusters for _, clusters in selected_stages):
            return None

        def frame_candidates(clusters):
            candidates = []
            seen = set()
            for cluster in clusters:
                for hit in cluster["hits"]:
                    key = (hit["video_id"], hit["frame_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append({**cluster, "best_hit": hit, "cluster_score": hit["score"]})
            return candidates

        match_count = len(selected_stages)
        transition_count = max(1, match_count - 1)

        def objective(score_sum, penalty_sum):
            return score_sum / match_count - penalty_sum / transition_count

        first_stage_index, first_clusters = selected_stages[0]
        states = [
            {
                "last": candidate,
                "sequence": [(first_stage_index, candidate)],
                "gaps": [],
                "score_sum": candidate["cluster_score"],
                "penalty_sum": 0.0,
            }
            for candidate in frame_candidates(first_clusters)
        ]

        for stage_index, clusters in selected_stages[1:]:
            _check_cancelled(cancel_event)
            next_states = []
            for candidate in frame_candidates(clusters):
                best_state = None
                best_score = float("-inf")
                current_frame = candidate["best_hit"]["frame_id"]
                for state in states:
                    previous_frame = state["last"]["best_hit"]["frame_id"]
                    gap = current_frame - previous_frame
                    if gap <= 0 or (max_interval > 0 and gap > max_interval):
                        continue
                    transition_penalty = (
                        penalty_weight * gap / max_interval if max_interval > 0 else 0.0
                    )
                    score_sum = state["score_sum"] + candidate["cluster_score"]
                    penalty_sum = state["penalty_sum"] + transition_penalty
                    candidate_score = objective(score_sum, penalty_sum)
                    if candidate_score > best_score:
                        best_score = candidate_score
                        best_state = {
                            "last": candidate,
                            "sequence": [*state["sequence"], (stage_index, candidate)],
                            "gaps": [*state["gaps"], gap],
                            "score_sum": score_sum,
                            "penalty_sum": penalty_sum,
                        }
                if best_state is not None:
                    next_states.append(best_state)
            states = next_states
            if not states:
                return None

        best = max(
            states,
            key=lambda state: objective(state["score_sum"], state["penalty_sum"]),
        )
        best["path_score"] = objective(best["score_sum"], best["penalty_sum"])
        return best

    @staticmethod
    def _source_frame_id(cluster: dict) -> str:
        raw_id = str(cluster["best_hit"]["hit"].get("entity", {}).get("frame_id", ""))
        return raw_id.split("#", 1)[1] if "#" in raw_id else str(cluster["best_hit"]["frame_id"])

    def _temporal_sequence_result(self, state: dict, total_stage_count: int) -> dict:
        indexed_sequence = state["sequence"]
        sequence = [cluster for _, cluster in indexed_sequence]
        best_hits = [cluster["best_hit"] for cluster in sequence]
        scores = [cluster["cluster_score"] for cluster in sequence]
        coverage = len(sequence) / total_stage_count
        total_gap = sum(state["gaps"])
        average_score = sum(scores) / len(scores)
        combined_score = state["path_score"] * coverage * coverage
        score_keys = ("clip", "ocr", "asr", "clip_raw", "ocr_raw", "asr_raw")
        combined_scores = {
            "final": round(combined_score, 6),
            "temporal_average": round(average_score, 6),
            "temporal_gap": total_gap,
            "temporal_coverage": round(coverage, 6),
        }
        for key in score_keys:
            combined_scores[key] = round(
                sum(float(hit["hit"].get("scores", {}).get(key, 0.0) or 0.0) for hit in best_hits)
                / len(best_hits),
                6,
            )

        events = []
        for stage_index, cluster in indexed_sequence:
            best_hit = cluster["best_hit"]
            events.append(
                {
                    "stage_index": stage_index,
                    "shot_start_frame": cluster["min_frame_id"],
                    "shot_end_frame": cluster["max_frame_id"],
                    "best_frame": best_hit["hit"]["entity"]["frame_id"],
                    "score": round(cluster["cluster_score"], 6),
                }
            )

        first_hit = best_hits[0]["hit"]
        return {
            "entity": first_hit["entity"],
            "distance": combined_score,
            "scores": combined_scores,
            "time_line": [self._source_frame_id(cluster) for cluster in sequence],
            "time_line_scores": [hit["hit"].get("scores", {}) for hit in best_hits],
            "temporal": {
                "video_id": sequence[0]["video_id"],
                "combined_score": combined_score,
                "average_score": average_score,
                "temporal_gap": total_gap,
                "gaps": state["gaps"],
                "coverage": coverage,
                "partial": len(sequence) < total_stage_count,
                "matched_stage_indices": [stage_index for stage_index, _ in indexed_sequence],
                "events": events,
            },
        }

    def _combine_temporal_results(
        self,
        results_list: list[list[dict]],
        max_interval: int,
        *,
        allow_relaxed_fallback: bool = True,
        penalty_weight: float = 0.05,
        max_sequences: int = constant.TEMPORAL_QUEUE_SIZE,
        candidate_limit_per_stage: int | None = None,
        cancel_event: threading.Event | Callable = None,
    ) -> tuple[list[dict], dict]:
        """Return the best online-shot-aware ordered timeline per video."""
        _check_cancelled(cancel_event)
        debug = {
            "stage_candidate_counts": [],
            "stage_cluster_counts": [],
            "candidate_limit_per_stage": candidate_limit_per_stage,
            "max_interval": max_interval,
            "max_interval_enforced": True,
            "used_relaxed_fallback": False,
            "full_match_video_count": 0,
            "partial_match_video_count": 0,
            "failure_reason": None,
        }
        if not results_list:
            debug["failure_reason"] = "stage_has_no_candidates"
            return [], debug

        stage_clusters = []
        for stage_results in results_list:
            clusters, candidate_count = self._cluster_temporal_stage(
                stage_results,
                cancel_event=cancel_event,
            )
            stage_clusters.append(clusters)
            debug["stage_candidate_counts"].append(candidate_count)
            debug["stage_cluster_counts"].append(len(clusters))

        stage_count = len(stage_clusters)
        clusters_by_video = {}
        for stage_index, clusters in enumerate(stage_clusters):
            for cluster in clusters:
                video_stages = clusters_by_video.setdefault(
                    cluster["video_id"],
                    [[] for _ in range(stage_count)],
                )
                video_stages[stage_index].append(cluster)

        debug["candidate_video_count"] = len(clusters_by_video)
        debug["eligible_video_count"] = sum(
            1 for stages in clusters_by_video.values() if all(stages)
        )
        results = []
        for video_id, stages in clusters_by_video.items():
            _check_cancelled(cancel_event)
            selected_stages = list(enumerate(stages))
            state = self._best_ordered_frame_sequence(
                selected_stages,
                max_interval,
                penalty_weight,
                cancel_event=cancel_event,
            )
            if state is not None:
                debug["full_match_video_count"] += 1
                results.append(self._temporal_sequence_result(state, stage_count))
                continue

            if not allow_relaxed_fallback or stage_count < 3:
                continue
            best_partial = None
            for omitted_stage in range(stage_count):
                partial_stages = [
                    (index, stage)
                    for index, stage in enumerate(stages)
                    if index != omitted_stage
                ]
                partial_state = self._best_ordered_frame_sequence(
                    partial_stages,
                    max_interval,
                    penalty_weight,
                    cancel_event=cancel_event,
                )
                if partial_state is not None and (
                    best_partial is None
                    or partial_state["path_score"] > best_partial["path_score"]
                ):
                    best_partial = partial_state
            if best_partial is not None:
                debug["used_relaxed_fallback"] = True
                debug["partial_match_video_count"] += 1
                results.append(self._temporal_sequence_result(best_partial, stage_count))

        if not results:
            debug["failure_reason"] = "no_valid_ordered_sequence"
        results.sort(key=lambda result: float(result.get("distance", 0.0)), reverse=True)
        return results[:max_sequences], debug

    def _get_camera_matches(
        self,
        include_video_ids: list[str],
        exclude_video_ids: list[str],
        camera_filter: str,
        offset: int,
        limit: int,
        cancel_event: threading.Event | Callable = None,
    ) -> dict:
        _check_cancelled(cancel_event)
        filter_parts = [camera_filter, self._get_video_filter(include_video_ids)]
        for video_id in exclude_video_ids:
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
                filter_parts.append(f"!(frame_id like {json.dumps(video_id + '%')})")
        filter_expr = self._combine_filters(*filter_parts)
        total = self._database.count(filter_expr)
        _check_cancelled(cancel_event)
        rows = self._database.query(filter_expr, offset, limit)
        return {
            "results": [{"entity": row} for row in rows],
            "total": total,
            "offset": offset,
        }

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
