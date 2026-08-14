import hashlib
import re
import time
import unicodedata
from typing import Optional

import torch
from pymilvus import AnnSearchRequest, RRFRanker

import aic51.packages.constant as constant
from aic51.packages.analyse import FeatureExtractorFactory
from aic51.packages.config import GlobalConfig
from aic51.packages.index import MilvusDatabase
from aic51.packages.logger import logger

from . import constants
from .utils import Query


def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


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
        norm_phrase = re.sub(r"\s+", " ", phrase.lower())
        norm_phrase_no_accent = remove_diacritics(norm_phrase)

        # Allow flexible spacing between word and digit boundaries (e.g. "cau 3" vs "cau3")
        flex_phrase = re.sub(r"(\w)\s+(\d)", r"\1\\s*\2", norm_phrase)
        flex_phrase = re.sub(r"(\d)\s+(\w)", r"\1\\s*\2", flex_phrase)

        flex_phrase_no_accent = re.sub(r"(\w)\s+(\d)", r"\1\\s*\2", norm_phrase_no_accent)
        flex_phrase_no_accent = re.sub(r"(\d)\s+(\w)", r"\1\\s*\2", flex_phrase_no_accent)

        pattern_exact = r"(?<!\w)" + flex_phrase + r"(?!\w)"
        pattern_no_accent = r"(?<!\w)" + flex_phrase_no_accent + r"(?!\w)"

        if not (re.search(pattern_exact, norm_target) or re.search(pattern_no_accent, norm_target_no_accent)):
            return False, len(phrases)

    return True, len(phrases)


class Searcher(object):
    cache = {}

    def __init__(self, collection_name: str, device: torch.device = torch.device("cpu")):
        self._database = MilvusDatabase(collection_name)
        self._prepare_feature_extractors(device)

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
        return list(self._features.keys())

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
        /,
        nprobe: int = 8,
        temporal_k: int = 2000,
        ocr_weight: float = 0.5,
        asr_weight: float = 0.0,
        max_interval: int = 1000,
        selected: str | None = None,
        auto_translate: bool = False,
        en_to_vi_translate: bool = False,
        include_videos: str = "",
        exclude_videos: str = "",
    ):
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
            res = self._get_videos(query.include_video_ids, query.exclude_video_ids, offset, limit, selected)
        elif query.advance and not query.temporal:
            logger.info(f"searcher: advance_search query={query.data}")
            res = self._advance_search(query, offset, limit, target_features, ocr_weight=ocr_weight, asr_weight=asr_weight, nprobe=nprobe)
        else:
            logger.info(f"searcher: temporal_search query={query.data}")
            res = self._temporal_search(
                query,
                offset,
                limit,
                target_features,
                ocr_weight=ocr_weight,
                asr_weight=asr_weight,
                nprobe=nprobe,
                temporal_k=temporal_k,
                max_interval=max_interval,
            )

        end_time = time.time()
        logger.info(f"searcher: Take {end_time - start_time:.4f} to extract and search")
        return res

    def search_image(
        self,
        id: str,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        nprobe: int = 8,
    ):
        record = self._database.get(id)
        if len(record) == 0:
            return {"results": [], "total": 0, "offset": 0}

        reqs = []
        subquery_limit = offset + limit

        for target_name in target_features:
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
        ocr_weight: float = 0.5,
        asr_weight: float = 0.0,
        nprobe: int = 8,
        exclude_video_ids: list[str] = [],
    ):
        ocr_weight = max(0, min(1, ocr_weight))
        asr_weight = max(0, min(1 - ocr_weight, asr_weight))
        video_filter = self._get_video_filter(video_ids)

        subquery_limit = offset + limit
        if exclude_video_ids and len(exclude_video_ids) > 0:
            subquery_limit = max(subquery_limit * 2, 300)

        # Score maps: frame_id -> raw score (per component)
        clip_raw_scores = {}  # frame_id -> sum of raw CLIP scores
        ocr_raw_scores = {}   # frame_id -> sum of raw OCR scores
        asr_raw_scores = {}   # frame_id -> sum of raw ASR scores
        all_frame_ids = set()
        # Store entity data for each frame_id
        entity_data = {}

        # 1. CLIP Search (using general "text" query or translated English "text_en" query)
        clip_weight = 1.0 - ocr_weight - asr_weight
        clip_req_count = 0
        clip_query_text = query_features.get("text_en", query_features.get("text", ""))
        if clip_query_text and clip_weight > 0:
            text_embeddings = {}
            for target_name in target_features:
                if target_name not in self._features:
                    logger.warning(f"searcher: {target_name} is invalid feature")
                    continue

                m = self._features[target_name]
                if m not in text_embeddings:
                    text_embeddings[m] = (
                        self._extractors[m]["feature_extractor"].get_text_features(clip_query_text).tolist()[0]
                    )

                search_results = self._database.search(
                    data=[text_embeddings[m]],
                    filter=video_filter,
                    offset=0,
                    limit=subquery_limit,
                    anns_field=target_name,
                    search_params={"nprobe": nprobe, "metric_type": "COSINE"},
                )
                clip_req_count += 1

                if search_results and len(search_results) > 0:
                    for hit in search_results[0]:
                        fid = hit["entity"]["frame_id"]
                        all_frame_ids.add(fid)
                        clip_raw_scores[fid] = clip_raw_scores.get(fid, 0) + hit["distance"]
                        if fid not in entity_data:
                            entity_data[fid] = hit["entity"]

        # 2. OCR Search
        ocr_req_count = 0
        if self._ocr_name and ocr_weight > 0:
            ocr_list = []
            if "ocr_translated" in query_features:
                ocr_list = query_features["ocr_translated"]
            elif "ocr" in query_features:
                ocr_list = query_features["ocr"]
            elif "text_vi" in query_features:
                ocr_list = [query_features["text_vi"]]
            elif "text_translated" in query_features:
                ocr_list = [query_features["text_translated"]]
            elif "text" in query_features:
                ocr_list = [query_features["text"]]

            raw_ocr_query = query_features.get("ocr", [query_features.get("text", "")])[0] if isinstance(query_features.get("ocr"), list) else query_features.get("text", "")

            if len(ocr_list) > 0:
                for ocr in ocr_list:
                    has_exact = bool(re.findall(r'"([^"]+)"', ocr) or re.findall(r'"([^"]+)"', raw_ocr_query))
                    search_limit = max(subquery_limit * 5, 500) if has_exact else subquery_limit
                    clean_ocr = re.sub(r'"', ' ', ocr).strip()

                    search_results = self._database.search(
                        data=[clean_ocr if clean_ocr else ocr],
                        filter=video_filter,
                        offset=0,
                        limit=search_limit,
                        anns_field=self._ocr_name,
                        search_params={"metric_type": "BM25"},
                    )
                    ocr_req_count += 1

                    if search_results and len(search_results) > 0:
                        for hit in search_results[0]:
                            fid = hit["entity"]["frame_id"]
                            doc_text = hit["entity"].get(self._ocr_name, "") or hit["entity"].get("ocr", "")

                            is_valid, phrase_count = check_exact_phrases(ocr, doc_text, fallback_query=raw_ocr_query)
                            if not is_valid:
                                continue

                            all_frame_ids.add(fid)
                            boost = 1.5 if phrase_count > 0 else 1.0
                            ocr_raw_scores[fid] = ocr_raw_scores.get(fid, 0) + hit["distance"] * boost
                            if fid not in entity_data:
                                entity_data[fid] = hit["entity"]

        # 3. ASR Search
        asr_req_count = 0
        if self._asr_name and asr_weight > 0:
            asr_list = []
            if "asr_translated" in query_features:
                asr_list = query_features["asr_translated"]
            elif "asr" in query_features:
                asr_list = query_features["asr"]
            elif "text_vi" in query_features:
                asr_list = [query_features["text_vi"]]
            elif "text_translated" in query_features:
                asr_list = [query_features["text_translated"]]
            elif "text" in query_features:
                asr_list = [query_features["text"]]

            raw_asr_query = query_features.get("asr", [query_features.get("text", "")])[0] if isinstance(query_features.get("asr"), list) else query_features.get("text", "")

            if len(asr_list) > 0:
                for asr in asr_list:
                    has_exact = bool(re.findall(r'"([^"]+)"', asr) or re.findall(r'"([^"]+)"', raw_asr_query))
                    search_limit = max(subquery_limit * 5, 500) if has_exact else subquery_limit
                    clean_asr = re.sub(r'"', ' ', asr).strip()

                    search_results = self._database.search(
                        data=[clean_asr if clean_asr else asr],
                        filter=video_filter,
                        offset=0,
                        limit=search_limit,
                        anns_field=self._asr_name,
                        search_params={"metric_type": "BM25"},
                    )
                    asr_req_count += 1

                    if search_results and len(search_results) > 0:
                        for hit in search_results[0]:
                            fid = hit["entity"]["frame_id"]
                            doc_text = hit["entity"].get(self._asr_name, "") or hit["entity"].get("asr", "")

                            is_valid, phrase_count = check_exact_phrases(asr, doc_text, fallback_query=raw_asr_query)
                            if not is_valid:
                                continue

                            all_frame_ids.add(fid)
                            boost = 1.5 if phrase_count > 0 else 1.0
                            asr_raw_scores[fid] = asr_raw_scores.get(fid, 0) + hit["distance"] * boost
                            if fid not in entity_data:
                                entity_data[fid] = hit["entity"]

        # Normalize scores per component
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
        ocr_weight: float = 0.5,
        asr_weight: float = 0.0,
        nprobe: int = 8,
    ):
        query_features = query.data[0]["features"]

        if len(query.include_video_ids) > 0:
            results = self._similarity_search(
                query_features,
                query.include_video_ids,
                0,
                10000,
                target_features,
                ocr_weight=ocr_weight,
                asr_weight=asr_weight,
                nprobe=nprobe,
                exclude_video_ids=query.exclude_video_ids,
            )
            total = len(results)
            results = results[offset : offset + limit]
        else:
            # Dynamic replenishment loop for exclude_video_ids (fast & accurate page filling)
            candidate_limit = max(300, (offset + limit) * 3) if len(query.exclude_video_ids) > 0 else max(200, offset + limit)
            db_size = self._database.get_size()
            while True:
                results = self._similarity_search(
                    query_features,
                    [],
                    0,
                    candidate_limit,
                    target_features,
                    ocr_weight=ocr_weight,
                    asr_weight=asr_weight,
                    nprobe=nprobe,
                    exclude_video_ids=query.exclude_video_ids,
                )
                if len(results) >= offset + limit or candidate_limit >= db_size or candidate_limit >= 10000:
                    break
                candidate_limit = min(db_size, candidate_limit * 2)

            total = db_size
            results = results[offset : offset + limit]

        res = {
            "results": results,
            "total": total,
            "offset": offset,
        }
        return res

    def _temporal_search(
        self,
        query: Query,
        offset: int = 0,
        limit: int = 50,
        target_features: list = [],
        /,
        ocr_weight: float = 0.5,
        asr_weight: float = 0.0,
        nprobe: int = 8,
        temporal_k: int = 2000,
        max_interval: int = 1000,
    ):
        params = {
            "query": query.data,
            "video_ids": query.include_video_ids,
            "exclude_video_ids": query.exclude_video_ids,
            "target_features": target_features,
            "ocr_weight": ocr_weight,
            "asr_weight": asr_weight,
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
                results = self._similarity_search(
                    q["features"],
                    query.include_video_ids,
                    0,
                    temporal_k,
                    target_features,
                    ocr_weight=ocr_weight,
                    asr_weight=asr_weight,
                    nprobe=nprobe,
                    exclude_video_ids=query.exclude_video_ids,
                )
                results_list.append(results)

            en = time.time()
            logger.info(f"searcher: Take {en-st:.4f} seconds to search results")

            st = time.time()
            temporal_results = self._combine_temporal_results(results_list, max_interval)
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

    def _combine_temporal_results(self, results_list: list, max_interval: int):
        best = None

        for i in range(len(results_list)):
            res = results_list[i]
            for j in range(len(res)):
                video_id, frame_id = results_list[i][j]["entity"]["frame_id"].split("#")
                results_list[i][j]["_id"] = (video_id, int(frame_id))
                results_list[i][j]["time_line"] = [frame_id]
                results_list[i][j]["time_line_scores"] = [results_list[i][j].get("scores", {})]

        for i, res in enumerate(results_list[::-1]):
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
    ):
        query_str = f"{constants.CACHE_GET_VIDEOS}:{repr(include_video_ids)}:{repr(exclude_video_ids)}"
        query_hash = hashlib.sha256(query_str.encode("utf-8")).hexdigest()

        if query_hash in self.cache:
            videos = self.cache[query_hash]
        elif len(include_video_ids) == 0 and len(exclude_video_ids) == 0:
            videos = []
        else:
            video_filter = self._get_video_filter(include_video_ids)
            query_limit = 10000 if include_video_ids else max(500, (offset + limit) * 5)
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
        if GlobalConfig.get("searcher", "ocr", "enable"):
            self._ocr_name = GlobalConfig.get("searcher", "ocr", "ocr_field") or "ocr"
        else:
            self._ocr_name = None

        if GlobalConfig.get("searcher", "asr", "enable"):
            self._asr_name = GlobalConfig.get("searcher", "asr", "asr_field") or "asr"
        else:
            self._asr_name = None

        language_models = GlobalConfig.get("searcher", "language_models") or {}

        for m in language_models.keys():
            source = GlobalConfig.get("searcher", "language_models", m, "source")
            model_name = GlobalConfig.get("searcher", "language_models", m, "model")
            arch_name = GlobalConfig.get("searcher", "language_models", m, "arch_name")
            pretrained_model = GlobalConfig.get("searcher", "language_models", m, "pretrained_model")
            target_features = GlobalConfig.get("searcher", "language_models", m, "target")
            batch_size = 1

            assert model_name is not None

            feature_extractor_cls = FeatureExtractorFactory.get(model_name)
            if feature_extractor_cls:
                feature_extractor = feature_extractor_cls.from_pretrained(
                    source=source,
                    arch_name=arch_name,
                    pretrained_model=pretrained_model,
                    name=m,
                    batch_size=batch_size,
                    device=device,
                )
            else:
                feature_extractor = None

            polite_name = f"{model_name}" + (f' from "{pretrained_model}"' if pretrained_model else "")
            if feature_extractor:
                logger.info(f"searcher: Loaded {polite_name} for searching")
            else:
                logger.error(f"searcher: {polite_name}: invalid feature extractor")
                continue

            if target_features is None or len(target_features) == 0:
                logger.error(f"searcher: {polite_name} does not have target features")
                continue

            for t in target_features:
                self._features[t] = m

            self._extractors[m] = {"feature_extractor": feature_extractor, "target_features": target_features}

        # --- Khởi tạo LLM Query Expander (bắt chước caube dòng 81-100) ---
        self._llm_expander = None
        llm_config = GlobalConfig.get("searcher", "llm") or {}
        llm_enabled = llm_config.get("enable", True)

        if llm_enabled:
            try:
                from aic51.packages.search.llm_expander import LLMQueryExpander

                self._llm_expander = LLMQueryExpander(
                    api_key=llm_config.get("api_key"),
                    model_name=llm_config.get("model_name", "openai/gpt-oss-120b"),
                    provider=llm_config.get("provider", "groq"),
                )
                if self._llm_expander.is_available:
                    logger.info("searcher: LLMQueryExpander loaded successfully")
                else:
                    logger.warning("searcher: LLMQueryExpander not available (check GROQ_API_KEY)")
                    self._llm_expander = None
            except Exception as e:
                logger.warning(f"searcher: Failed to load LLMQueryExpander: {e}")
                self._llm_expander = None

    def expand_query(self, query_text: str) -> list[str]:
        """Sinh 3 biến thể ngữ nghĩa (sát nghĩa / vai trò / nơi chốn) từ query gốc bằng LLM.

        Bắt chước caube (D:\\AIC_2026\\caube\\app.py, /expand_query):
        Trả về list các biến thể text để người dùng chọn trên giao diện UI.
        """
        if not self._llm_expander or not self._llm_expander.is_available:
            logger.warning("searcher: expand_query called but LLMQueryExpander is not available")
            return []
        return self._llm_expander.expand_query(query_text)

