import unittest
from semantic import projection,fuse


class SemanticTests(unittest.TestCase):
    def test_equal_rank_ties_retain_control_and_duplicate_votes_once_per_route(self):
        b=[{"frame_id":"V#1"},{"frame_id":"X#1"}]
        s=[{"frame_id":"W#1"},{"frame_id":"X#1"}]
        out=fuse(b,s)
        self.assertEqual([r["frame_id"] for r in out["frames"]],["X#1","V#1","W#1"])
        self.assertEqual([r["rank"] for r in out["videos"]],[1,2,3])


if __name__=="__main__":unittest.main()
