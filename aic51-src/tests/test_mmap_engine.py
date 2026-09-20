"""Automated verification test for Vecna's numpy.mmap search engine.
Verifies MmapDatabase, multi-vector similarity, BM25 text search, and Searcher integration.
"""

import time
import numpy as np
import torch
from pathlib import Path

from aic51.packages.index.mmap_database import MmapDatabase
from aic51.packages.search import Searcher


def test_mmap_database_unit():
    print("\n--- TEST 1: MmapDatabase Unit Verification ---")
    t0 = time.time()
    db = MmapDatabase("milvus")
    load_time = time.time() - t0
    
    total = db.get_size()
    print(f"Loaded MmapDatabase with {total:,} frames in {load_time:.4f}s")
    assert total > 0, "Database size must be > 0"
    assert load_time < 5.0, f"Mmap load time should be fast, got {load_time}s"
    
    # 1. Test get single record
    first_fid = db._frame_ids[0]
    rec = db.get(first_fid)
    assert len(rec) == 1, f"Expected 1 record for {first_fid}"
    assert rec[0]["frame_id"] == first_fid
    print(f"  [OK] db.get('{first_fid}') -> {rec[0]['video_id']} at pts={rec[0]['pts_time']}")

    # 2. Test vector search (CLIP)
    query_vec = np.random.randn(1, 1024).astype(np.float32)
    t_search = time.time()
    res = db.search(data=[query_vec], anns_field="image_clip_pe_l_14_336", limit=10)
    dur_ms = (time.time() - t_search) * 1000
    assert len(res) == 1 and len(res[0]) == 10
    print(f"  [OK] db.search(CLIP 1024-d, top_k=10) took {dur_ms:.2f} ms")
    
    # 3. Test vector search (SigLIP)
    siglip_query = np.random.randn(1, 1152).astype(np.float32)
    t_search = time.time()
    res_sig = db.search(data=[siglip_query], anns_field="image_siglip_so400m_384", limit=10)
    dur_ms_sig = (time.time() - t_search) * 1000
    assert len(res_sig) == 1 and len(res_sig[0]) == 10
    print(f"  [OK] db.search(SigLIP 1152-d, top_k=10) took {dur_ms_sig:.2f} ms")

    # 4. Test video filter
    vid_filter = 'frame_id like "L21_V001%"'
    res_filtered = db.search(data=[query_vec], filter=vid_filter, anns_field="image_clip_pe_l_14_336", limit=5)
    assert len(res_filtered[0]) <= 5
    for hit in res_filtered[0]:
        assert hit["entity"]["video_id"] == "L21_V001", f"Expected L21_V001, got {hit['entity']['video_id']}"
    print(f"  [OK] db.search with filter '{vid_filter}' passed (all hits from L21_V001)")

    # 5. Test BM25 sparse search
    res_bm25 = db.search(data=["đbscl sụt lún"], anns_field="ocr_sparse", search_params={"metric_type": "BM25"}, limit=5)
    assert len(res_bm25) == 1
    if res_bm25[0]:
        print(f"  [OK] db.search(BM25 OCR) returned top hit: {res_bm25[0][0]['id']} with score {res_bm25[0][0]['distance']:.2f}")


def test_searcher_integration():
    print("\n--- TEST 2: Vecna Searcher End-to-End Integration ---")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Initializing Searcher on {device}...")
    t0 = time.time()
    searcher = Searcher("milvus", device=device)
    print(f"Searcher initialized in {time.time() - t0:.2f}s")
    
    assert isinstance(searcher._database, MmapDatabase), f"Expected MmapDatabase, got {type(searcher._database)}"

    # 1. Test multimodal visual query
    query = "người đi xe máy"
    print(f"\nExecuting multimodal visual search for: '{query}'...")
    t_search = time.time()
    res = searcher.search_multimodal(
        query,
        0,
        5,
        ["image_clip_pe-l-14-336", "image_siglip_so400m-384"],
        auto_translate=False,
    )
    total_ms = (time.time() - t_search) * 1000
    print(f"Multimodal search completed in {total_ms:.2f} ms")
    assert "results" in res, "Expected 'results' key in response"
    print(f"Found {len(res['results'])} results (total: {res['total']}):")
    for r in res["results"][:3]:
        ent = r.get("entity", {})
        print(f"  - Frame: {ent.get('frame_id')} | Score: {r.get('score', 0):.4f} | pts: {ent.get('pts_time')}")

    # 2. Test video filter query
    print(f"\nExecuting search filtered to L21_V001...")
    res_vid = searcher.search_multimodal(
        "L21_V001",
        0,
        5,
        [],
    )
    assert len(res_vid["results"]) > 0
    print(f"Video query returned {len(res_vid['results'])} frames for L21_V001")


if __name__ == "__main__":
    test_mmap_database_unit()
    test_searcher_integration()
    print("\n=== ALL VECNA NUMPY.MMAP TESTS PASSED SUCCESSFULLY! ===")
