import unittest
from semantic_grounding import project_record


class GroundingTests(unittest.TestCase):
    def test_interval_score_then_frozen_tie(self):
        record={'video_id':'v','start_sec':1,'end_sec':2}
        catalog={'fps':{'v':10}}
        candidates={'v':[('v#9',9),('v#10',10),('v#20',20),('v#21',21)]}
        scores={'v#9':100,'v#10':1,'v#20':1,'v#21':100}
        self.assertEqual(project_record(record,catalog,candidates,scores,{'v#10':2,'v#20':1},'v#15'),'v#20')
        self.assertEqual(project_record(record,catalog,{},scores,{},'v#15'),'v#15')


if __name__=='__main__':unittest.main()
