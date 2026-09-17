"""One cached-model semantic representation; resumable batches, no truth during retrieval."""
import datetime
import hashlib
import json
import os
import time
from pathlib import Path
from architecture_common import ROOT, PARENT, read_json, read_jsonl, write, unique_index, evaluate
from semantic import projection, fuse


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_frames(scores, records, mapping, limit=100):
    order = sorted(range(len(records)), key=lambda i: (-float(scores[i]), records[i]['segment_id'], i))
    frames, seen = [], set()
    for i in order:
        fid = mapping[i]
        if fid is None or fid in seen:
            continue
        seen.add(fid)
        frames.append({'frame_id': fid, 'video_id': records[i]['video_id'],
                       'rank': len(frames)+1, 'score': float(scores[i]), 'record_index': i})
        if len(frames) == limit:
            break
    return projection(frames)


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    policy_path = ROOT/'semantic_dense_policy.json'
    policy = read_json(policy_path)
    out = ROOT/'outputs/semantic-dense'
    out.mkdir(exist_ok=True)
    if (out/'complete.json').exists():
        raise RuntimeError('Terminal run already exists; do not relaunch')
    for name, digest in policy['inputs_sha256'].items():
        assert sha(Path(name)) == digest, name
    binding = sha(policy_path)
    manifest = {'policy_sha256': binding, 'inputs_sha256': policy['inputs_sha256']}
    if (out/'input_binding.json').exists():
        assert read_json(out/'input_binding.json') == manifest
    else:
        write(out/'input_binding.json', manifest)
    records = read_jsonl(ROOT/'outputs/semantic/records.jsonl')
    mapping = read_json(ROOT/'outputs/semantic/record_frame_mapping.json')
    queries = read_jsonl(PARENT/'outputs/fusion/queries.jsonl')
    assert len(records) == 2956 and len(mapping) == len(records) and len(queries) == 115
    texts = [r['text'] for r in records]+[q['query_text'] for q in queries]
    import numpy as np
    import torch
    from collect_dense_visibility import load_encoder
    torch.set_num_threads(policy['cpu_threads'])
    torch.set_num_interop_threads(1)
    encoder, identity = load_encoder(
        PARENT/'outputs/source-visibility/source/text_embedding_main.py',
        read_json(PARENT/'outputs/source-visibility/dense_config.json'), np, torch, out/'model_audit.json')
    batches = out/'batches'
    batches.mkdir(exist_ok=True)
    vectors, metadata = [], []
    batch_size = policy['batch_size']
    deadline = datetime.datetime.fromisoformat(policy['stop_compute_utc'])
    for start in range(0, len(texts), batch_size):
        path = batches/f'{start:05d}.npy'
        meta_path = path.with_suffix('.json')
        batch = texts[start:start+batch_size]
        text_hash = hashlib.sha256(json.dumps(batch, ensure_ascii=False).encode()).hexdigest()
        if meta_path.exists():
            info = read_json(meta_path)
            assert info['policy_sha256'] == binding and info['text_sha256'] == text_hash
            assert sha(path) == info['vectors_sha256']
            value = np.load(path, allow_pickle=False)
        else:
            if datetime.datetime.now(datetime.timezone.utc) >= deadline:
                write(out/'deadline_stop.json', {'completed_texts': start, 'required_texts': len(texts), 'status': 'INCOMPLETE'})
                return
            token_counts = [len(ids) for ids in encoder._tokenizer(batch, padding=False, truncation=False)['input_ids']]
            started = time.perf_counter_ns()
            value = encoder.get_text_features(batch)
            elapsed = time.perf_counter_ns()-started
            assert value.shape == (len(batch),1024) and np.isfinite(value).all()
            assert np.allclose(np.linalg.norm(value,axis=1),1,atol=1e-5)
            # A crash before metadata leaves an unaccepted batch; replace only that batch on resume.
            with path.with_suffix('.tmp').open('wb') as f:
                np.save(f, value, allow_pickle=False)
            os.replace(path.with_suffix('.tmp'), path)
            info = {'start':start, 'count':len(batch), 'policy_sha256':binding, 'text_sha256':text_hash,
                    'vectors_sha256':sha(path), 'wall_ns':elapsed, 'untruncated_tokens':token_counts,
                    'truncated_count':sum(n>1024 for n in token_counts)}
            write(meta_path, info)
        assert value.shape == (len(batch),1024) and np.isfinite(value).all()
        vectors.append(value)
        metadata.append(info)
    embeddings = np.concatenate(vectors)
    document_vectors, query_vectors = embeddings[:len(records)], embeddings[len(records):]
    base = unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    ranked = []
    for q, vector in zip(queries, query_vectors):
        started = time.perf_counter_ns()
        arm = select_frames(document_vectors @ vector, records, mapping)
        ranked.append({'query_id':q['query_id'], 'query_text_sha256':q['query_text_sha256'],
                       'wall_ns':time.perf_counter_ns()-started,
                       'arms':{'control':base[q['query_id']]['arms']['control'], 'semantic_dense':arm}})
    # evaluate saves every ranking before it opens frozen truth.
    summary = evaluate(ranked, out, 'semantic_dense')
    gate = bool(summary['coverage']['accepted_video_present']['rescues'] or summary['coverage']['target_coverage']['rescues'])
    summary['contribution_gate_passed'] = gate
    summary['workload'] = {'embedded_documents':len(records), 'embedded_queries':len(queries),
        'inference_batches':len(metadata), 'encoding_wall_ns':sum(m['wall_ns'] for m in metadata),
        'search_wall_ns':sum(r['wall_ns'] for r in ranked), 'cosine_pairs':len(records)*len(queries),
        'truncated_texts':sum(m['truncated_count'] for m in metadata), 'cpu_threads':policy['cpu_threads'],
        'new_model_download_bytes':0, 'external_index_writes':0}
    write(out/'summary.json', summary)
    if gate:
        integrated = ROOT/'outputs/semantic-dense-integrated'
        integrated.mkdir(exist_ok=False)
        rows = [{'query_id':r['query_id'], 'arms':{'control':r['arms']['control'],
                 'semantic_dense_rrf':fuse(r['arms']['control']['frames'],r['arms']['semantic_dense']['frames'])}} for r in ranked]
        write(integrated/'summary.json', evaluate(rows, integrated, 'semantic_dense_rrf'))
    write(out/'complete.json', {'status':'complete', 'policy_sha256':binding, 'coverage_gate':gate,
          'rankings_sha256':sha(out/'rankings.jsonl'), 'summary_sha256':sha(out/'summary.json'),
          'batch_count':len(metadata), 'vector_count':len(texts)})
    print('semantic dense complete', summary['workload'], 'gate', gate, flush=True)


if __name__ == '__main__':
    main()
