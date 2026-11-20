#!/usr/bin/env python3
"""Assemble a static preview, verifying every deployed file against its manifest."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BASE = "https://liangheng121.github.io/WE-Dream-web/"


def checked_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid manifest path: {value}")
    return Path(*path.parts)


def verify(data, item):
    if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError(f"Content verification failed: {item['path']}")


def assemble(item, output, local_media):
    relative = checked_path(item["path"])
    local = ROOT / relative
    if item.get("source"):
        if item["source"] != SOURCE_BASE + item["path"]:
            raise ValueError(f"Unexpected source: {item['path']}")
        if local_media:
            data = (local_media / relative).read_bytes()
            verify(data, item)
        else:
            for attempt in range(3):
                try:
                    url = item["source"]
                    parsed = urlsplit(url)
                    url = parsed._replace(path=quote(parsed.path, safe="/")).geturl()
                    request = Request(url, headers={"User-Agent": "WE-Dream-static-preview", "Accept-Encoding": "identity"})
                    with urlopen(request, timeout=90) as response:
                        data = response.read(item["bytes"] + 1)
                    verify(data, item)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
    else:
        data = local.read_bytes()
        verify(data, item)
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return len(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    parser.add_argument("--local-media", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Output already exists; use a new directory.")
    output.mkdir(parents=True)
    items = json.loads((ROOT / "deployment-manifest.json").read_text())["files"]
    if len({item["path"] for item in items}) != len(items):
        raise SystemExit("Duplicate paths in deployment manifest.")
    total = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(assemble, item, output, args.local_media) for item in items]
        for index, future in enumerate(as_completed(futures), 1):
            total += future.result()
            if index % 100 == 0:
                print(f"Verified {index}/{len(items)} files", flush=True)
    if total >= 1_000_000_000:
        raise SystemExit("Preview exceeds the configured Pages size budget.")
    print(f"Ready: {len(items)} verified files, {total:,} bytes", flush=True)


if __name__ == "__main__":
    main()
