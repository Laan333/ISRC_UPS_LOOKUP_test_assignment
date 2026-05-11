from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def _build_url(base_url: str, kind: str, code: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/lookup/{kind}/{code}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simple client for ISRC/UPC lookup API")
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL", "http://127.0.0.1:8000"),
        help='API base URL (default: env BASE_URL or "http://127.0.0.1:8000")',
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--isrc", help="ISRC code, e.g. USRC17607839")
    group.add_argument("--upc", help="UPC/EAN code, e.g. 5901234123457")

    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    args = parser.parse_args(argv)

    if args.isrc:
        kind, code = "isrc", args.isrc
    else:
        kind, code = "upc", args.upc

    url = _build_url(args.base_url, kind, code)

    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout), follow_redirects=True) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 2

    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:  # noqa: BLE001
            detail = r.text
        print(f"HTTP {r.status_code}: {detail}", file=sys.stderr)
        return 1

    data = r.json()
    if args.pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

