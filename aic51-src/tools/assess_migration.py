import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yaml import safe_load

from aic51.packages.provenance import assess_legacy_migration


def main():
    parser = argparse.ArgumentParser(description="Assess legacy Vecna artifact migration decisions")
    parser.add_argument("legacy_report")
    parser.add_argument("target_config")
    parser.add_argument("--legacy-keyframe-policy", required=True)
    parser.add_argument("--target-keyframe-policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.legacy_report, encoding="utf-8") as stream:
        legacy_report = json.load(stream)
    with open(args.target_config, encoding="utf-8") as stream:
        target_config = safe_load(stream) or {}

    result = assess_legacy_migration(
        legacy_report,
        target_features=target_config.get("features") or {},
        legacy_keyframe_policy=args.legacy_keyframe_policy,
        target_keyframe_policy=args.target_keyframe_policy,
    )
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
