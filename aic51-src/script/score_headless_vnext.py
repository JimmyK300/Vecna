#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'benchmark-results' / 'headless-vnext' / 'manifest.json'
KS = (1, 5, 20)

def norm_video(v: Any) -> str: return Path(str(v or '').strip()).stem.upper()
def result_rank(item: dict[str, Any], fallback: int) -> int:
    try: rank = int(item.get('rank', fallback))
    except (TypeError, ValueError): rank = fallback
    if rank < 1: raise ValueError(f'invalid saved rank: {rank}')
    return rank

def ranked(results: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    pairs = [(result_rank(item, i), item) for i, item in enumerate(results, 1)]
    pairs.sort(key=lambda pair: pair[0])
    ranks = [rank for rank, _ in pairs]
    if len(ranks) != len(set(ranks)): raise ValueError('duplicate saved ranks are not allowed')
    return pairs

def top_k(pairs: list[tuple[int, dict[str, Any]]], k: int) -> list[tuple[int, dict[str, Any]]]:
    return [(rank, item) for rank, item in pairs if rank <= k]

def result_frames(item: dict[str, Any]) -> list[int]:
    raw = item.get('time_line', item.get('timeline'))
    if raw is None: raw = [item.get('frame_id', item.get('frame'))]
    if not isinstance(raw, (list, tuple)): raw = [raw]
    out=[]
    for v in raw:
        if v is None or isinstance(v,bool): continue
        try: out.append(int(v))
        except (TypeError,ValueError): pass
    return out

def segment(item: dict[str, Any]) -> tuple[int,int] | None:
    if item.get('start_frame') is None or item.get('end_frame') is None: return None
    a,b=int(item['start_frame']),int(item['end_frame'])
    return (min(a,b),max(a,b))

def overlaps(item: dict[str, Any], ranges: list[dict[str, Any]]) -> bool:
    seg=segment(item)
    if seg:
        a,b=seg
        return any(a <= int(r['end_frame']) and b >= int(r['start_frame']) for r in ranges)
    return any(int(r['start_frame']) <= f <= int(r['end_frame']) for f in result_frames(item) for r in ranges)

def distance_to_ranges(item: dict[str, Any], ranges: list[dict[str, Any]]) -> int | None:
    seg=segment(item)
    if seg:
        a,b=seg; vals=[]
        for r in ranges:
            s,e=int(r['start_frame']),int(r['end_frame'])
            if a <= e and b >= s: return 0
            vals.append(s-b if b < s else a-e)
        return min(vals) if vals else None
    frames=result_frames(item)
    if not frames: return None
    vals=[]
    for f in frames:
        for r in ranges:
            s,e=int(r['start_frame']),int(r['end_frame'])
            vals.append(0 if s <= f <= e else min(abs(f-s),abs(f-e)))
    return min(vals) if vals else None

def distance_to_anchor(item: dict[str, Any], anchor: int) -> int | None:
    seg=segment(item)
    if seg:
        a,b=seg
        return 0 if a <= anchor <= b else min(abs(anchor-a),abs(anchor-b))
    fs=result_frames(item)
    return min((abs(f-anchor) for f in fs), default=None)

def first_rank(pairs: list[tuple[int,dict[str,Any]]], pred) -> int | None:
    for rank,item in pairs:
        if pred(item): return rank
    return None

def score_row(record: dict[str,Any], results: list[dict[str,Any]]) -> dict[str,Any]:
    pairs=ranked(results)
    ordered=[item for _,item in pairs]
    video=norm_video(record['accepted_video_id'])
    is_correct=lambda x: norm_video(x.get('video_id') or x.get('video')) == video
    vr=first_rank(pairs,is_correct)
    out={
      'canonical_query_id':record['canonical_query_id'],'vecna_provenance_id':record['vecna_provenance_id'],
      'task_type':record['task_type'],'operational_phase':record['operational_phase'],
      'first_correct_video_rank':vr,'video':{f'R@{k}': float(vr is not None and vr<=k) for k in KS},
      'video_reciprocal_rank_at_20':0.0 if vr is None or vr>20 else 1.0/vr,
      'qa_answer':{'status':'not_evaluated'},'rankings':ordered,
    }
    if record['scoreability']['range']:
        ranges=record['accepted_ranges']
        rr=first_rank(pairs,lambda x:is_correct(x) and overlaps(x,ranges))
        first_video_item=next((x for _,x in pairs if is_correct(x)),None)
        dfirst=None if first_video_item is None else distance_to_ranges(first_video_item,ranges)
        dnear={}
        for k in KS:
            ds=[distance_to_ranges(x,ranges) for _,x in top_k(pairs,k) if is_correct(x)]
            ds=[d for d in ds if d is not None]
            dnear[str(k)]={'status':'ok' if ds else 'no_correct_video_in_topK','frames':min(ds) if ds else None}
        out['range']={
          'first_range_valid_rank':rr,
          **{f'R@{k}':float(rr is not None and rr<=k) for k in KS},
          'reciprocal_rank_at_20':0.0 if rr is None or rr>20 else 1.0/rr,
          'first_correct_video_distance_to_range':{'status':'ok' if dfirst is not None else 'no_correct_video','frames':dfirst},
          'nearest_correct_video_distance_to_range':dnear,
          'video_to_range_rank_delta': None if vr is None or rr is None else rr-vr,
          'slots_before_first_range_hit': None if rr is None else rr-1,
          'correct_video_slots_before_first_range_hit': None if rr is None else sum(1 for rank,x in pairs if rank < rr and is_correct(x)),
          'video_found_but_range_missed':{str(k): bool(vr is not None and vr<=k and (rr is None or rr>k)) for k in KS},
        }
    else: out['range']={'status':'not_applicable_trake'}
    if record['scoreability']['trake_event']:
        events=[]
        for ev in record['trake_event_truth']:
            window=[ev['proxy_window']]
            er=first_rank(pairs,lambda x:is_correct(x) and overlaps(x,window))
            hit_item=next((x for rank,x in pairs if rank==er),None) if er else None
            correct20=[x for _,x in top_k(pairs,20) if is_correct(x)]
            dproxy=[distance_to_ranges(x,window) for x in correct20]; dproxy=[d for d in dproxy if d is not None]
            danchor=[distance_to_anchor(x,int(ev['submitted_frame'])) for x in correct20]; danchor=[d for d in danchor if d is not None]
            events.append({
              'event_index':ev['event_index'],'submitted_frame':ev['submitted_frame'],'proxy_window':ev['proxy_window'],
              'truth_tier':ev['truth_tier'],'first_event_hit_rank':er,
              'first_hit_absolute_distance_to_submitted_frame':None if hit_item is None else distance_to_anchor(hit_item,int(ev['submitted_frame'])),
              'nearest_correct_video_distance_to_proxy_window@20':min(dproxy) if dproxy else None,
              'nearest_correct_video_absolute_distance_to_submitted_frame@20':min(danchor) if danchor else None,
            })
        n=len(events)
        out['trake']={'event_count':n,'events':events,
          'event_coverage':{str(k):sum(e['first_event_hit_rank'] is not None and e['first_event_hit_rank']<=k for e in events)/n for k in KS},
          'all_events_covered':{str(k):all(e['first_event_hit_rank'] is not None and e['first_event_hit_rank']<=k for e in events) for k in KS},
          'truth_tier':'provisional_submission_anchor'}
    return out

def pct(values:list[float],q:float)->float|None:
    if not values:return None
    xs=sorted(values); i=(len(xs)-1)*q; lo=math.floor(i); hi=math.ceil(i)
    return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(i-lo)

def aggregate(rows:list[dict[str,Any]], manifest:dict[str,Any])->dict[str,Any]:
    video_rows=rows; range_rows=[r for r in rows if r['range'].get('status')!='not_applicable_trake']; trake=[r for r in rows if 'trake' in r]
    out={'counts':manifest['counts'],'video':{},'range':{},'trake':{},'qa_answer':{'status':'not_evaluated'}}
    nv=len(video_rows)
    for k in KS: out['video'][f'R@{k}']=sum(r['video'][f'R@{k}'] for r in video_rows)/nv
    out['video']['MRR@20']=sum(r['video_reciprocal_rank_at_20'] for r in video_rows)/nv
    nr=len(range_rows)
    for k in KS:
        out['range'][f'R@{k}']=sum(r['range'][f'R@{k}'] for r in range_rows)/nr
        eligible=[r for r in range_rows if r['first_correct_video_rank'] is not None and r['first_correct_video_rank']<=k]
        hit=sum(r['range'][f'R@{k}'] for r in eligible)
        out['range'][f'range_success_given_video@{k}']={'numerator':int(hit),'denominator':len(eligible),'rate':None if not eligible else hit/len(eligible)}
        out['range'][f'video_found_but_range_missed@{k}']=sum(r['range']['video_found_but_range_missed'][str(k)] for r in range_rows)/nr
    out['range']['MRR@20']=sum(r['range']['reciprocal_rank_at_20'] for r in range_rows)/nr
    firstd=[r['range']['first_correct_video_distance_to_range']['frames'] for r in range_rows if r['range']['first_correct_video_distance_to_range']['frames'] is not None]
    out['range']['first_correct_video_distance_frames']={'n':len(firstd),'p50':pct(firstd,.5),'p90':pct(firstd,.9)}
    total_events=sum(r['trake']['event_count'] for r in trake)
    out['trake']['query_denominator']=len(trake); out['trake']['event_denominator']=total_events; out['trake']['truth_tier']='provisional_submission_anchor'
    for k in KS:
        hits=sum(sum(e['first_event_hit_rank'] is not None and e['first_event_hit_rank']<=k for e in r['trake']['events']) for r in trake)
        out['trake'][f'event_coverage@{k}']={'numerator':hits,'denominator':total_events,'rate':hits/total_events if total_events else None}
        allq=sum(r['trake']['all_events_covered'][str(k)] for r in trake)
        out['trake'][f'all_events_covered@{k}']={'numerator':allq,'denominator':len(trake),'rate':allq/len(trake) if trake else None}
    return out

def load_rankings(path:Path)->dict[str,list[dict[str,Any]]]:
    if path.suffix.lower()=='.json':
        obj=json.loads(path.read_text(encoding='utf-8')); rows=obj if isinstance(obj,list) else obj.get('queries',[])
    else: rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    out={}
    for row in rows:
        qid=row.get('canonical_query_id') or row.get('vecna_provenance_id') or row.get('source_qualified_id') or row.get('query_id')
        out[str(qid)]=row.get('results',row.get('top_results',[]))
    return out

def score(manifest:dict[str,Any], rankings:dict[str,list[dict[str,Any]]])->tuple[list[dict[str,Any]],dict[str,Any]]:
    scored=[]
    for record in manifest['records']:
        res=rankings.get(record['canonical_query_id'],rankings.get(record['vecna_provenance_id'],[]))
        scored.append(score_row(record,res))
    return scored,aggregate(scored,manifest)

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('rankings',type=Path); ap.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST); ap.add_argument('--out-dir',type=Path,required=True); args=ap.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8')); rankings=load_rankings(args.rankings); rows,summary=score(manifest,rankings)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/'scored.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
    (args.out_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
