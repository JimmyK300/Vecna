"""Truth-blind membership change from PR91 Packet E; no score normalization here."""
PROVIDERS = ("qwen", "siglip", "ocr_sparse", "asr_sparse")


def balanced_admission(row, budget=100):
    eligible = set(row["candidate_tie_order"])
    streams = {p: iter(row["providers"][p]["hits"]) for p in PROVIDERS}
    selected, seen = [], set()
    while len(selected) < min(budget, len(eligible)):
        changed = False
        for provider in PROVIDERS:
            for hit in streams[provider]:
                fid = hit["frame_id"]
                if fid in eligible and fid not in seen:
                    selected.append(fid)
                    seen.add(fid)
                    changed = True
                    break
            if len(selected) == budget:
                break
        if not changed:
            break
    if len(selected) != min(budget, len(eligible)):
        raise ValueError("eligible union not reachable from active provider streams")
    return selected
