"""Scoring-only interval upper bound; never a100-frame retrieval arm."""
import bisect
import statistics
from architecture_common import *


def main():
    out=ROOT/'outputs/semantic-ceiling-v1'
    out.mkdir(exist_ok=False)
    records=read_jsonl(ROOT/'outputs/semantic/records.jsonl')
    catalog=read_json(ROOT/'outputs/semantic/frame_catalog.json')
    numbers={v:[pair[0] for pair in fs] for v,fs in catalog['frames'].items()}
    expanded=[]
    for r in records:
        video=r['video_id']
        lo=bisect.bisect_left(numbers[video],r['start_sec']*catalog['fps'][video])
        hi=bisect.bisect_right(numbers[video],r['end_sec']*catalog['fps'][video])
        expanded.append([video+'#'+pair[1] for pair in catalog['frames'][video][lo:hi]])
    truth=unique_index(read_jsonl(PARENT/'inputs/canonical_truth.jsonl'))
    scorer=load_scorer(PARENT/'reference/evaluate_reranker_fusion.py')
    base=unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    rows=[]
    for folder,name in [('semantic','semantic'),('semantic-dense','semantic_dense'),('query-translation/provider','translation_provider')]:
        rankings=read_jsonl(ROOT/'outputs'/folder/'rankings.jsonl')
        for r in rankings:
            qid=r['query_id'];t=truth[qid]
            if not t['scoreable']:continue
            frames=r['arms'][name]['frames']
            videos={scorer.norm_video(t['accepted_video_id'])} if t.get('accepted_video_id') else {scorer.norm_video(x['video_id']) for g in t['accepted_groups'] for x in g}
            fid_union=set(fid for f in frames for fid in expanded[f['record_index']])
            # Wrong-video frames cannot satisfy frozen targets. Filtering here only saves scorer work;
            # this diagnostic never exposes oracle-filtered candidates as a retrieval output.
            relevant=[{'frame_id':fid,'video_id':fid.split('#')[0]} for fid in sorted(fid_union) if scorer.norm_video(fid.split('#')[0]) in videos]
            cov=coverage(relevant,t,scorer)
            midpoint=coverage(frames,t,scorer)
            control=coverage(base[qid]['arms']['control']['frames'],t,scorer)
            rows.append({'provider':name,'query_id':qid,'scoring_only_unbounded_interval_ceiling':cov,
                'midpoint100':midpoint,'control100':control,'expanded_frame_union_count':len(fid_union),
                'provider_frame_slots':len(frames),'wrong_video_frame_slots':sum(scorer.norm_video(f['video_id']) not in videos for f in frames),
                'unique_candidate_videos':len({f['video_id'] for f in frames}),
                'interval_target_rescue_over_midpoint':cov['target_coverage']>midpoint['target_coverage'],
                'interval_target_rescue_over_control':cov['target_coverage']>control['target_coverage']})
    write(out/'per_query.jsonl',rows,True)
    summary={}
    for name in sorted({r['provider'] for r in rows}):
        rs=[r for r in rows if r['provider']==name]
        summary[name]={'queries':len(rs),'midpoint_complete':sum(r['midpoint100']['all_required_targets_present'] for r in rs),
            'interval_upper_bound_complete':sum(r['scoring_only_unbounded_interval_ceiling']['all_required_targets_present'] for r in rs),
            'interval_rescues_over_midpoint':[r['query_id'] for r in rs if r['interval_target_rescue_over_midpoint']],
            'interval_rescues_over_control':[r['query_id'] for r in rs if r['interval_target_rescue_over_control']],
            'wrong_video_slot_fraction':sum(r['wrong_video_frame_slots'] for r in rs)/sum(r['provider_frame_slots'] for r in rs),
            'expanded_frame_count_mean':statistics.fmean(r['expanded_frame_union_count'] for r in rs),
            'expanded_frame_count_max':max(r['expanded_frame_union_count'] for r in rs)}
    write(out/'summary.json',{'interpretation':'Oracle scoring-only ceiling over all existing frames within selected semantic intervals, often thousands of frames; NOT fixed100 retrieval, not a positive arm, not precise semantic grounding. Broad intervals can contain targets by coincidence. No truth was used in original retrieval.', 'providers':summary})
    print({name:{k:v for k,v in s.items() if not isinstance(v,list)} for name,s in summary.items()})


if __name__=='__main__':main()
