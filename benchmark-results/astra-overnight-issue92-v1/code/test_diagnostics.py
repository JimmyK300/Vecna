import unittest
from diagnostics import diversity
from query_translation import routes


class DiagnosticTests(unittest.TestCase):
    def test_unknown_segments_not_collapsed(self):
        frames=[{'frame_id':'v#001','video_id':'v'},{'frame_id':'v#002','video_id':'v'},
                {'frame_id':'x#003','video_id':'x'}]
        v=diversity(frames,{('v',1):('v',0),('v',2):('v',0)})
        self.assertEqual(v['repeated_known_segment_slots'],1)
        self.assertEqual(v['unknown_segment_slots'],1)
        self.assertEqual(v['repeated_video_slots'],1)

    def test_canonical_route_retained_with_duplicate_translations(self):
        self.assertEqual(routes(['A B','a b','c d'],lambda s:s.lower().split()),[['a','b'],['c','d']])


if __name__=='__main__':unittest.main()
