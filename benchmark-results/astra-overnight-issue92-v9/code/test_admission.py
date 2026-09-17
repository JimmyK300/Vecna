import unittest
from candidate_admission import admit
def frame(v,n):return {'frame_id':f'{v}#{n}','video_id':v,'rank':n+1,'score':0}
class AdmissionTests(unittest.TestCase):
 def test_preserves_videos_and_first(self):
  base=[frame('a',i) for i in range(99)]+[frame('b',99)]
  sem=[frame('a',100)]+[frame(f'new{i}',0) for i in range(25)]
  result=admit(base,sem)
  self.assertEqual(len(result),100);self.assertEqual(result[0],base[0])
  self.assertEqual(len({f['frame_id'] for f in result}),100)
  self.assertTrue({'a','b'}<={f['video_id'] for f in result})
  self.assertEqual(len({f['video_id'] for f in result}),22)
 def test_all_unique_no_eviction(self):
  base=[frame(str(i),i) for i in range(100)]
  self.assertEqual(admit(base,[frame('new',0)]),base)
if __name__=='__main__':unittest.main()
