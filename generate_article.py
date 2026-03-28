#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
ARTICLES_DIR = ROOT / "articles"
TOPICS_FILE = DATA_DIR / "topics.json"
AFFILIATE_FILE = DATA_DIR / "affiliate_links.json"
SITEMAP_FILE = ROOT / "sitemap.xml"
PUBLISHED_FILE = ROOT / ".published.json"

SITE_URL = "https://wealthpulseblog.com"
SITE_NAME = "WealthPulse"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest"
INTENT_OVERRIDE = (os.getenv("INTENT_OVERRIDE") or "").strip().lower()

ADS_PROMPT = """You are a professional writer for {site_name}, a UK blog.

Write a complete informational article.

Topic: {topic}
Niche: {niche}
Format: {fmt}
Target length: about 800 words
Audience: UK adults

Rules:
- Use plain British English.
- Be helpful, specific, and practical.
- No fake statistics, no fake citations, no made-up studies.
- Do not include any external links.
- Use [AD_SLOT] exactly once in the body.
- Only use these HTML tags in BODY: h2, h3, p, ul, ol, li, strong, em, blockquote.

Return EXACTLY these sections and nothing else:
===TITLE===
===SLUG===
===META===
===KEYWORDS===
===LEDE===
===BODY===
===TAGS===
"""

AFFILIATE_PROMPT = """You are a professional affiliate content writer for {site_name}, a UK blog.

Write a commercial-intent article.

Topic: {topic}
Niche: {niche}
Format: {fmt}
Target length: about 950 words
Audience: UK adults comparing products

Approved products:
{products_block}

Rules:
- Use only the approved products above.
- Never invent brands, product names, prices, ratings, or URLs.
- Do not include any external links.
- Use [AD_SLOT] exactly once in the body.
- Where a product recommendation should appear, end that section with [PRODUCT_CARD:go_slug].
- Use only these HTML tags in BODY: h2, h3, p, ul, ol, li, strong, em, blockquote.
- Be balanced and specific.

Return EXACTLY these sections and nothing else:
===TITLE===
===SLUG===
===META===
===KEYWORDS===
===LEDE===
===BODY===
===TAGS===
"""

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>{title} — {site_name}</title>
<meta name=\"description\" content=\"{meta_description}\">
<meta name=\"keywords\" content=\"{keywords}\">
<meta name=\"robots\" content=\"index,follow\">
<meta property=\"og:title\" content=\"{title} — {site_name}\">
<meta property=\"og:description\" content=\"{meta_description}\">
<meta property=\"og:type\" content=\"article\">
<meta property=\"og:url\" content=\"{canonical}\">
<link rel=\"canonical\" href=\"{canonical}\">
<link rel=\"stylesheet\" href=\"../assets/style.css\">
<link rel=\"stylesheet\" href=\"../assets/product-cards.css\">
<script type=\"application/ld+json\">{schema}</script>
</head>
<body>
<header class=\"masthead\">
  <div class=\"masthead-top\"><span class=\"date-line\">{pub_date}</span></div>
  <div class=\"masthead-logo\">
    <a class=\"logo-name\" href=\"../index.html\">{site_name}</a>
    <p class=\"logo-tagline\">Practical advice on money · health · career · life</p>
  </div>
  <nav class=\"nav-bar\">
    <a href=\"../index.html\">Home</a>
    <a href=\"personal-finance.html\">Finance</a>
    <a href=\"health-fitness.html\">Health</a>
    <a href=\"productivity.html\">Productivity</a>
    <a href=\"career-growth.html\">Career</a>
    <a href=\"home-living.html\">Home</a>
  </nav>
</header>
<main class=\"article-container\">
  <article class=\"feature-article\">
    <div class=\"article-header\">
      <div class=\"article-niche\">{niche}</div>
      <h1 class=\"article-title\">{title}</h1>
      <div class=\"article-meta\">{pub_date} · {read_time} min read · {word_count} words</div>
      <p class=\"article-lede\"><em>{lede}</em></p>
    </div>
    <div class=\"article-content\">
      {body_html}
    </div>
    <div class=\"article-tags\">{tags_html}</div>
  </article>
</main>
<footer class=\"footer\"><p>© {year} {site_name}. All rights reserved.</p></footer>
</body>
</html>
"""


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_published() -> dict[str, list[str]]:
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text(encoding="utf-8"))
    return {"slugs": [], "topic_ids": []}


def save_published(data: dict[str, list[str]]) -> None:
    PUBLISHED_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_section(raw: str, key: str) -> str:
    pattern = rf"===\s*{re.escape(key)}\s*===\s*([\s\S]*?)(?=\n===|\Z)"
    m = re.search(pattern, raw, flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def make_slug(value: str) -> str:
    slug = value.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80] or "article"


def is_real_url(url: str) -> bool:
    return bool(url) and url.startswith(("http://", "https://")) and not url.startswith("REPLACE_")


def get_usable_products(affiliate_db: dict, category: str) -> list[dict]:
    products = affiliate_db.get(category, [])
    usable = []
    for p in products:
        if p.get("active") is not True:
            continue
        if not p.get("go_slug"):
            continue
        if not is_real_url(p.get("url", "")):
            continue
        usable.append(p)
    return usable


def format_products_for_prompt(products: list[dict]) -> str:
    chunks = []
    for p in products:
        chunks.append(
            f"PRODUCT: {p['name']}\n"
            f"GO_SLUG: {p['go_slug']}\n"
            f"DESCRIPTION: {p.get('description','')}\n"
            f"PRICE_NOTE: {p.get('price_note','')}\n"
            f"RATING: {p.get('rating','')}\n"
            f"BEST_FOR: {p.get('best_for','')}\n"
            f"PROS: {', '.join(p.get('pros', []))}\n"
            f"CONS: {', '.join(p.get('cons', []))}\n"
        )
    return "\n".join(chunks)


def call_ai(prompt: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def build_product_card_html(p: dict) -> str:
    stars = int(round(float(p.get("rating", 4))))
    star_html = "★" * stars + "☆" * (5 - stars)
    pros = "".join(f"<li>{pro}</li>" for pro in p.get("pros", []))
    cons = "".join(f"<li>{con}</li>" for con in p.get("cons", []))
    return f"""
<div class=\"product-card\">
  <div class=\"product-card-header\">
    <h3 class=\"product-name\">{p['name']}</h3>
    <div class=\"product-rating\">{star_html} <span>{p.get('rating', '')}/5</span></div>
  </div>
  <p class=\"product-desc\">{p.get('description','')}</p>
  <div class=\"product-meta\">
    <span class=\"product-chip\">{p.get('programme','Affiliate Programme')}</span>
    <span class=\"product-chip\">{p.get('price_note','See site for pricing')}</span>
    <span class=\"product-chip\">Best for: {p.get('best_for','General use')}</span>
  </div>
  <div class=\"product-columns\">
    <div>
      <h4>Pros</h4>
      <ul>{pros}</ul>
    </div>
    <div>
      <h4>Cons</h4>
      <ul>{cons}</ul>
    </div>
  </div>
  <a class=\"product-cta\" rel=\"sponsored nofollow\" href=\"{SITE_URL}/go/{p['go_slug']}/\">Check latest details</a>
</div>
"""


def validate_output(data: dict) -> tuple[bool, str]:
    if len(data.get("title", "")) < 8:
        return False, "title missing or too short"
    if len(data.get("meta_description", "")) < 40:
        return False, "meta description missing or too short"
    if len(data.get("body_html", "")) < 350:
        return False, "body too short"
    if data.get("intent") == "affiliate" and not data.get("products"):
        return False, "affiliate article has no usable products"
    if re.search(r'href="https?://', data.get("body_html", "")):
        data["body_html"] = re.sub(r'href="https?://[^"]*"', 'href="#"', data["body_html"])
    return True, ""


def render_article_page(data: dict) -> str:
    now = datetime.now(timezone.utc)
    canonical = f"{SITE_URL}/articles/{data['slug']}.html"
    body_html = data["body_html"].replace(
        "[AD_SLOT]",
        """<div class=\"in-article-ad\"><div class=\"ad-placeholder ad-half\">Advertisement</div></div>""",
    )
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": data["title"],
        "description": data["meta_description"],
        "url": canonical,
        "datePublished": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL},
    })
    tags_html = " ".join(f'<a class="tag" href="#">{t}</a>' for t in data.get("tags", [])[:6])
    return ARTICLE_TEMPLATE.format(
        title=data["title"],
        site_name=SITE_NAME,
        meta_description=data["meta_description"],
        keywords=", ".join(data.get("keywords", [])),
        canonical=canonical,
        schema=schema,
        pub_date=now.strftime("%d %B %Y"),
        niche=data.get("niche", "Article"),
        read_time=max(1, data.get("word_count", 0) // 200),
        word_count=data.get("word_count", 0),
        lede=data.get("lede", ""),
        body_html=body_html,
        tags_html=tags_html,
        year=now.year,
    )


def update_sitemap(url: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"  <url>\n"
        f"    <loc>{url}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>monthly</changefreq>\n"
        f"    <priority>0.8</priority>\n"
        f"  </url>\n"
    )
    if SITEMAP_FILE.exists():
        text = SITEMAP_FILE.read_text(encoding="utf-8")
        if url in text:
            print("URL already present in sitemap.")
            return
        if "</urlset>" in text:
            text = text.replace("</urlset>", entry + "</urlset>")
        else:
            text += "\n" + entry
    else:
        text = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
            f'{entry}</urlset>'
        )
    tmp = SITEMAP_FILE.with_suffix(".xml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(SITEMAP_FILE)


def ensure_unique_slug(slug: str, published_slugs: list[str]) -> str:
    base = make_slug(slug)
    candidate = base
    n = 2
    while candidate in published_slugs or (ARTICLES_DIR / f"{candidate}.html").exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def parse_common(raw: str, fallback_topic: str) -> dict:
    body = extract_section(raw, "BODY")
    words = len(re.sub(r"<[^>]+>", " ", body).split())
    return {
        "title": extract_section(raw, "TITLE") or fallback_topic.title(),
        "slug": make_slug(extract_section(raw, "SLUG") or fallback_topic),
        "meta_description": extract_section(raw, "META") or f"Read our guide on {fallback_topic}.",
        "keywords": [k.strip() for k in extract_section(raw, "KEYWORDS").split(",") if k.strip()],
        "lede": extract_section(raw, "LEDE") or "",
        "body_html": body,
        "tags": [t.strip() for t in extract_section(raw, "TAGS").split(",") if t.strip()],
        "word_count": words,
    }


def generate_ads_article(topic: dict) -> dict:
    raw = call_ai(ADS_PROMPT.format(site_name=SITE_NAME, topic=topic["topic"], niche=topic["niche"], fmt=topic.get("format", "guide")))
    data = parse_common(raw, topic["topic"])
    data.update({"intent": "ads", "products": [], "niche": topic["niche"]})
    return data


def generate_affiliate_article(topic: dict, affiliate_db: dict) -> dict | None:
    category = topic.get("product_category", "")
    products = get_usable_products(affiliate_db, category)
    if not products:
        return None
    raw = call_ai(AFFILIATE_PROMPT.format(
        site_name=SITE_NAME,
        topic=topic["topic"],
        niche=topic["niche"],
        fmt=topic.get("format", "best-of"),
        products_block=format_products_for_prompt(products),
    ))
    data = parse_common(raw, topic["topic"])
    product_map = {p["go_slug"]: p for p in products}

    def repl(match: re.Match) -> str:
        slug = match.group(1).strip()
        product = product_map.get(slug)
        return build_product_card_html(product) if product else ""

    data["body_html"] = re.sub(r"\[PRODUCT_CARD:([^\]]+)\]", repl, data["body_html"])
    data.update({"intent": "affiliate", "products": products, "niche": topic["niche"]})
    return data


def pick_topics(topics: list[dict], published: dict) -> list[dict]:
    available = [t for t in topics if t["id"] not in published.get("topic_ids", [])]
    if INTENT_OVERRIDE in {"ads", "affiliate"}:
        available = [t for t in available if t.get("intent") == INTENT_OVERRIDE]
    available.sort(key=lambda t: t.get("priority", 999))
    return available


def main() -> None:
    topics = load_json(TOPICS_FILE)
    affiliate_db = load_json(AFFILIATE_FILE)
    published = load_published()
    ARTICLES_DIR.mkdir(exist_ok=True)

    candidates = pick_topics(topics, published)
    if not candidates:
        print("No available topics to publish.")
        sys.exit(0)

    for topic in candidates:
        print(f"Trying topic: {topic['topic']} [{topic.get('intent')}]")
        if topic.get("intent") == "affiliate":
            data = generate_affiliate_article(topic, affiliate_db)
            if data is None:
                print("Skipping: no usable affiliate products configured for this topic.")
                continue
        else:
            data = generate_ads_article(topic)

        ok, reason = validate_output(data)
        if not ok:
            raise RuntimeError(f"Validation failed: {reason}")

        data["slug"] = ensure_unique_slug(data["slug"], published.get("slugs", []))
        html = render_article_page(data)
        out_path = ARTICLES_DIR / f"{data['slug']}.html"
        out_path.write_text(html, encoding="utf-8")

        article_url = f"{SITE_URL}/articles/{data['slug']}.html"
        update_sitemap(article_url)

        published.setdefault("slugs", []).append(data["slug"])
        published.setdefault("topic_ids", []).append(topic["id"])
        save_published(published)

        print(f"Published: {article_url}")
        return

    print("No publishable topics were found in this run.")


if __name__ == "__main__":
    main()
