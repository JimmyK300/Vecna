"""Drop-in replacement for MilvusDatabase using zero-copy numpy.mmap.
No Docker, no background daemon, sub-millisecond query latency.
"""

import math
import os
import re
import time
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, List, Dict, Optional

import numpy as np
from aic51.packages.config import GlobalConfig
from aic51.packages.logger import logger


class SimpleInvertedBM25:
    """Ultra-fast, zero-dependency in-memory BM25 index for OCR & ASR text search."""
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.postings: Dict[str, List[int]] = defaultdict(list)
        self.term_freqs: Dict[str, List[int]] = defaultdict(list)
        self.doc_lens: np.ndarray = np.array([], dtype=np.int32)
        self.avgdl: float = 0.0
        self.n_docs: int = 0
        self.idf: Dict[str, float] = {}

    def build(self, documents: List[str]):
        self.n_docs = len(documents)
        if self.n_docs == 0:
            return
        
        doc_lens = np.zeros(self.n_docs, dtype=np.int32)
        word_re = re.compile(r"[^\W_]+", re.UNICODE)
        
        for doc_id, text in enumerate(documents):
            tokens = word_re.findall(str(text or "").lower())
            doc_lens[doc_id] = len(tokens)
            if not tokens:
                continue
            
            # Count term frequencies in this document
            counts = defaultdict(int)
            for t in tokens:
                counts[t] += 1
            for term, count in counts.items():
                self.postings[term].append(doc_id)
                self.term_freqs[term].append(count)
                
        self.doc_lens = doc_lens
        self.avgdl = float(np.mean(doc_lens)) if self.n_docs > 0 else 1.0
        
        # Compute Robertson-Spärck Jones IDF
        for term, doc_list in self.postings.items():
            df = len(doc_list)
            # Standard Lucene/BM25 IDF: log(1 + (N - df + 0.5) / (df + 0.5))
            self.idf[term] = math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def search(self, query: str, candidate_mask: Optional[set] = None, top_k: int = 500) -> List[tuple]:
        if not self.n_docs:
            return []
        word_re = re.compile(r"[^\W_]+", re.UNICODE)
        q_tokens = word_re.findall(str(query or "").lower())
        if not q_tokens:
            return []
            
        scores = defaultdict(float)
        for token in q_tokens:
            if token not in self.postings:
                continue
            idf_val = self.idf[token]
            postings = self.postings[token]
            freqs = self.term_freqs[token]
            
            for doc_id, freq in zip(postings, freqs):
                if candidate_mask is not None and doc_id not in candidate_mask:
                    continue
                dl = self.doc_lens[doc_id]
                denom = freq + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                scores[doc_id] += idf_val * ((freq * (self.k1 + 1.0)) / denom)
                
        if not scores:
            return []
            
        sorted_hits = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return sorted_hits


class MmapDatabase(object):
    """Complete drop-in replacement for MilvusDatabase using numpy.mmap.
    Implements all query, search, and hybrid_search interfaces expected by Vecna Searcher.
    """
    SEARCH_LIMIT = 10000

    def __init__(self, collection_name: str = "milvus", do_overwrite: bool = False):
        self._collection_name = collection_name
        
        # Locate mmap indices directory
        repo_root = Path(__file__).resolve().parents[4]
        configured_dir = GlobalConfig.get("backends", "search", "mmap_dir")
        if configured_dir:
            self._indices_dir = Path(configured_dir).resolve()
        else:
            self._indices_dir = repo_root / "workspace" / "mmap_indices"
            
        logger.info(f'MmapDatabase: Initializing with indices at "{self._indices_dir}"')
        self._matrices: Dict[str, np.ndarray] = {}
        self._metadata: List[dict] = []
        self._frame_ids: np.ndarray = np.array([])
        self._video_ids: np.ndarray = np.array([])
        self._fid_to_row: Dict[str, int] = {}
        self._vid_to_rows: Dict[str, List[int]] = defaultdict(list)
        
        self._ocr_bm25 = SimpleInvertedBM25(k1=1.2, b=0.75)
        self._asr_bm25 = SimpleInvertedBM25(k1=1.2, b=0.75)
        
        self._load_indices()

    def _load_indices(self):
        if not self._indices_dir.is_dir():
            logger.warning(f'MmapDatabase: Indices directory "{self._indices_dir}" does not exist yet.')
            return

        t0 = time.time()
        meta_file = self._indices_dir / "metadata.json"
        if meta_file.is_file():
            with open(meta_file, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            logger.info(f"MmapDatabase: Loaded {len(self._metadata):,} metadata records")

        fids_file = self._indices_dir / "frame_ids.npy"
        if fids_file.is_file():
            self._frame_ids = np.load(fids_file, allow_pickle=True)
            self._fid_to_row = {fid: idx for idx, fid in enumerate(self._frame_ids)}
        elif self._metadata:
            self._frame_ids = np.array([r["frame_id"] for r in self._metadata], dtype=object)
            self._fid_to_row = {fid: idx for idx, fid in enumerate(self._frame_ids)}

        vids_file = self._indices_dir / "video_ids.npy"
        if vids_file.is_file():
            self._video_ids = np.load(vids_file, allow_pickle=True)
        elif self._metadata:
            self._video_ids = np.array([r["video_id"] for r in self._metadata], dtype=object)

        for idx, vid in enumerate(self._video_ids):
            self._vid_to_rows[vid].append(idx)

        # Mmap all available feature matrices
        for mat_file in self._indices_dir.glob("*.npy"):
            stem = mat_file.stem
            if stem in ("frame_ids", "video_ids"):
                continue
            try:
                # Open with read-only memory map (zero copy, OS manages paging)
                m = np.load(mat_file, mmap_mode="r")
                if m.ndim == 2:
                    self._matrices[stem] = m
                    logger.info(f"MmapDatabase: Mapped {stem} shape={m.shape} dtype={m.dtype}")
            except Exception as e:
                logger.error(f"MmapDatabase: Failed to mmap {mat_file}: {e}")

        # Build in-memory BM25 index for OCR & ASR if metadata is loaded
        if self._metadata:
            t_bm25 = time.time()
            ocr_texts = [r.get("ocr", "") for r in self._metadata]
            asr_texts = [r.get("asr", "") for r in self._metadata]
            self._ocr_bm25.build(ocr_texts)
            self._asr_bm25.build(asr_texts)
            logger.info(f"MmapDatabase: Inverted BM25 ready for OCR and ASR in {time.time() - t_bm25:.2f}s")

        logger.info(f"MmapDatabase: All indices ready in {time.time() - t0:.2f}s (Total frames: {self.get_size():,})")

    def process_field_name(self, field_name: str) -> str:
        return field_name.replace("-", "_")

    def get_size(self) -> int:
        return len(self._metadata)

    def get_scalar_output_fields(self) -> List[str]:
        return ["frame_id", "ocr", "asr", "pts_time", "video_id", "frame_idx"]

    def get(self, id: str, output_fields: Optional[List[str]] = None) -> List[dict]:
        row_idx = self._fid_to_row.get(id)
        if row_idx is None:
            return []
        
        record = dict(self._metadata[row_idx])
        # If output fields request vector data (e.g. for image-to-image similarity)
        if output_fields and "*" in output_fields:
            for feat_name, mat in self._matrices.items():
                record[feat_name] = mat[row_idx].tolist()
        elif output_fields:
            for f in output_fields:
                clean_f = self.process_field_name(f)
                if clean_f in self._matrices:
                    record[clean_f] = self._matrices[clean_f][row_idx].tolist()
        return [record]

    def _parse_filter_candidates(self, filter_expr: str) -> Optional[np.ndarray]:
        """Extract matching candidate row indices from Milvus filter expression."""
        if not filter_expr or not filter_expr.strip():
            return None

        # Pattern: frame_id like "L21_V001%"
        prefixes = re.findall(r'frame_id\s+like\s+"([^%"]+)', filter_expr)
        if prefixes:
            row_set = []
            for prefix in prefixes:
                vid = prefix.split("#")[0].strip()
                if vid in self._vid_to_rows:
                    row_set.extend(self._vid_to_rows[vid])
                else:
                    for v, rows in self._vid_to_rows.items():
                        if v.startswith(vid):
                            row_set.extend(rows)
            if row_set:
                return np.unique(np.array(row_set, dtype=np.int64))
            return np.array([], dtype=np.int64)

        return None

    def query(self, filter: str, offset: int = 0, limit: int = 50, output_fields: Optional[List[str]] = None) -> List[dict]:
        limit = min(limit, self.SEARCH_LIMIT)
        candidate_rows = self._parse_filter_candidates(filter)

        if candidate_rows is not None:
            selected_rows = candidate_rows[offset : offset + limit]
        else:
            total = len(self._metadata)
            selected_rows = range(offset, min(offset + limit, total))

        results = []
        for r_idx in selected_rows:
            results.append(dict(self._metadata[r_idx]))
        return results

    def search(
        self,
        data: Any,
        filter: str = "",
        offset: int = 0,
        limit: int = 50,
        anns_field: str = "image_clip_pe_l_14_336",
        search_params: dict = {},
        output_fields: Optional[List[str]] = None,
    ) -> List[List[dict]]:
        limit = min(limit, self.SEARCH_LIMIT)
        clean_field = self.process_field_name(anns_field)
        metric_type = search_params.get("metric_type", "COSINE").upper()

        candidate_rows = self._parse_filter_candidates(filter)
        candidate_set = set(candidate_rows.tolist()) if candidate_rows is not None else None

        # 1. Sparse BM25 Search
        if clean_field in ("ocr_sparse", "asr_sparse") or metric_type == "BM25":
            query_str = str(data[0]) if isinstance(data, (list, tuple)) else str(data)
            engine = self._ocr_bm25 if "ocr" in clean_field.lower() else self._asr_bm25
            top_bm25 = engine.search(query_str, candidate_mask=candidate_set, top_k=offset + limit)
            
            hits = []
            for doc_id, score in top_bm25[offset : offset + limit]:
                fid = self._frame_ids[doc_id]
                hits.append({
                    "id": fid,
                    "distance": float(score),
                    "entity": dict(self._metadata[doc_id]),
                })
            return [hits]

        # 2. Dense Vector Search (numpy.mmap with BLAS inner product)
        if clean_field not in self._matrices:
            # Fallback alias handling
            candidates = [k for k in self._matrices if clean_field in k or k in clean_field]
            if candidates:
                clean_field = candidates[0]
            else:
                logger.warning(f"MmapDatabase: Vector field {clean_field} not found in {list(self._matrices.keys())}")
                return [[]]

        matrix = self._matrices[clean_field]
        query_vec = np.asarray(data[0], dtype=np.float32).reshape(1, -1)
        
        # Normalize query vector for cosine similarity
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec /= norm

        k_target = offset + limit

        if candidate_rows is not None and len(candidate_rows) > 0:
            sub_matrix = matrix[candidate_rows]
            scores = np.asarray(sub_matrix @ query_vec[0], dtype=np.float32)
            k = min(k_target, len(scores))
            if k <= 0:
                return [[]]
            if k < len(scores):
                top_part = np.argpartition(scores, -k)[-k:]
                sorted_sub = top_part[np.argsort(scores[top_part])[::-1]]
            else:
                sorted_sub = np.argsort(scores)[::-1]
                
            sorted_indices = candidate_rows[sorted_sub][offset : offset + limit]
            top_scores = scores[sorted_sub][offset : offset + limit]
        else:
            # Full database scan with BLAS dot product across mmap memory
            scores = np.asarray(matrix @ query_vec[0], dtype=np.float32)
            k = min(k_target, len(scores))
            if k <= 0:
                return [[]]
            if k < len(scores):
                top_part = np.argpartition(scores, -k)[-k:]
                sorted_indices = top_part[np.argsort(scores[top_part])[::-1]][offset : offset + limit]
            else:
                sorted_indices = np.argsort(scores)[::-1][offset : offset + limit]
            top_scores = scores[sorted_indices]

        hits = []
        for row_idx, score in zip(sorted_indices, top_scores):
            fid = self._frame_ids[row_idx]
            hits.append({
                "id": fid,
                "distance": float(score),
                "entity": dict(self._metadata[row_idx]),
            })

        return [hits]

    def hybrid_search(
        self,
        reqs: List[Any],
        ranker: Any,
        offset: int = 0,
        limit: int = 50,
        output_fields: Optional[List[str]] = None,
    ) -> List[List[dict]]:
        limit = min(limit, self.SEARCH_LIMIT)
        if not reqs:
            return [[]]

        # Execute each search request
        rrf_scores = defaultdict(float)
        hit_entities = {}

        for req in reqs:
            field = getattr(req, "anns_field", "image_clip_pe_l_14_336")
            req_data = getattr(req, "data", [])
            req_limit = getattr(req, "limit", offset + limit)
            search_param = getattr(req, "param", {})

            res = self.search(
                data=req_data,
                anns_field=field,
                limit=req_limit,
                search_params=search_param,
            )
            if res and res[0]:
                for rank, hit in enumerate(res[0], start=1):
                    fid = hit["id"]
                    # Reciprocal Rank Fusion (standard smoothing k=60)
                    rrf_scores[fid] += 1.0 / (60.0 + rank)
                    if fid not in hit_entities:
                        hit_entities[fid] = hit["entity"]

        sorted_fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[offset : offset + limit]
        
        fused_hits = []
        for fid, score in sorted_fused:
            fused_hits.append({
                "id": fid,
                "distance": float(score),
                "entity": hit_entities[fid],
            })

        return [fused_hits]

    @classmethod
    def start_server(cls):
        """No-op for mmap database; no Docker daemon or process needed."""
        pass

    @classmethod
    def stop_server(cls):
        """No-op for mmap database."""
        pass
