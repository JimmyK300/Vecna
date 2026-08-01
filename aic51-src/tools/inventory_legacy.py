import argparse
import json

from aic51.packages.provenance import build_legacy_manifest


def main():
    parser = argparse.ArgumentParser(description="Inventory a legacy Vecna extraction directory")
    parser.add_argument("root")
    parser.add_argument("--output", required=True)
    parser.add_argument("--hash-content", action="store_true")
    args = parser.parse_args()

    report = build_legacy_manifest(args.root, hash_content=args.hash_content)
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
