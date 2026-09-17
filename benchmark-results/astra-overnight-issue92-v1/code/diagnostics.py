"""Scoring-only cross-arm diagnostics. Never produces retrieval candidates."""
from collections import Counter, defaultdict
import statistics
from architecture_common import *
from admission import PROVIDERS, balanced_admission
from segment import identity

FOLDERS=['packet-e','segment-v2','semantic','semantic-integrated','yolo','query-variants',
         'semantic-dense','semantic-dense-integrated','query-translation/provider','query-translation',
         'semantic-grounding/provider','semantic-grounding']


def diversity(frames,mapping):
    videos=Counter(f['video_id'] for f in frames)
    mapped=[mapping[identity(f['frame_id'])] for f in frames if identity(f['frame_id']) in mapping]
    n=len(frames)
    return {'slots':n,'unique_frames':len({f['frame_id'] for f in frames}),'unique_videos':len(videos),
            'repeated_video_slots':n-len(videos),'repeated_video_slot_fraction':(n-len(videos))/n if n else 0,
            'mapped_slots':len(mapped),'unique_known_segments':len(set(mapped)),
            'repeated_known_segment_slots':len(mapped)-len(set(mapped)),
            'unknown_segment_slots':n-len(mapped)}


def admission_owners(row):
    eligible=set(row['candidate_tie_order'])
    streams={p:iter(row['providers'][p]['hits']) for p in PROVIDERS}
    owners={}
    while len(owners)<min(100,len(eligible)):
        changed=False
        for p in PROVIDERS:
            for hit in streams[p]:
                fid=hit['frame_id']
                if fid in eligible and fid not in owners:
                    owners[fid]=p
                    changed=True
                    break
            if len(owners)==100:break
        if not changed:raise ValueError('unreachable eligible union')
    assert list(owners)==balanced_admission(row)
    return owners


def main():
    out=ROOT/'outputs/diagnostics-v2'
    out.mkdir(exist_ok=False)
    truth=unique_index(read_jsonl(PARENT/'inputs/canonical_truth.jsonl'))
    inherited=unique_index(read_jsonl(PARENT/'outputs/fusion/evaluation/per_query.jsonl'))
    scorer=load_scorer(PARENT/'reference/evaluate_reranker_fusion.py')
    mapping={}
    for video,data in read_json(ROOT/'outputs/segment-v2/segment_map.json').items():
        mapping.update({(video,int(fid)):(video,seg) for fid,seg in zip(data['fids'],data['segs'])})
    baseline=unique_index(read_jsonl(ROOT/'outputs/packet-e/rankings.jsonl'))
    expected={qid for qid,t in truth.items() if t['scoreable']}
    arms={}
    all_rows=[]
    for folder in FOLDERS:
        directory=ROOT/'outputs'/folder
        rankings=unique_index(read_jsonl(directory/'rankings.jsonl'))
        scores=unique_index(read_jsonl(directory/'per_query.jsonl'))
        assert set(rankings)==set(truth) and set(scores)==expected
        summary=read_json(directory/'summary.json')
        name=next(a for a in next(iter(rankings.values()))['arms'] if a!='control')
        rows=[]
        for qid in sorted(rankings):
            result=rankings[qid]
            assert result['arms']['control']==baseline[qid]['arms']['control'],(folder,qid,'control drift')
            for arm in ('control',name):
                fs=result['arms'][arm]['frames']
                assert len(fs)<=100 and len({f['frame_id'] for f in fs})==len(fs)
            if qid not in expected:continue
            target=truth[qid]
            s=scores[qid]
            assert s['arms']['control']==score_arm(result['arms']['control']['frames'],result['arms']['control']['videos'],target,scorer)
            assert s['arms'][name]==score_arm(result['arms'][name]['frames'],result['arms'][name]['videos'],target,scorer)
            metadata=inherited[qid]
            row={'family':folder,'arm':name,'query_id':qid,'phase':metadata['phase'],
                 'truth_tier':metadata['truth_tier'],'task_type':metadata['task_type'],
                 'capability_tags':metadata['capability_tags'],'primary_challenge':metadata['primary_challenge'],
                 'effective_truth_basis':metadata['effective_truth_basis'],'depths':{},'deltas':{},'ranks':{}}
            for a in ('control',name):
                fs=result['arms'][a]['frames']
                row['depths'][a]={str(k):{'coverage':coverage(fs[:k],target,scorer),
                    'diversity':diversity(fs[:k],mapping)} for k in (20,50,100)}
                cov=row['depths'][a]['100']['coverage']
                hit=s['arms'][a]['distinct_video']['metrics']['R@20']
                row['ranks'][a]={layer:s['arms'][a][layer]['first_success_rank'] for layer in LAYERS}
                row['depths'][a]['failure_class']='candidate_absent' if not cov['accepted_video_present'] else ('candidate_present_outside_video_top20' if not hit else 'video_top20_success')
            for layer in LAYERS:
                row['deltas'][layer]={metric:s['arms'][name][layer]['metrics'][metric]-value for metric,value in s['arms']['control'][layer]['metrics'].items()}
            rows.append(row)
        slices=defaultdict(list)
        for row in rows:
            for key in ('phase','task_type','truth_tier','primary_challenge','effective_truth_basis'):
                slices[key+':'+row[key]].append(row)
            for tag in row['capability_tags']:slices['capability:'+tag].append(row)
        sliced={label:{'queries':len(rs),'R20_delta':statistics.fmean(x['deltas']['distinct_video']['R@20'] for x in rs),
                  'MRR20_delta':statistics.fmean(x['deltas']['distinct_video']['MRR@20'] for x in rs),
                  'R20_rescues':[x['query_id'] for x in rs if x['deltas']['distinct_video']['R@20']>0],
                  'R20_regressions':[x['query_id'] for x in rs if x['deltas']['distinct_video']['R@20']<0]} for label,rs in slices.items()}
        arm_record={'arm':name,'folder':folder,'verdict':summary['verdict'],'metrics':summary['metrics'],
             'paired':summary['paired'],'coverage':summary['coverage'],'workload':summary.get('workload'),
             'slices':sliced,'failure_counts':{},'diversity':{}}
        for a in ('control',name):
            arm_record['failure_counts'][a]=dict(Counter(x['depths'][a]['failure_class'] for x in rows))
            arm_record['diversity'][a]={str(k):{key:statistics.fmean(x['depths'][a][str(k)]['diversity'][key] for x in rows)
                for key in rows[0]['depths'][a][str(k)]['diversity']} for k in (20,50,100)}
        arms[folder]=arm_record
        all_rows.extend(rows)
    write(out/'per_query.jsonl',all_rows,True)
    write(out/'arms.json',arms)
    # Attribute each new useful E frame to the admitting provider and every provider containing it.
    raw=unique_index(read_jsonl(PARENT/'outputs/fusion/capture-full115-v1/provider_rankings.jsonl'))
    attribution=[]
    for qid in sorted(expected):
        r=baseline[qid]
        old={f['frame_id'] for f in r['arms']['control']['frames']}
        owners=admission_owners(raw[qid])
        for frame in r['arms']['e1']['frames']:
            fid=frame['frame_id']
            if fid in old:continue
            cov=coverage([frame],truth[qid],scorer)
            if not cov['accepted_video_present'] and not any(cov['target_present']):continue
            providers={p:next((hit['rank'] for hit in raw[qid]['providers'][p]['hits'] if hit['frame_id']==fid),None) for p in PROVIDERS}
            attribution.append({'query_id':qid,'frame_id':fid,'admitting_provider':owners[fid],
                'all_provider_ranks':{p:rank for p,rank in providers.items() if rank is not None},
                'video_useful':cov['accepted_video_present'],'required_target_bits':cov['target_present'],
                'newly_covers_target_bits':[new and not old for new,old in zip(cov['target_present'],coverage(r['arms']['control']['frames'],truth[qid],scorer)['target_present'])]})
    write(out/'e1_useful_candidate_attribution.jsonl',attribution,True)
    write(out/'verification.json',{'scored_arms':len(arms),'canonical_queries_per_arm':115,'scoreable_queries_per_arm':113,
          'control_exact_all_arms':True,'all_saved_scores_recomputed_exact':True,'candidate_budget_unique100':True,
          'e1_new_useful_candidates':len(attribution),'note':'Diversity across videos is not necessarily redundant evidence. Segment metrics cover only known five-video map. Slices are descriptive, overlapping, and not held out.'})
    print('diagnostics verified',len(arms),'arms;',len(all_rows),'paired rows;',len(attribution),'new useful E1 frames')


if __name__=='__main__':main()
