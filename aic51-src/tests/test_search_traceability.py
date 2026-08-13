import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aic51.packages.search.traceability import (
    CHANNEL_STATES,
    artifact_provider_generation_ids,
    build_search_trace,
    build_serving_composition,
    channel_state,
    load_current_index_generation,
    record_index_generation,
    resolve_frame_provenance,
    summarize_provider_generations,
)
from aic51.packages.utils.provenance import file_sha256
from aic51.packages.webui.backend.utils import process_searcher_results


class SearchTraceabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _config_get(*keys):
        config = {
            "searcher": {
                "language_models": {
                    "siglip-query": {
                        "source": "hf",
                        "model": "image_siglip",
                        "arch_name": "siglip",
                        "pretrained_model": "weights",
                        "target": ["siglip"],
                    }
                },
                "ocr": {"ocr_field": "ocr"},
                "asr": {"asr_field": "asr"},
            }
        }
        value = config
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    def _composition(self, **overrides):
        params = {
            "collection_name": "milvus",
            "query_mode": "similarity",
            "target_features": ["siglip"],
            "available_target_features": ["siglip"],
            "nprobe": 32,
            "temporal_k": 10000,
            "ocr_weight": 0.25,
            "asr_weight": 0.25,
            "max_interval": 1000,
            "auto_translate": False,
            "en_to_vi_translate": False,
            "support_ocr": True,
            "support_asr": True,
        }
        params.update(overrides)
        with patch("aic51.packages.search.traceability.GlobalConfig.get", side_effect=self._config_get):
            return build_serving_composition(self.work_dir, **params)

    def test_same_material_composition_has_same_id(self):
        first = self._composition()
        second = self._composition()
        self.assertEqual(first["serving_composition_id"], second["serving_composition_id"])

    def test_material_change_changes_composition_id(self):
        first = self._composition(nprobe=32)
        second = self._composition(nprobe=64)
        self.assertNotEqual(first["serving_composition_id"], second["serving_composition_id"])

    def test_irrelevant_nprobe_does_not_change_id_when_visual_channel_is_disabled(self):
        first = self._composition(ocr_weight=1.0, asr_weight=0.0, nprobe=32)
        second = self._composition(ocr_weight=1.0, asr_weight=0.0, nprobe=256)
        self.assertEqual(first["serving_composition_id"], second["serving_composition_id"])

    def test_missing_active_feature_lineage_cannot_resolve_as_exact(self):
        lineage = {
            "source_id": "src_1",
            "rendition_id": "rnd_1",
            "selection_generation_id": "sel_1",
            "provider_generation_id": "prv_1",
        }
        record_index_generation(
            self.work_dir,
            collection_name="milvus",
            feature_fields=["siglip", "ocr"],
            feature_configs={"siglip": {}, "ocr": {}},
            provider_generations={
                "siglip": {"state": "resolved", "provider_generation_ids": ["prv_1"]},
                "ocr": {"state": "unavailable", "provider_generation_ids": []},
            },
            video_lineage={
                "V001": {
                    "siglip": {"state": "resolved", "lineages": [lineage]}
                }
            },
            inserted_entities=1,
            do_overwrite=False,
            do_update=True,
        )
        resolved = resolve_frame_provenance(
            self.work_dir,
            "V001",
            "000001",
            collection_name="milvus",
            feature_names=["siglip", "ocr"],
        )
        self.assertNotEqual(resolved["state"], "resolved")

    def test_query_run_id_changes_independently(self):
        kwargs = {
            "collection_name": "milvus",
            "query_mode": "similarity",
            "target_features": ["siglip"],
            "available_target_features": ["siglip"],
            "nprobe": 32,
            "temporal_k": 10000,
            "ocr_weight": 0.25,
            "asr_weight": 0.25,
            "max_interval": 1000,
            "auto_translate": False,
            "en_to_vi_translate": False,
            "support_ocr": True,
            "support_asr": True,
        }
        with patch("aic51.packages.search.traceability.GlobalConfig.get", side_effect=self._config_get):
            first = build_search_trace(self.work_dir, **kwargs)
            second = build_search_trace(self.work_dir, **kwargs)
        self.assertNotEqual(first["query_run_id"], second["query_run_id"])
        self.assertEqual(
            first["serving_composition"]["serving_composition_id"],
            second["serving_composition"]["serving_composition_id"],
        )

    def test_legacy_index_is_explicitly_unavailable(self):
        generation = load_current_index_generation(self.work_dir, "milvus")
        self.assertEqual(generation["state"], "unavailable")
        self.assertIsNone(generation["index_generation_id"])
        self.assertEqual(generation["reason"], "legacy_or_unmanifested_index")

    def test_index_generation_is_recorded_and_resolved(self):
        created = record_index_generation(
            self.work_dir,
            collection_name="milvus",
            feature_fields=["siglip"],
            feature_configs={"siglip": {"index": {"datatype": "FLOAT_VECTOR"}}},
            provider_generations={
                "siglip": {"state": "resolved", "provider_generation_ids": ["prv_abc"]}
            },
            video_lineage={},
            inserted_entities=12,
            do_overwrite=False,
            do_update=True,
        )
        loaded = load_current_index_generation(self.work_dir, "milvus")
        self.assertEqual(loaded["state"], "resolved")
        self.assertEqual(loaded["index_generation_id"], created["index_generation_id"])

    def test_all_channel_states_are_distinctly_representable(self):
        values = {state: channel_state(state)["state"] for state in CHANNEL_STATES}
        self.assertEqual(set(values.values()), CHANNEL_STATES)

    def test_hash_matching_artifact_provenance_only(self):
        feature_path = self.work_dir / "features/V001/000001/siglip.npy"
        feature_path.parent.mkdir(parents=True)
        feature_path.write_bytes(b"current-feature")
        relative = feature_path.relative_to(self.work_dir).as_posix()
        current_sha = file_sha256(feature_path)
        provenance = {
            relative: [
                {"content_sha256": "0" * 64, "provider_generation_id": "prv_stale"},
                {"content_sha256": current_sha, "provider_generation_id": "prv_current"},
            ]
        }
        self.assertEqual(
            artifact_provider_generation_ids(self.work_dir, feature_path, provenance),
            {"prv_current"},
        )

    def test_provider_summary_does_not_fabricate_missing_identity(self):
        summary = summarize_provider_generations(["ocr", "siglip"], {"siglip": {"prv_a"}})
        self.assertEqual(summary["siglip"]["state"], "resolved")
        self.assertEqual(summary["ocr"]["state"], "unavailable")

    def test_frame_provenance_resolves_from_index_generation_not_current_registry(self):
        lineage = {
            "source_id": "src_1",
            "rendition_id": "rnd_1",
            "selection_generation_id": "sel_1",
            "provider_generation_id": "prv_1",
        }
        record_index_generation(
            self.work_dir,
            collection_name="milvus",
            feature_fields=["siglip"],
            feature_configs={"siglip": {}},
            provider_generations={
                "siglip": {"state": "resolved", "provider_generation_ids": ["prv_1"]}
            },
            video_lineage={
                "V001": {
                    "siglip": {"state": "resolved", "lineages": [lineage]}
                }
            },
            inserted_entities=1,
            do_overwrite=False,
            do_update=True,
        )
        resolved = resolve_frame_provenance(
            self.work_dir,
            "V001",
            "000001",
            collection_name="milvus",
            feature_names=["siglip"],
        )
        self.assertEqual(resolved["state"], "resolved")
        self.assertEqual(resolved["source_id"], "src_1")
        self.assertTrue(resolved["frame_evidence_id"].startswith("ev_frame_"))

    def test_v2_projection_preserves_legacy_fields_order_and_scores(self):
        searcher_res = {
            "results": [
                {
                    "entity": {"frame_id": "V001#000002", "ocr": "two", "asr": ""},
                    "distance": 0.9,
                    "scores": {"final": 0.9, "clip": 0.9, "ocr": 0.0, "asr": 0.0},
                },
                {
                    "entity": {"frame_id": "V001#000001", "ocr": "one", "asr": "hello"},
                    "distance": 0.8,
                    "scores": {"final": 0.8, "clip": 0.7, "ocr": 0.1, "asr": 0.0},
                },
            ],
            "total": 2,
            "offset": 0,
        }
        with patch("aic51.packages.webui.backend.utils.get_fps", return_value=25):
            legacy = process_searcher_results(searcher_res)
            v2 = process_searcher_results(
                searcher_res,
                include_traceability=True,
                work_dir=self.work_dir,
            )

        self.assertEqual([f["id"] for f in legacy["frames"]], [f["id"] for f in v2["frames"]])
        for old, new in zip(legacy["frames"], v2["frames"]):
            for key, value in old.items():
                self.assertEqual(new[key], value)
            self.assertIn("traceability", new)
        self.assertEqual(legacy["total"], v2["total"])
        self.assertEqual(legacy["offset"], v2["offset"])


if __name__ == "__main__":
    unittest.main()
