import unittest
from audit_artifacts import classify

class AcceptanceRegression(unittest.TestCase):
    def test_success_filter_is_not_caption(self):
        self.assertEqual(classify("This request was blocked by Gemini's filters.", 'structured-evidence')[0], 'filter_response')

    def test_preamble_does_not_pass_raw_json_contract(self):
        self.assertEqual(classify('Commentary {"overview":"scene"}', 'structured-evidence')[0], 'json_with_extra_text')

    def test_truncated_output_not_salvaged(self):
        self.assertEqual(classify('{"overview":"scene"', 'structured-evidence')[0], 'invalid_output')

    def test_strict_json(self):
        self.assertEqual(classify('{"overview":"scene"}', 'structured-evidence')[0], 'strict_json')

if __name__ == '__main__':
    unittest.main()
