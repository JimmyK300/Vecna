import unittest
from aic51.packages.search.utils import Query, extract_text_entities


class TestAutoOCRBoost(unittest.TestCase):

    def test_extract_quoted_entities(self):
        text = 'Đoạn phim có logo "VTV1" và chữ "Cứu hỏa 114"'
        entities = extract_text_entities(text)
        self.assertIn("VTV1", entities)
        self.assertIn("Cứu hỏa 114", entities)

    def test_extract_codes_and_numbers(self):
        text = "xe tuần tra 113 biển số 29A-12345 phát tín hiệu"
        entities = extract_text_entities(text)
        self.assertIn("113", entities)
        self.assertIn("29A-12345", entities)

    def test_extract_named_entities(self):
        text = "Sự kiện diễn ra tại Hà Nội và TP.HCM với sự tham gia của VinFast"
        entities = extract_text_entities(text)
        self.assertIn("Hà Nội", entities)
        self.assertIn("TP.HCM", entities)
        self.assertIn("VinFast", entities)

    def test_pure_visual_query_returns_empty(self):
        text = "hai chú chó đang vui đùa trên bãi cỏ dưới ánh nắng mặt trời"
        entities = extract_text_entities(text)
        self.assertEqual(entities, [], "Pure visual action query must have NO auto OCR entities")

    def test_pure_visual_sentence_start_stopword_ignored(self):
        text = "Người phụ nữ đang nấu ăn trong gian bếp gia đình"
        entities = extract_text_entities(text)
        self.assertEqual(entities, [], "Sentence starter 'Người' must not trigger OCR")

    def test_query_parsing_integration(self):
        # 1. Visual query -> no auto_ocr
        q_vis = Query("hai con mèo nằm ngủ trên ghế sofa")
        self.assertNotIn("auto_ocr", q_vis.data[0]["features"])

        # 2. Query with entities -> auto_ocr populated
        q_ent = Query('xe cứu hỏa 114 tại Đà Nẵng có logo "HTV9"')
        features = q_ent.data[0]["features"]
        self.assertIn("auto_ocr", features)
        self.assertIn("HTV9", features["auto_ocr"])
        self.assertIn("114", features["auto_ocr"])
        self.assertIn("Đà Nẵng", features["auto_ocr"])

        # 3. Query with explicit [ocr:...] -> explicit ocr takes precedence
        q_exp = Query('[ocr:"VTV24"] xe cảnh sát đuổi bắt tội phạm')
        features_exp = q_exp.data[0]["features"]
        self.assertIn("ocr", features_exp)
        self.assertNotIn("auto_ocr", features_exp)


if __name__ == "__main__":
    unittest.main()
