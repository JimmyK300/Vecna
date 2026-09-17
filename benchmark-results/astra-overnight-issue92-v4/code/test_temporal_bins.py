import unittest
from temporal_bins import select

class BinTests(unittest.TestCase):
    def test_boundaries_video_identity_unknown_fps(self):
        order=['a#124','a#000100','a#125','b#124','u#1','u#2']
        self.assertEqual(select(order,{'a':25,'b':25}),['a#124','a#125','b#124','u#1','u#2'])

    def test_refill_and_budget(self):
        self.assertEqual(select(['a#1','a#2','a#125','a#250'],{'a':25},budget=2),['a#1','a#125'])

if __name__=='__main__':unittest.main()
