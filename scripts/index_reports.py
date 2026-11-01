import argparse
import json

from analyst.rag import ReportIndex

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index the locked public PDF corpus locally")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--query")
    args = parser.parse_args()
    index = ReportIndex()
    if args.download:
        index.download()
    result = index.search(args.query) if args.query else index.ingest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
