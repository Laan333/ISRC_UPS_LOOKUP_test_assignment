from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from typing import Any

import httpx


def _build_lookup_url(base_url: str, kind: str, code: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/lookup/{kind}/{code}"


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"


def _normalize_api_base(raw: str) -> str:
    """Strip, add http:// if scheme missing, drop trailing slash (paths use _join_url)."""
    s = (raw or "").strip()
    if not s:
        return s
    if "://" not in s:
        s = f"http://{s}"
    return s.rstrip("/")


def _is_openapi_json_url(url: str) -> bool:
    path = url.split("?")[0].rstrip("/")
    return path.endswith("/openapi.json") or path.endswith("openapi.json")


def _print_response(
    r: httpx.Response,
    *,
    pretty: bool,
    request_url: str | None = None,
    max_pretty_json_chars: int = 120_000,
) -> None:
    print(f"HTTP {r.status_code}")
    ct = (r.headers.get("content-type") or "").lower()
    if "application/json" in ct or r.text.strip().startswith(("{", "[")):
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            print(r.text)
            return
        openapi = bool(request_url and _is_openapi_json_url(request_url))
        sort_keys = not (pretty and openapi)
        if pretty:
            text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys)
            if openapi and len(text) > max_pretty_json_chars:
                print(text[:max_pretty_json_chars])
                print(
                    f"\n... [truncated: OpenAPI JSON is {len(text)} characters; "
                    f"save full schema, e.g.: curl -sS {shlex.quote(request_url)} -o openapi.json]"
                )
            else:
                print(text)
        else:
            print(json.dumps(data, ensure_ascii=False))
    else:
        body = r.text
        if len(body) > 2000:
            print(body[:2000] + "\n... [truncated]")
        else:
            print(body)


def _request_get(
    client: httpx.Client,
    url: str,
    *,
    pretty: bool,
    request_timeout: float | None = None,
) -> int:
    try:
        r = client.get(url, timeout=request_timeout)
    except httpx.HTTPError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 2
    _print_response(r, pretty=pretty, request_url=url)
    return 0 if r.status_code < 400 else 1


def _prompt_base_url(default: str) -> str:
    raw = input(f"API base URL [{default}]: ").strip()
    merged = raw or default
    return _normalize_api_base(merged)


def run_interactive(*, timeout: float, pretty: bool) -> int:
    default = _normalize_api_base(
        (os.getenv("BASE_URL") or "http://127.0.0.1:8000").strip()
    )
    base = _prompt_base_url(default)

    print("\nCommands: test ISRC/UPC lookup, health, readiness, or OpenAPI JSON.")
    print("Tip: use full URL with scheme, e.g. https://api.example.com\n")

    with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        while True:
            print("-" * 48)
            print(f"Current base: {base}")
            print("  1) Lookup ISRC")
            print("  2) Lookup UPC / EAN")
            print("  3) GET /health")
            print("  4) GET /ready")
            print("  5) GET /openapi.json (schema)")
            print("  6) Change base URL")
            print("  0) Exit")
            choice = input("Choice: ").strip()

            if choice == "0":
                print("Bye.")
                return 0
            if choice == "6":
                base = _prompt_base_url(base)
                continue
            if choice == "1":
                code = input("ISRC (e.g. USRC17607839): ").strip()
                if not code:
                    print("Empty code, skipped.")
                    continue
                url = _build_lookup_url(base, "isrc", code)
                print(f"GET {url}")
                _request_get(client, url, pretty=pretty)
                continue
            if choice == "2":
                code = input("UPC/EAN (8/12/13 digits): ").strip()
                if not code:
                    print("Empty code, skipped.")
                    continue
                url = _build_lookup_url(base, "upc", code)
                print(f"GET {url}")
                _request_get(client, url, pretty=pretty)
                continue
            if choice == "3":
                url = _join_url(base, "/health")
                print(f"GET {url}")
                _request_get(client, url, pretty=pretty)
                continue
            if choice == "4":
                url = _join_url(base, "/ready")
                print(f"GET {url}")
                _request_get(client, url, pretty=pretty)
                continue
            if choice == "5":
                url = _join_url(base, "/openapi.json")
                print(f"GET {url}")
                # Schema can be large; allow a longer read than the default client timeout.
                _request_get(
                    client,
                    url,
                    pretty=pretty,
                    request_timeout=max(timeout, 120.0),
                )
                continue

            print("Unknown choice. Try 0–6.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Client for ISRC/UPC lookup API (CLI or interactive)"
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive mode: set base URL, then menu (ISRC, UPC, health, ready, OpenAPI).",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL", "http://127.0.0.1:8000"),
        help='API base URL (default: env BASE_URL or "http://127.0.0.1:8000")',
    )
    parser.add_argument("--isrc", help="ISRC code, e.g. USRC17607839")
    parser.add_argument("--upc", help="UPC/EAN code, e.g. 5901234123457")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    args = parser.parse_args(argv)
    args.base_url = _normalize_api_base(args.base_url)

    if args.interactive:
        if args.isrc or args.upc:
            parser.error("Do not combine --interactive with --isrc/--upc.")
        return run_interactive(timeout=args.timeout, pretty=args.pretty)

    if bool(args.isrc) == bool(args.upc):
        parser.error("Provide exactly one of --isrc or --upc, or use --interactive.")

    kind, code = ("isrc", args.isrc) if args.isrc else ("upc", args.upc)
    url = _build_lookup_url(args.base_url, kind, code)

    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout), follow_redirects=True) as client:
            r = client.get(url)
    except httpx.HTTPError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 2

    if r.status_code >= 400:
        try:
            detail: Any = r.json()
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
