import unittest
from query_rank import *
class TestQueryRank(unittest.TestCase):
    def test_identity(self):
        fs=[{'frame_id':f'a#{i}','video_id':'a','rank':i+1,'score':0} for i in range(5)]
        base=projection(fs);s={'a#1':3,'a#3':2,'a#4':1}
        self.assertEqual(rerank(base,s,s),base)
    def test_matches_accepted_when_variant_identical(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('accepted_frame_text',V5/'code/frame_text.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        base=unique_index(read_jsonl(V4/'outputs/temporal-bins/rankings.jsonl'))
        for q,r in base.items():
            old=read_json(V5/'outputs/frame-text/queries'/f'{q}.json');s=dict(zip(old['chosen'],old['logits']))
            self.assertEqual(rerank(r['arms']['temporal5s'],s,s),m.rerank_frames(r['arms']['temporal5s'],s))
if __name__=='__main__':unittest.main()
