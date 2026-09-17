import unittest
from object_rank import reorder
class TestRank(unittest.TestCase):
    def test_no_evidence(self):
        frames=[{'frame_id':f'a#{i}','video_id':'a','rank':i+1,'score':0} for i in range(100)]
        self.assertEqual(reorder(frames,{})['frames'],frames)
    def test_protection_and_membership(self):
        frames=[{'frame_id':f'a#{i}','video_id':'a','rank':i+1,'score':0} for i in range(100)]
        out=reorder(frames,{'a#3':1})['frames']
        self.assertEqual(out[0],frames[0]);self.assertEqual(out[1]['frame_id'],'a#3')
        self.assertEqual({f['frame_id'] for f in out},{f['frame_id'] for f in frames})
if __name__=='__main__':unittest.main()
