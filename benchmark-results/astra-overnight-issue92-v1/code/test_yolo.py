import unittest
from yolo import mentions,normalize


class YoloTests(unittest.TestCase):
    def test_boundary_negation_and_accents(self):
        p={"categories":{"bicycle":{"query":["xe dap","bike"]}},"negative_query_markers":["khong"]}
        self.assertTrue(mentions("Một chiếc xe đạp.",p)["applicable"])
        self.assertFalse(mentions("Không có xe đạp",p)["applicable"])
        self.assertFalse(mentions("motorbike",p)["applicable"])


if __name__=="__main__":unittest.main()
