#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
AFFILIATE_FILE = ROOT / "data" / "affiliate_links.json"
GO_DIR = ROOT / "go"
MANIFEST_FILE = ROOT / ".generated_go_manifest.json"
SITE_NAME = "WealthPulse"

REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Redirecting…</title>
<meta name="robots" content="noindex, nofollow">
<meta http-equiv="refresh" content="0; url={url}">
</head>
<body>
<p>Redirecting to <strong>{name}</strong>…</p>
<p>If nothing happens, <a rel="sponsored nofollow" href="{url}">continue here</a>.</p>
<script>window.location.replace({url_js});</script>
</body>
</html>
"""


def is_real_url(url: str) -> bool:
    return bool(url) and url.startswith(("http://", "https://")) and not url.startswith("REPLACE_")


def js_string(value: str) -> str:
    return json.dumps(value)


def load_affiliates() -> dict:
    with open(AFFILIATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def iter_usable_products(db: dict):
    for category, products in db.items():
        if category.startswith("_") or not isinstance(products, list):
            continue
        for p in products:
            if p.get("active") is not True:
                continue
            url = p.get("url", "")
            go_slug = p.get("go_slug", "").strip()
            if not go_slug or not is_real_url(url):
                continue
            yield p


def load_manifest() -> list[str]:
    if MANIFEST_FILE.exists():
        try:
            return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_manifest(slugs: list[str]) -> None:
    MANIFEST_FILE.write_text(json.dumps(sorted(slugs), indent=2), encoding="utf-8")


def build_redirects() -> None:
    db = load_affiliates()
    GO_DIR.mkdir(exist_ok=True)
    current_slugs: list[str] = []

    for p in iter_usable_products(db):
        slug = p["go_slug"].strip()
        current_slugs.append(slug)
        dest = GO_DIR / slug
        dest.mkdir(parents=True, exist_ok=True)
        html = REDIRECT_HTML.format(name=p.get("name", slug), url=p["url"], url_js=js_string(p["url"]))
        (dest / "index.html").write_text(html, encoding="utf-8")
        print(f"Built /go/{slug}")

    old_slugs = set(load_manifest())
    for stale in sorted(old_slugs - set(current_slugs)):
        stale_dir = GO_DIR / stale
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
            print(f"Removed stale /go/{stale}")

    save_manifest(current_slugs)


if __name__ == "__main__":
    build_redirects()
