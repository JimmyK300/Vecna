import argparse
import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "script" / "headless_benchmark.py"
CANONICAL_CSV = Path(__file__).resolve().parents[1] / "benchmark" / "issue34_headless_queries.csv"
SPEC = importlib.util.spec_from_file_location("headless_benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def result(video: str, frame: int, distance: float = 1.0, timeline=None):
    record = {
        "entity": {"frame_id": f"{video}#{frame}"},
        "distance": distance,
    }
    if timeline is not None:
        record["time_line"] = timeline
    return record


def case(targets, target_mode="any", scoreable=True):
    return {
        "query_id": "q",
        "scoreable": scoreable,
        "accepted_groups": [targets] if targets else [],
        "target_mode": target_mode,
    }


class AnswerParsingTests(unittest.TestCase):
    def test_interval_points_point_text_and_video(self):
        self.assertEqual(
            benchmark.parse_answer_string("TKIS-V003-100 -> 200", "tkis", "q"),
            [{"video_id": "V003", "kind": "interval", "start": 100, "end": 200}],
        )
        self.assertEqual(
            benchmark.parse_answer_string("TR-L26_V194-4,5,6", "trake", "q"),
            [
                {"video_id": "L26_V194", "kind": "point", "frame": 4},
                {"video_id": "L26_V194", "kind": "point", "frame": 5},
                {"video_id": "L26_V194", "kind": "point", "frame": 6},
            ],
        )
        parsed = benchmark.parse_answer_string("QA-HOA-L27_V010-5580-TEXT", "qa", "q")
        self.assertEqual(parsed[0]["frame"], 5580)
        self.assertEqual(parsed[0]["answer_text"], "TEXT")
        parsed = benchmark.parse_answer_string("QA-MARBURG-V007", "qa", "q")
        self.assertEqual(parsed, [{"video_id": "V007", "kind": "video", "answer_text": "MARBURG"}])

    def test_reversed_and_malformed_answers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "reversed interval"):
            benchmark.parse_answer_string("TKIS-V014-2985 -> 2955", "tkis", "q")
        with self.assertRaisesRegex(ValueError, "unrecognized answer suffix"):
            benchmark.parse_answer_string("TKIS-V014-garbage", "tkis", "q")


class MetricsTests(unittest.TestCase):
    def test_qa_is_evidence_only(self):
        qa = case([{"video_id": "V001", "kind": "video"}]) | {"task_type": "qa"}
        metrics = benchmark.metrics_for_results([result("V009", 1), result("V001", 2)], qa, 0)
        self.assertEqual(metrics["first_correct_rank"], 2)
        self.assertEqual(metrics["evidence_retrieval"]["evidence_recall_at_20"], 1.0)
        self.assertIsNone(metrics.get("answer_accuracy"))
        self.assertTrue(metrics["evidence_retrieval"]["evidence_no_hit_within_20"] is False)

        wrong = benchmark.metrics_for_results([result("V009", 1)], qa, 0)
        self.assertEqual(wrong["evidence_retrieval"]["evidence_recall_at_20"], 0.0)

    def test_trake_video_retrieval_and_event_candidates_are_separate(self):
        targets = [{"video_id": "V001", "kind": "point", "frame": 10}, {"video_id": "V001", "kind": "point", "frame": 20}]
        metrics = benchmark.metrics_for_results([result("V001", 99), result("V001", 10)], case(targets, "events") | {"task_type": "trake"}, 0)
        self.assertEqual(metrics["video_retrieval"]["first_correct_video_rank"], 1)
        self.assertEqual(metrics["event_candidate_coverage"]["event_candidate_recall_at_20"], 0.5)
        self.assertIsNone(metrics.get("end_to_end_trake_success"))

    def test_trake_video_uses_alternative_groups_without_event_frame_hit(self):
        trake = case(
            [{"video_id": "V001", "kind": "point", "frame": 10}], "events"
        ) | {"task_type": "trake", "accepted_groups": [
            [{"video_id": "V001", "kind": "point", "frame": 10}],
            [{"video_id": "V002", "kind": "point", "frame": 20}],
        ]}
        metrics = benchmark.metrics_for_results([result("V002", 99)], trake, 0)
        self.assertEqual(metrics["video_retrieval"]["video_recall_at_20"], 1.0)
        self.assertEqual(metrics["event_candidate_coverage"]["event_candidate_recall_at_20"], 0.0)
        self.assertEqual(metrics["localization_status"], "not_implemented")
        self.assertIsNone(metrics["end_to_end_trake_success"])
        self.assertIsNone(metrics["frame_localization_error"])

    def test_rank_boundaries_and_no_hit(self):
        target = {"video_id": "V999", "kind": "point", "frame": 7}
        for rank, expected in [
            (1, (1.0, 1.0, 1.0, 1.0)),
            (5, (0.0, 1.0, 1.0, 1.0)),
            (10, (0.0, 0.0, 1.0, 1.0)),
            (11, (0.0, 0.0, 0.0, 1.0)),
            (20, (0.0, 0.0, 0.0, 1.0)),
        ]:
            rows = [result("V001", number) for number in range(1, rank)] + [result("V999", 7)]
            metrics = benchmark.metrics_for_results(rows, case([target]), 0)
            self.assertEqual(
                (metrics["recall_at_1"], metrics["recall_at_5"], metrics["recall_at_10"], metrics["recall_at_20"]),
                expected,
            )
            self.assertEqual(metrics["first_correct_rank"], rank)
            self.assertFalse(metrics["no_hit_within_20"])

        rows = [result("V001", number) for number in range(1, 22)] + [result("V999", 7)]
        metrics = benchmark.metrics_for_results(rows, case([target]), 0)
        self.assertIsNone(metrics["first_correct_rank"])
        self.assertTrue(metrics["no_hit_within_20"])
        self.assertEqual(metrics["reciprocal_rank"], 0.0)

    def test_event_recall_and_inclusive_intervals(self):
        targets = [
            {"video_id": "V001", "kind": "point", "frame": 10},
            {"video_id": "V001", "kind": "point", "frame": 20},
        ]
        metrics = benchmark.metrics_for_results(
            [result("V001", 10), result("V001", 99)], case(targets, target_mode="events"), 0
        )
        self.assertEqual(metrics["recall_at_20"], 0.5)
        self.assertFalse(metrics["all_targets_hit_at_20"])
        self.assertIn("first_correct_rank", metrics)
        self.assertIn("reciprocal_rank", metrics)
        self.assertIn("target_ranks", metrics)
        interval = {"video_id": "V002", "kind": "interval", "start": 100, "end": 200}
        self.assertTrue(benchmark.target_matches(result("V002", 100), interval, 0))
        self.assertTrue(benchmark.target_matches(result("V002", 200), interval, 0))
        self.assertFalse(benchmark.target_matches(result("V002", 201), interval, 0))

    def test_timestamp_point_matcher_uses_per_video_fps(self):
        config = benchmark.MatchConfig(
            fps_by_video={"V001": 25.0, "L24_V033": 30.0},
            retrieval_point_tolerance_seconds=2.0,
            official_point_tolerance_frames=12,
        )
        gold = {"video_id": "V001", "kind": "point", "frame": 2471}
        # 5 frames at 25 fps = 0.2 s → retrieval HIT
        self.assertTrue(benchmark.target_matches(result("V001", 2466), gold, config))
        # 51 frames at 25 fps = 2.04 s → retrieval MISS
        self.assertFalse(benchmark.target_matches(result("V001", 2471 + 51), gold, config))
        # official ±12: 11 frames HIT, 13 MISS
        close = {"video_id": "L24_V033", "kind": "point", "frame": 16009}
        self.assertTrue(benchmark.target_matches(result("L24_V033", 16020), close, config, mode="official"))
        self.assertFalse(benchmark.target_matches(result("L24_V033", 16022), close, config, mode="official"))
        # interval still has no extra slack
        interval = {"video_id": "V002", "kind": "interval", "start": 3247, "end": 3608}
        self.assertTrue(benchmark.target_matches(result("V002", 3471), interval, config))
        self.assertFalse(benchmark.target_matches(result("V002", 3610), interval, config))

        metrics = benchmark.metrics_for_results(
            [result("V001", 2466)],
            case([gold]),
            config,
        )
        self.assertEqual(metrics["first_correct_rank"], 1)
        self.assertTrue(metrics["retrieval_hit_2s"])
        self.assertTrue(metrics["official_tolerance_hit"])
        self.assertEqual(metrics["nearest_gold_delta_frames"], 5)
        self.assertAlmostEqual(metrics["nearest_gold_delta_seconds"], 0.2)

    def test_stable_tie_break_and_result_schema(self):
        rows = [result("V002", 4, 0.8), result("V001", 9, 0.8), result("V001", 3, 0.8)]
        ordered = benchmark.normalize_results(rows, 20)
        self.assertEqual([row["entity"]["frame_id"] for row in ordered], ["V001#3", "V001#9", "V002#4"])
        with self.assertRaisesRegex(ValueError, "missing entity"):
            benchmark.normalize_results([{"distance": 1.0}], 20)
        with self.assertRaisesRegex(ValueError, "invalid entity.frame_id"):
            benchmark.normalize_results([{"entity": {"frame_id": "V001"}, "distance": 1.0}], 20)


class DatasetTests(unittest.TestCase):
    HEADER = [
        "query_id", "source", "source_question_number", "task_type", "query_mode", "query",
        "hint_1", "hint_2", "hint_3", "hint_4", "media_file", "answer", "answer_alt_1",
        "scoreable", "evaluation_scope", "provenance", "validation_state",
        "source_attachment_url", "source_attachment_sha256", "official_text_mapping",
        "media_source_url", "media_source_sha256", "media_source_size_bytes",
    ]

    def write_rows(self, rows):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8-sig", newline="", delete=False)
        with handle:
            writer = csv.DictWriter(handle, fieldnames=self.HEADER, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def base_row(self):
        return {
            "query_id": "q1", "source": "source.txt", "source_question_number": "1",
            "task_type": "tkis", "query_mode": "text", "query": "  Official, Q0\nline two  ",
            "hint_1": " First hint ", "hint_2": "Second hint\n", "hint_3": "", "hint_4": "",
            "media_file": "",
            "answer": "TKIS-V001-10 -> 20", "answer_alt_1": "", "scoreable": "true",
            "evaluation_scope": "include_current_dataset", "provenance": "issue attachment",
            "validation_state": "source_text_verified_needs_corpus_validation",
            "source_attachment_url": "https://example.test/source.txt",
            "source_attachment_sha256": "0" * 64,
            "official_text_mapping": "official_question_body_to_q0",
            "media_source_url": "", "media_source_sha256": "", "media_source_size_bytes": "",
        }

    def test_bom_multiline_q0_and_qn_are_exact(self):
        path = self.write_rows([self.base_row()])
        loaded = benchmark.load_cases(path)
        self.assertEqual(loaded[0]["query"], "  Official, Q0\nline two  ")
        self.assertEqual(loaded[0]["hints"], [" First hint ", "Second hint\n"])
        q0 = "\n".join([loaded[0]["query"], *loaded[0]["hints"][:0]])
        qn = "\n".join([loaded[0]["query"], *loaded[0]["hints"]])
        self.assertEqual(q0, "  Official, Q0\nline two  ")
        self.assertEqual(qn, "  Official, Q0\nline two  \n First hint \nSecond hint\n")

        class Searcher:
            queries = []

            def search_multimodal(self, query, *_args, **_kwargs):
                self.queries.append(query)
                return {"results": [result("V001", 10)]}

        args = argparse.Namespace(
            top_k=20,
            nprobe=32,
            temporal_k=10000,
            ocr_weight=0.5,
            asr_weight=0.0,
            max_interval=1000,
            auto_translate=False,
            en_to_vi_translate=False,
            point_tolerance_frames=0,
        )
        searcher = Searcher()
        q0_record = benchmark.run_text_variant(searcher, loaded[0], 0, args, ["image_clip"])
        qn_record = benchmark.run_text_variant(searcher, loaded[0], 2, args, ["image_clip"])
        self.assertEqual(searcher.queries, [q0, qn])
        self.assertEqual(q0_record["query_text"], q0)
        self.assertEqual(qn_record["query_text"], qn)
        self.assertEqual(q0_record["status"], "scored_provisional")

    def test_hint_gap_is_rejected(self):
        row = self.base_row()
        row["hint_1"] = ""
        with self.assertRaisesRegex(ValueError, "non-contiguous hint"):
            benchmark.load_cases(self.write_rows([row]))

    def test_scope_and_unscoreable_denominators(self):
        included = self.base_row()
        excluded = self.base_row() | {
            "query_id": "q2", "source_question_number": "2", "evaluation_scope": "exclude_different_dataset",
        }
        unscored = self.base_row() | {
            "query_id": "q3", "source_question_number": "3", "answer": "", "scoreable": "false",
            "validation_state": "source_text_verified_missing_ground_truth",
        }
        loaded = benchmark.load_cases(self.write_rows([included, excluded, unscored]))
        current = [item for item in loaded if item["evaluation_scope"] == "include_current_dataset"]
        self.assertEqual([item["query_id"] for item in current], ["q1", "q3"])
        records = [{
            "status": "scored_provisional", "source": "source.txt", "condition": "Q0", "is_primary_baseline": True,
            "is_all_hints": False, "first_correct_rank": 1, "reciprocal_rank": 1.0,
            "recall_at_1": 1.0, "recall_at_5": 1.0, "recall_at_10": 1.0, "recall_at_20": 1.0,
            "no_hit_within_20": False, "latency_ms": 1.0,
        }]
        summary = benchmark.summarize(records, current)
        self.assertEqual(summary["dataset"]["scoreable_questions"], 1)
        self.assertEqual(summary["dataset"]["unscoreable_questions"], ["q3"])


class CanonicalContractTests(unittest.TestCase):
    def setUp(self):
        self.cases = benchmark.load_cases(CANONICAL_CSV)

    def test_canonical_inventory_and_immutable_digest(self):
        inventory = benchmark.validate_canonical_issue34_inventory(self.cases, False)
        self.assertTrue(inventory["complete"])
        self.assertEqual(inventory["source_counts"], {"Questions.txt": 20, "p1.txt": 22})
        self.assertEqual(
            benchmark.canonical_content_sha256(CANONICAL_CSV),
            benchmark.EXPECTED_CANONICAL_CONTENT_SHA256,
        )
        media = {item["query_id"]: item for item in self.cases if item["query_mode"] == "media"}
        self.assertEqual(
            {query_id: item["media_source_url"] for query_id, item in media.items()},
            benchmark.MEDIA_SOURCE_URLS,
        )
        self.assertTrue(all(not item["media_source_sha256"] for item in media.values()))

    def test_manifest_rejects_wrong_source_metadata_and_unknown_id(self):
        wrong = [dict(item) for item in self.cases]
        wrong[0]["source_attachment_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "canonical source_attachment_sha256"):
            benchmark.validate_canonical_issue34_inventory(wrong, False)

        wrong_media = [dict(item) for item in self.cases]
        next(item for item in wrong_media if item["query_id"] == "set1_q04")["media_source_url"] = ""
        with self.assertRaisesRegex(ValueError, "canonical media_source_url"):
            benchmark.validate_canonical_issue34_inventory(wrong_media, False)

        unknown = [dict(item) for item in self.cases]
        unknown[0]["query_id"] = "set1_q99"
        with self.assertRaisesRegex(ValueError, "unknown Issue #34 query IDs"):
            benchmark.validate_canonical_issue34_inventory(unknown, True)

    def test_provisional_gate_and_separate_summary(self):
        current = [case for case in self.cases if case["evaluation_scope"] == "include_current_dataset"]
        with self.assertRaisesRegex(ValueError, "not validated against the current corpus"):
            benchmark.validate_run_readiness(current, False)
        self.assertEqual(len(benchmark.validate_run_readiness(current, True)), 21)

        record = {
            "status": "scored_provisional",
            "source": "p1.txt",
            "condition": "Q0",
            "is_primary_baseline": True,
            "is_all_hints": True,
            "first_correct_rank": 1,
            "reciprocal_rank": 1.0,
            "recall_at_1": 1.0,
            "recall_at_5": 1.0,
            "recall_at_10": 1.0,
            "recall_at_20": 1.0,
            "no_hit_within_20": False,
            "latency_ms": 1.0,
        }
        summary = benchmark.summarize([record], current)
        self.assertIsNone(summary["validated_metrics"])
        self.assertEqual(summary["provisional_metrics"]["primary_q0"]["mean_recall_at_10"], 1.0)

    def test_all_scope_suppresses_mixed_primary(self):
        records = []
        for source in ("Questions.txt", "p1.txt"):
            records.append({
                "status": "scored_provisional",
                "source": source,
                "condition": "Q0",
                "is_primary_baseline": True,
                "is_all_hints": True,
                "first_correct_rank": 1,
                "reciprocal_rank": 1.0,
                "recall_at_1": 1.0,
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "recall_at_20": 1.0,
                "no_hit_within_20": False,
                "latency_ms": 1.0,
            })
        partition = benchmark.summarize(records, self.cases)["provisional_metrics"]
        self.assertTrue(partition["mixed_source_aggregate_suppressed"])
        self.assertIsNone(partition["primary_q0"])
        self.assertEqual(set(partition["by_source"]), {"Questions.txt", "p1.txt"})

    def test_task_summary_partitions_and_preserves_legacy_metrics(self):
        current = [case for case in self.cases if case["evaluation_scope"] == "include_current_dataset"]
        chosen = {task: next(item for item in current if item["task_type"] == task and item["scoreable"])
                  for task in ("tkis", "qa", "trake")}
        records = []
        for task, item in chosen.items():
            metrics = benchmark.metrics_for_results(
                [result(item["accepted_groups"][0][0]["video_id"], 1)], item, 0
            )
            records.append({
                "task_type": task, "source": item["source"], "condition": "Q0",
                "is_primary_baseline": True, "is_all_hints": True,
                "status": "scored_provisional", "latency_ms": 1.0, **metrics,
            })
        summary = benchmark.summarize(records, current)
        self.assertEqual(set(summary["task_metrics"]), {"tkis", "qa", "trake"})
        self.assertIn("evidence_recall_at_20", summary["task_metrics"]["qa"]["evidence_retrieval"])
        self.assertEqual(summary["task_metrics"]["trake"]["localization_status"], "not_implemented")
        self.assertIsNone(summary["task_metrics"]["trake"]["end_to_end_trake_success"])
        self.assertIn("legacy_mixed_retrieval_diagnostic", summary)
        self.assertEqual(summary["reporting"]["primary_report"], "task_metrics")
        self.assertTrue(summary["reporting"]["legacy_reports_are_compatibility_only"])

    def test_unscoreable_qa_is_excluded_and_reasoned(self):
        current = [case for case in self.cases if case["evaluation_scope"] == "include_current_dataset"]
        q22 = next(case for case in current if case["query_id"] == "p1_q22")
        self.assertEqual(q22["task_type"], "qa")
        self.assertFalse(q22["scoreable"])
        summary = benchmark.summarize([], current)
        qa = summary["task_metrics"]["qa"]
        self.assertIn("p1_q22", qa["unscoreable_cases"])
        self.assertEqual(summary["dataset"]["unscoreable_reasons"]["p1_q22"], "missing official answer ground truth")
        self.assertIsNone(qa["evidence_retrieval"])


class GuardrailTests(unittest.TestCase):
    def args(self, **changes):
        values = {
            "top_k": 20,
            "point_tolerance_frames": 0,
            "point_tolerance_seconds": 2.0,
            "official_point_tolerance_frames": 12,
            "ocr_weight": 0.5,
            "asr_weight": 0.0,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def test_rejects_weight_sum_that_backend_would_clamp(self):
        with self.assertRaisesRegex(ValueError, "otherwise clamps ASR"):
            benchmark.validate_numeric_args(self.args(ocr_weight=0.8, asr_weight=0.8))

    def test_output_overwrite_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text("evidence", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                benchmark.validate_output_paths(output, False)
            self.assertEqual(benchmark.validate_output_paths(output, True), output.with_suffix(".summary.json"))

            second_output = Path(directory) / "second.jsonl"
            benchmark.run_metadata_path(second_output).write_text("running evidence", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "second.run.json"):
                benchmark.validate_output_paths(second_output, False)

    def test_actual_device_and_critical_hash_provenance(self):
        extractor = type("Extractor", (), {"_device": "cpu"})()
        searcher = type(
            "Searcher",
            (),
            {
                "_features": {"image_clip": "language_clip"},
                "_extractors": {"language_clip": {"feature_extractor": extractor}},
            },
        )()
        self.assertEqual(
            benchmark.actual_query_encoder_devices(searcher, ["image_clip"]),
            {"image_clip": "cpu"},
        )
        hashes = benchmark.critical_code_hashes()
        self.assertRegex(hashes["headless_benchmark"]["sha256"], r"^[0-9a-f]{64}$")

    @mock.patch.object(benchmark.subprocess, "run")
    def test_git_provenance_records_dirty_state(self, run):
        run.side_effect = [
            type("Result", (), {"stdout": "abc123\n"})(),
            type("Result", (), {"stdout": " M script.py\n?? new.py\n"})(),
        ]
        provenance = benchmark.git_provenance()
        self.assertEqual(provenance["sha"], "abc123")
        self.assertTrue(provenance["dirty"])
        self.assertEqual(provenance["status_entries"], [" M script.py", "?? new.py"])


if __name__ == "__main__":
    unittest.main()
