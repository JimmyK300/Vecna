import argparse
import json

from aic51.packages.provenance.benchmark import load_queries, run_search_benchmark


def main():
    parser = argparse.ArgumentParser(description="Replay frozen queries against the Vecna Search API")
    parser.add_argument("queries", help="JSON list of query objects")
    parser.add_argument("--endpoint", default="http://127.0.0.1:1337/api/search_multimodal")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_search_benchmark(load_queries(args.queries), args.endpoint)
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
