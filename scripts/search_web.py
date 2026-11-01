"""Search without an API key or model calls; source snippets are not live price feeds."""

import argparse
import json

from analyst.web import search_web

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--historical", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            search_web(args.query, freshness=not args.historical), ensure_ascii=False, indent=2
        )
    )
