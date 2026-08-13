import ast
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "script" / "issue34_runtime_bundle.py"
SPEC = importlib.util.spec_from_file_location("issue34_runtime_bundle", SCRIPT)
bundle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bundle)


class PathAndSecretGuardTests(unittest.TestCase):
    def test_backup_name_and_containment_are_strict(self):
        self.assertEqual(bundle.validate_backup_name("vecna_issue34.current-1"), "vecna_issue34.current-1")
        for value in ("", ".", "..", "../escape", "a/b", r"a\b", "-leading"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bundle.validate_backup_name(value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            with self.assertRaisesRegex(RuntimeError, "escapes"):
                bundle.safe_child(root, "../escape", "test child")

    def test_secret_detection_never_needs_the_secret_value(self):
        data = {
            "nested": {"api_token": "do-not-print"},
            "url": "https://user:password@example.test/repo?token=also-secret",
        }
        self.assertEqual(bundle.secret_paths(data), ["nested.api_token", "url"])
        with self.assertRaisesRegex(RuntimeError, "nested.api_token") as caught:
            bundle.assert_no_secrets(data, "test config")
        self.assertNotIn("do-not-print", str(caught.exception))
        self.assertEqual(
            bundle.sanitize_url(data["url"]), "https://example.test/repo"
        )
        redacted = bundle.redact_known_secrets(
            "password=do-not-print", {"password": "do-not-print"}
        )
        self.assertEqual(redacted, "password=<redacted>")
        bundle.assert_compose_transfer_safe(
            {"services": {"minio": {"environment": {"MINIO_SECRET_KEY": "minioadmin"}}}}
        )
        with self.assertRaisesRegex(RuntimeError, "services.minio.environment.MINIO_SECRET_KEY"):
            bundle.assert_compose_transfer_safe(
                {"services": {"minio": {"environment": {"MINIO_SECRET_KEY": "production-secret"}}}}
            )

    def test_custom_containers_replace_defaults(self):
        parser = bundle.build_parser()
        base = [
            "inventory",
            "--workspace",
            ".",
            "--manifest",
            "manifest.json",
            "--target-features",
            "feature",
        ]
        self.assertIsNone(parser.parse_args(base).container)
        custom = parser.parse_args([*base, "--container", "one", "--container", "two"])
        self.assertEqual(custom.container, ["one", "two"])

    def test_offline_cache_variables_are_forced_not_defaulted(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {
                "HF_HUB_OFFLINE": "0",
                "TRANSFORMERS_OFFLINE": "0",
                "HF_HUB_CACHE": str(Path(temporary) / "outside"),
            },
            clear=False,
        ):
            root = Path(temporary) / "bundle-cache"
            values = bundle.force_offline_environment(
                hf_home=root,
                hub_cache=root / "hub",
                torch_home=root / "torch",
            )
            self.assertEqual(values["HF_HUB_OFFLINE"], "1")
            self.assertEqual(values["TRANSFORMERS_OFFLINE"], "1")
            self.assertEqual(os.environ["HF_HUB_CACHE"], str((root / "hub").resolve()))
            self.assertEqual(os.environ["HUGGINGFACE_HUB_CACHE"], str((root / "hub").resolve()))


class MinimumSourceAndCacheTests(unittest.TestCase):
    def test_retrieval_source_slice_is_python_parseable_and_has_no_frontend(self):
        paths = bundle.runtime_source_paths()
        self.assertGreaterEqual(len(paths), 30)
        for path in paths:
            relative = path.relative_to(bundle.REPO_ROOT).as_posix()
            self.assertNotIn("/frontend/", f"/{relative}/")
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_model_copy_uses_only_resolved_snapshot_and_refs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source" / "models--org--model"
            snapshot = repo / "snapshots" / "abc123"
            snapshot.mkdir(parents=True)
            (snapshot / "model.bin").write_bytes(b"weights")
            (repo / "refs").mkdir()
            (repo / "refs" / "main").write_text("abc123", encoding="utf-8")
            (repo / "blobs").mkdir()
            (repo / "blobs" / "unused").write_bytes(b"unused blob")
            old = repo / "snapshots" / "old"
            old.mkdir()
            (old / "old.bin").write_bytes(b"old")
            manifest = {
                "query_models": [
                    {
                        "repo_id": "org/model",
                        "revision": "abc123",
                        "cache_repo_name": repo.name,
                        "cache_repo_path": str(repo),
                        "snapshot_path": str(snapshot),
                        "snapshot_files": bundle.tree_records(snapshot),
                    }
                ]
            }
            destination = root / "out"
            destination.mkdir()
            bundle.copy_model_caches(manifest, destination)
            copied = destination / repo.name
            self.assertTrue((copied / "snapshots" / "abc123" / "model.bin").is_file())
            self.assertEqual((copied / "refs" / "main").read_text(), "abc123")
            self.assertFalse((copied / "blobs").exists())
            self.assertFalse((copied / "snapshots" / "old").exists())


class ClosedBundleTests(unittest.TestCase):
    def make_bundle(self, root: Path) -> Path:
        directory = root / "runtime-bundle"
        (directory / "runtime").mkdir(parents=True)
        (directory / "runtime" / "config.yaml").write_text("x: 1\n", encoding="utf-8")
        bundle.write_bundle_manifest(directory, {"bundle_manifest_version": 2})
        return directory

    def test_closed_file_set_rejects_tampering_and_additions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.make_bundle(root)
            bundle.verify_bundle_hashes(directory)
            extra = directory / "unexpected.txt"
            extra.write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not closed"):
                bundle.verify_bundle_hashes(directory)
            extra.unlink()
            (directory / "runtime" / "config.yaml").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                bundle.verify_bundle_hashes(directory)

    def test_manifest_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.make_bundle(Path(temporary))
            manifest_path = directory / "bundle-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["relative_path"] = "../escape"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unsafe bundle path"):
                bundle.verify_bundle_hashes(directory)


class IndexReadinessTests(unittest.TestCase):
    def test_indexes_must_be_nonempty_and_demonstrably_finished(self):
        client = mock.Mock()
        client.list_indexes.return_value = []
        with self.assertRaisesRegex(RuntimeError, "has no indexes"):
            bundle.index_readiness(client, "collection")

        client.list_indexes.return_value = ["vector"]
        client.describe_index.return_value = {"index_name": "vector"}
        with mock.patch.object(bundle, "_index_progress", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "not demonstrably Finished"):
                bundle.index_readiness(client, "collection")

        client.describe_index.return_value = {
            "index_name": "vector",
            "state": "Finished",
        }
        with mock.patch.object(bundle, "_index_progress", return_value=None):
            result = bundle.index_readiness(client, "collection")
        self.assertIn("vector", result)


class PortabilityRegressionTests(unittest.TestCase):
    def test_target_docker_signature_ignores_only_volume_project_prefixes(self):
        source = [
            {
                "name": "milvus-standalone",
                "configured_image": "milvusdb/milvus:v2.4.0",
                "image_id": "sha256:same",
                "repo_digests": ["milvusdb/milvus@sha256:same"],
                "mounts": [
                    {
                        "type": "volume",
                        "name": "source_standalone",
                        "destination": "/var/lib/milvus",
                        "rw": True,
                    }
                ],
            }
        ]
        target = json.loads(json.dumps(source))
        target[0]["mounts"][0]["name"] = "target_standalone"
        self.assertNotEqual(bundle.docker_signature(source), bundle.docker_signature(target))
        self.assertEqual(
            bundle.docker_signature(source, include_volume_names=False),
            bundle.docker_signature(target, include_volume_names=False),
        )

    def test_smoke_guard_blocks_writes_and_preserves_load_state(self):
        class FakeMilvusClient:
            def create_collection(self):
                return "created"

            def load_collection(self):
                return "loaded"

            def release_collection(self):
                return "released"

        fake_pymilvus = types.SimpleNamespace(MilvusClient=FakeMilvusClient)
        with mock.patch.dict(sys.modules, {"pymilvus": fake_pymilvus}):
            with bundle.block_milvus_writes():
                with self.assertRaisesRegex(RuntimeError, "forbids Milvus writes"):
                    FakeMilvusClient().create_collection()
                self.assertIsNone(FakeMilvusClient().load_collection())
                self.assertIsNone(FakeMilvusClient().release_collection())
            self.assertEqual(FakeMilvusClient().create_collection(), "created")
            self.assertEqual(FakeMilvusClient().load_collection(), "loaded")
            self.assertEqual(FakeMilvusClient().release_collection(), "released")

    def test_package_paths_cannot_recurse_or_overlap_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_dir = root / "bundle"
            backup_dir = root / "backups" / "snapshot"
            with self.assertRaisesRegex(RuntimeError, "recursively archive"):
                bundle.validate_package_outputs(
                    bundle_dir,
                    bundle_dir / "bundle.zip",
                    root / "bundle.zip.sha256",
                    backup_dir,
                )
            with self.assertRaisesRegex(RuntimeError, "overlaps logical-backup"):
                bundle.validate_package_outputs(
                    backup_dir / "bundle",
                    root / "bundle.zip",
                    root / "bundle.zip.sha256",
                    backup_dir,
                )
            bundle.validate_package_outputs(
                bundle_dir,
                root / "bundle.zip",
                root / "bundle.zip.sha256",
                backup_dir,
            )

    def test_smoke_identity_uses_all_twenty_judged_results(self):
        results = [
            {"frame_id": f"video#{index}", "time_line": [index]}
            for index in range(25)
        ]
        self.assertEqual(len(bundle.normalized_ids(results)), 20)
        changed_at_twenty = json.loads(json.dumps(results))
        changed_at_twenty[19]["frame_id"] = "different#19"
        self.assertNotEqual(
            bundle.normalized_ids(results), bundle.normalized_ids(changed_at_twenty)
        )


if __name__ == "__main__":
    unittest.main()
