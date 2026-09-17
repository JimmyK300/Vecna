import unittest
from semantic_dense import select_frames


class DenseAdmissionTests(unittest.TestCase):
    def test_stable_ties_duplicate_mapping_and_budget(self):
        records = [{'segment_id':s,'video_id':v} for s,v in [('b','v1'),('a','v2'),('c','v2'),('d','v3')]]
        result = select_frames([1,1,.9,.8],records,['v1#1','v2#2','v2#2','v3#3'],2)
        self.assertEqual([r['frame_id'] for r in result['frames']],['v2#2','v1#1'])
        self.assertEqual([r['rank'] for r in result['videos']],[1,2])

    def test_unmapped_not_admitted(self):
        result = select_frames([1,.9],[{'segment_id':'a','video_id':'v'},{'segment_id':'b','video_id':'v'}],[None,'v#2'])
        self.assertEqual(len(result['frames']),1)


if __name__ == '__main__':
    unittest.main()
