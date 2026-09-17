import unittest
from segment import select


class SegmentTests(unittest.TestCase):
    def test_numeric_identity_and_unmapped_singletons(self):
        mapping={("V",1):("V",0),("V",2):("V",0)}
        self.assertEqual(select(["V#000001","V#000002","X#1","X#2"],mapping),["V#000001","X#1","X#2"])


if __name__=="__main__":unittest.main()
