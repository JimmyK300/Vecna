import unittest
from semantic_crossencoder import rerank, projection

class RerankTests(unittest.TestCase):
    def base(self):
        frames = [{'video_id':f'v{i%25:02}', 'frame_id':f'v{i%25:02}#{i}', 'rank':i+1, 'score':100-i} for i in range(100)]
        return projection(frames)

    def test_uncovered_and_tail_fixed(self):
        base=self.base()
        result=rerank(base,{'v00':-5.,'v02':6.,'v19':10.})
        before=[r['video_id'] for r in base['videos']]
        after=[r['video_id'] for r in result['videos']]
        for i in range(25):
            if i not in (0,2,19): self.assertEqual(before[i],after[i])
        self.assertEqual({r['frame_id'] for r in base['frames']},{r['frame_id'] for r in result['frames']})

    def test_ties_keep_control_video_order(self):
        base=self.base()
        result=rerank(base,{r['video_id']:0 for r in base['videos'][:20]})
        self.assertEqual([r['video_id'] for r in base['videos']],[r['video_id'] for r in result['videos']])

    def test_within_video_order_preserved(self):
        base=self.base()
        result=rerank(base,{'v00':-5.,'v02':6.,'v19':10.})
        for v in {r['video_id'] for r in base['frames']}:
            self.assertEqual([r['frame_id'] for r in base['frames'] if r['video_id']==v],
                [r['frame_id'] for r in result['frames'] if r['video_id']==v])

if __name__=='__main__': unittest.main()
