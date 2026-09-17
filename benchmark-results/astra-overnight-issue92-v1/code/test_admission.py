import unittest
from admission import balanced_admission, PROVIDERS


def row(streams, eligible):
    return {"candidate_tie_order": eligible, "providers": {
        p: {"hits": [{"frame_id": x} for x in s]} for p, s in zip(PROVIDERS, streams)}}


class AdmissionTests(unittest.TestCase):
    def test_skip_duplicate_and_ineligible_within_turn(self):
        r = row([["x", "a", "b"], ["a", "c"], ["d"], ["e"]], list("abcde"))
        self.assertEqual(balanced_admission(r, 4), ["a", "c", "d", "e"])

    def test_exhausted_streams_and_short_union(self):
        self.assertEqual(balanced_admission(row([["a", "b"], [], [], []], ["b", "a"])), ["a", "b"])

    def test_fail_closed_unreachable_union(self):
        with self.assertRaises(ValueError):
            balanced_admission(row([[], [], [], []], ["a"]))


if __name__ == "__main__":
    unittest.main()
