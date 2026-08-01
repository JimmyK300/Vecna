import json
from pathlib import Path

from aic51.packages.provenance import build_manifest

from .command import BaseCommand


class ManifestCommand(BaseCommand):
    """Write a read-only baseline manifest for the current workspace."""

    def add_args(self, subparser):
        parser = subparser.add_parser("manifest", help="Write a Vecna workspace provenance manifest")
        parser.add_argument(
            "-o",
            "--output",
            default="baseline-manifest.json",
            help="Output path, relative to the workspace by default",
        )
        parser.add_argument(
            "--hash-content",
            action="store_true",
            help="Hash every video and feature artifact; can be expensive",
        )
        parser.set_defaults(func=self)

    def __call__(self, output: str, hash_content: bool, *args, **kwargs):
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = self._work_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(build_manifest(self._work_dir, hash_content=hash_content), indent=2),
            encoding="utf-8",
        )
