from __future__ import annotations
import importlib.util, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'aic51-src'/'script'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
score=load('score_headless_vnext',SCRIPT/'score_headless_vnext.py')
builder=load('build_headless_vnext_manifest',SCRIPT/'build_headless_vnext_manifest.py')

def rec(task='kis', ranges=None, anchors=None, video='V1'):
    return {
      'canonical_query_id':'test_round_8_8::p1-x','vecna_provenance_id':'testing88_submission633::p1-x',
      'operational_phase':'P0','task_type':task,'accepted_video_id':video,
      'accepted_ranges':ranges or [],
      'scoreability':{'video':True,'range':task!='trake','trake_event':task=='trake','qa_answer':False},
      'qa_answer':{'status':'not_evaluated'},
      'trake_event_truth':[{'event_index':i+1,'submitted_frame':f,'proxy_window':{'start_frame':max(0,f-5),'end_frame':f+25},'truth_tier':'provisional_submission_anchor'} for i,f in enumerate(anchors or [])]
    }

class ScorerTests(unittest.TestCase):
    def test_video_and_range_hit(self):
        r=score.score_row(rec(ranges=[{'start_frame':10,'end_frame':20}]),[{'rank':1,'video_id':'V1','frame_id':15}])
        self.assertEqual(r['first_correct_video_rank'],1); self.assertEqual(r['range']['first_range_valid_rank'],1)
    def test_explicit_saved_rank_values_are_preserved(self):
        rr=rec(ranges=[{'start_frame':10,'end_frame':20}])
        r=score.score_row(rr,[{'rank':2,'video_id':'V2','frame_id':15},{'rank':5,'video_id':'V1','frame_id':15}])
        self.assertEqual(r['first_correct_video_rank'],5); self.assertEqual(r['range']['first_range_valid_rank'],5)
        self.assertEqual(r['video']['R@1'],0.0); self.assertEqual(r['video']['R@5'],1.0)
        self.assertEqual(r['range']['nearest_correct_video_distance_to_range']['1']['status'],'no_correct_video_in_topK')
    def test_just_outside_distance(self):
        r=score.score_row(rec(ranges=[{'start_frame':10,'end_frame':20}]),[{'rank':1,'video_id':'V1','frame_id':21}])
        self.assertIsNone(r['range']['first_range_valid_rank']); self.assertEqual(r['range']['first_correct_video_distance_to_range']['frames'],1)
    def test_no_correct_video_null_distance(self):
        r=score.score_row(rec(ranges=[{'start_frame':10,'end_frame':20}]),[{'rank':1,'video_id':'V2','frame_id':15}])
        self.assertIsNone(r['first_correct_video_rank']); self.assertEqual(r['range']['first_correct_video_distance_to_range'],{'status':'no_correct_video','frames':None})
    def test_segment_overlap_and_multiple_ranges(self):
        rr=rec(ranges=[{'start_frame':10,'end_frame':20},{'start_frame':40,'end_frame':50}])
        self.assertEqual(score.score_row(rr,[{'rank':1,'video_id':'V1','start_frame':5,'end_frame':10}])['range']['first_range_valid_rank'],1)
        self.assertEqual(score.score_row(rr,[{'rank':1,'video_id':'V1','frame_id':45}])['range']['first_range_valid_rank'],1)
    def test_trake_partial_proxy_and_absolute_distance(self):
        rr=rec(task='trake',anchors=[100,200,300,400])
        results=[{'rank':1,'video_id':'V1','frame_id':110},{'rank':2,'video_id':'V1','frame_id':204},{'rank':3,'video_id':'V1','frame_id':310}]
        r=score.score_row(rr,results)
        self.assertEqual(r['range']['status'],'not_applicable_trake')
        self.assertEqual(r['trake']['event_coverage']['5'],0.75); self.assertFalse(r['trake']['all_events_covered']['5'])
        self.assertEqual(r['trake']['events'][0]['first_hit_absolute_distance_to_submitted_frame'],10)
    def test_qa_not_evaluated(self):
        rr=rec(task='qa',ranges=[{'start_frame':1,'end_frame':2}]); r=score.score_row(rr,[])
        self.assertEqual(r['qa_answer']['status'],'not_evaluated')
    def test_manifest_actual_invariants_and_identity(self):
        doc=builder.build()
        self.assertEqual(doc['counts']['execution_rows'],48); self.assertEqual(doc['counts']['range_scoreable_non_trake'],44); self.assertEqual(doc['counts']['trake_rows'],4)
        self.assertEqual(doc['counts']['p0_rows'],23); self.assertEqual(doc['counts']['p1_rows'],25); self.assertEqual(doc['counts']['p2_rows'],0)
        p0=next(r for r in doc['records'] if r['operational_phase']=='P0'); p1=next(r for r in doc['records'] if r['operational_phase']=='P1')
        self.assertTrue(p0['canonical_query_id'].startswith('test_round_8_8::')); self.assertTrue(p0['vecna_provenance_id'].startswith('testing88_submission633::'))
        self.assertTrue(p1['canonical_query_id'].startswith('actual_p1_10_4::')); self.assertTrue(p1['vecna_provenance_id'].startswith('final_round1_10_4of13::'))
        self.assertTrue(all((r['task_type']=='trake') != r['scoreability']['range'] for r in doc['records']))
    def test_incomplete_arm_fails_by_default(self):
        doc=builder.build(); first=doc['records'][0]
        with self.assertRaisesRegex(ValueError,'incomplete saved-ranking arm'):
            score.score(doc,{first['canonical_query_id']:[]})
    def test_partial_fixture_is_explicit_and_uses_subset_denominators(self):
        doc=builder.build(); ordinary=next(r for r in doc['records'] if r['scoreability']['range']); trake=next(r for r in doc['records'] if r['scoreability']['trake_event'])
        rankings={ordinary['canonical_query_id']:[],trake['vecna_provenance_id']:[]}
        rows,summary=score.score(doc,rankings,allow_partial=True)
        self.assertEqual(len(rows),2); self.assertEqual(summary['input_status'],'partial_fixture')
        self.assertEqual(summary['manifest_counts']['execution_rows'],48); self.assertEqual(summary['scored_counts']['queries'],2)
        self.assertEqual(summary['scored_counts']['range_scoreable_non_trake'],1); self.assertEqual(summary['scored_counts']['trake_rows'],1)
        self.assertEqual(summary['range']['R@1'],0.0)
    def test_aggregate_range_denominator_excludes_trake(self):
        m={'counts':{'execution_rows':2,'video_scoreable':2,'range_scoreable_non_trake':1,'trake_rows':1,'p0_rows':2,'p1_rows':0,'p2_rows':0,'trake_events':1}}
        a=score.score_row(rec(ranges=[{'start_frame':1,'end_frame':2}]),[{'rank':1,'video_id':'V1','frame_id':1}])
        b=score.score_row(rec(task='trake',anchors=[5]),[{'rank':1,'video_id':'V1','frame_id':5}])
        s=score.aggregate([a,b],m); self.assertEqual(s['range']['R@1'],1.0); self.assertEqual(s['trake']['query_denominator'],1)

if __name__=='__main__': unittest.main()
