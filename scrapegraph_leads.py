#!/usr/bin/env python3
"""Find public DFW listing candidates through ScrapeGraphAI Search v2.

Outputs research-only candidates to a separate CSV. Does not update MBM's canonical
lead database, collect private homeowner contact details, send messages, or infer
seller motivation from a listing alone.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

DEFAULT_QUERIES = [
    'Dallas Fort Worth TX single family home for sale "price reduced" fixer as-is',
    'DFW Texas single family listing "days on market" fixer upper estate sale',
    'Dallas Tarrant County TX older home for sale needs work investor special price drop',
]

PROMPT = """From the search results, extract ONLY residential property listings actually supported by the fetched source pages. Return a `listings` array. For each listing include: source_url (the exact listing-page URL from the source), address, city, state, zip, asking_price (number if available), days_on_market (number if explicitly available), beds, baths, sqft, property_type, description (brief factual listing text), price_reduced (true only if page explicitly states a reduction), listing_agent (only if displayed on the page), and brokerage (only if displayed on the page). Do not invent missing fields: use empty strings or null. Do not state an owner is motivated, distressed, vacant, pre-foreclosure, or likely to sell unless the source explicitly says so. Do not extract homeowner personal phone numbers, private emails, or other private contact data. Prefer public listing pages and broker/agent pages. Do not bypass access controls, login walls, or anti-bot restrictions. Every source_url must correspond to an actual source page in this search response."""

SCHEMA = {
    "type": "object",
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_url": {"type": "string"},
                    "address": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "zip": {"type": "string"},
                    "asking_price": {"type": ["number", "string", "null"]},
                    "days_on_market": {"type": ["number", "string", "null"]},
                    "beds": {"type": ["number", "string", "null"]},
                    "baths": {"type": ["number", "string", "null"]},
                    "sqft": {"type": ["number", "string", "null"]},
                    "property_type": {"type": "string"},
                    "description": {"type": "string"},
                    "price_reduced": {"type": ["boolean", "string", "null"]},
                    "listing_agent": {"type": "string"},
                    "brokerage": {"type": "string"},
                },
            },
        }
    },
}

CSV_FIELDS = [
    "first_seen_at_utc", "source_query", "source_url", "source_is_cited",
    "address", "city", "state", "zip", "asking_price", "days_on_market",
    "beds", "baths", "sqft", "property_type", "description", "price_reduced",
    "listing_agent", "brokerage", "observed_signals", "signal_score",
    "verification_status", "seller_intent", "contact_status", "next_action",
]

SIGNAL_TERMS = (
    "as-is", "as is", "fixer", "needs work", "investor special", "handyman",
    "cash only", "estate sale", "price reduced", "reduced", "bring offers",
    "priced to sell", "needs tlc", "repair", "distressed",
)
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}


def get_value(obj: Any, *names: str, default: Any = None) -> Any:
    """Read a field from an SDK response object or mapping without assuming SDK internals."""
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    path = parts.path.rstrip("/") or "/"
    query_parts = [p for p in parts.query.split("&") if p]
    kept = []
    for part in query_parts:
        key = part.split("=", 1)[0].lower()
        if key not in TRACKING_KEYS:
            kept.append(part)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "&".join(kept), ""))


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def extract_records(payload: Any) -> list[dict[str, Any]]:
    """Extract listing arrays from common JSON payload shapes; no free-text guessing."""
    payload = _as_json(payload)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("listings", "properties", "candidates", "results"):
        if key in payload:
            found = extract_records(payload[key])
            if found:
                return found
    nested = payload.get("data")
    if isinstance(nested, (dict, list, str)):
        return extract_records(nested)
    return []


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _money(value: Any) -> str:
    if value is None or value == "":
        return ""
    raw = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        number = float(raw)
        if number <= 0:
            return ""
        return str(int(number)) if number.is_integer() else str(number)
    except (ValueError, OverflowError):
        return ""


def _number(value: Any) -> str:
    if value is None or value == "":
        return ""
    raw = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        number = float(raw)
        if number < 0:
            return ""
        return str(int(number)) if number.is_integer() else str(number)
    except (ValueError, OverflowError):
        return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "y", "1", "reduced"}


def _address_key(address: str, city: str = "", state: str = "") -> str:
    value = f"{address} {city} {state}".lower()
    # Normalize common US street-type variants before punctuation removal.
    replacements = {
        r"\bstreet\b": "st", r"\broad\b": "rd", r"\bdrive\b": "dr",
        r"\bavenue\b": "ave", r"\bboulevard\b": "blvd", r"\blane\b": "ln",
        r"\bcourt\b": "ct", r"\bplace\b": "pl", r"\bhighway\b": "hwy",
        r"\bterrace\b": "ter", r"\bcircle\b": "cir",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)
    return re.sub(r"[^a-z0-9]", "", value)


def normalize_listing(raw: dict[str, Any], cited_urls: set[str], first_seen_at: str, source_query: str = "") -> dict[str, Any]:
    """Normalize one extracted record and gate it on real citation + essential fields."""
    source_url = _text(get_value(raw, "source_url", "listing_url", "url", "source"))
    clean_url = normalize_url(source_url)
    cited = bool(clean_url and clean_url in cited_urls)
    address = _text(get_value(raw, "address", "property_address", "street_address"))
    city = _text(get_value(raw, "city", "municipality"))
    state = _text(get_value(raw, "state", "state_code")).upper()
    zip_code = _text(get_value(raw, "zip", "zipcode", "postal_code"))
    price = _money(get_value(raw, "asking_price", "list_price", "price"))
    dom = _number(get_value(raw, "days_on_market", "dom", "days_on_site"))
    beds = _number(get_value(raw, "beds", "bedrooms"))
    baths = _number(get_value(raw, "baths", "bathrooms"))
    sqft = _number(get_value(raw, "sqft", "square_feet", "living_area"))
    ptype = _text(get_value(raw, "property_type", "type"))
    description = _text(get_value(raw, "description", "remarks", "summary"))
    reduced = _truthy(get_value(raw, "price_reduced", "has_price_reduction", default=False))
    agent = _text(get_value(raw, "listing_agent", "agent_name"))
    brokerage = _text(get_value(raw, "brokerage", "listing_brokerage"))

    text_blob = f"{description} {ptype}".lower()
    hits = [term for term in SIGNAL_TERMS if term in text_blob]
    signals = list(dict.fromkeys(hits + (["explicit_price_reduction"] if reduced else [])))
    try:
        dom_num = float(dom) if dom else None
    except ValueError:
        dom_num = None

    # Deterministic research-priority score, not a probability of seller intent.
    score = 0
    if dom_num is not None:
        score += 25 if dom_num >= 90 else 18 if dom_num >= 60 else 10 if dom_num >= 45 else 0
    score += min(24, 8 * len(hits))
    if reduced:
        score += 20
    if price:
        score += 10
    if address and city and state:
        score += 10
    if cited:
        score += 11
    score = min(100, score)

    required_present = bool(clean_url and address and city and state and price)
    if cited and required_present:
        verification = "SOURCE_CITED_REVIEW_REQUIRED"
    else:
        verification = "QUARANTINE_UNCITED_OR_INCOMPLETE"

    return {
        "first_seen_at_utc": first_seen_at,
        "source_query": source_query,
        "source_url": source_url,
        "source_is_cited": str(cited).lower(),
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "asking_price": price,
        "days_on_market": dom,
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
        "property_type": ptype,
        "description": description,
        "price_reduced": str(reduced).lower(),
        "listing_agent": agent,
        "brokerage": brokerage,
        "observed_signals": ";".join(signals),
        "signal_score": score,
        "verification_status": verification,
        "seller_intent": "NOT_INFERRED",
        "contact_status": "NOT_COLLECTED",
        "next_action": "Manually verify listing is active, confirm comp sales/repairs, and qualify seller/agent before any outreach.",
    }


def dedupe_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by normalized property address, retaining the strongest observed record."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _address_key(_text(row.get("address")), _text(row.get("city")), _text(row.get("state")))
        url_key = normalize_url(row.get("source_url"))
        key = key or url_key
        if not key:
            # Don't collapse records with no address/source evidence into one another.
            key = f"__missing_{len(best)}"
        current = best.get(key)
        rank = (int(row.get("signal_score") or 0), str(row.get("source_is_cited", "false")) == "true")
        current_rank = (int(current.get("signal_score") or 0), str(current.get("source_is_cited", "false")) == "true") if current else None
        if current is None or rank > current_rank:
            best[key] = row
    return sorted(best.values(), key=lambda r: (-int(r.get("signal_score") or 0), r.get("city", ""), r.get("address", "")))


def _get_ref_urls(data: Any) -> set[str]:
    refs = get_value(data, "reference_urls", "referenceUrls", "citations", default=[]) or []
    if isinstance(refs, str):
        refs = [refs]
    urls: set[str] = set()
    for item in refs:
        raw = get_value(item, "url", "source_url", default=item)
        norm = normalize_url(raw)
        if norm:
            urls.add(norm)
    # Search results are also source evidence according to the current SDK interface.
    results = get_value(data, "results", default=[]) or []
    for item in results:
        norm = normalize_url(get_value(item, "url", "source_url", default=""))
        if norm:
            urls.add(norm)
    return urls


def run_searches(queries: list[str], num_results: int, api_key: str | None = None) -> list[dict[str, Any]]:
    """Call official ScrapeGraphAI Search v2 and return quarantined research candidates."""
    key = (api_key or os.getenv("SGAI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("Missing SGAI_API_KEY. Set it in the environment; never commit or paste the key into GitHub.")
    try:
        from scrapegraph_py import ScrapeGraphAI
    except ImportError as exc:
        raise RuntimeError("Missing SDK. Install with: python -m pip install scrapegraph-py") from exc

    client = ScrapeGraphAI(api_key=key)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    candidates: list[dict[str, Any]] = []
    for query in queries:
        response = client.search(
            query,
            num_results=num_results,
            prompt=PROMPT,
            schema=SCHEMA,
            location_geo_code="us",
        )
        status = _text(get_value(response, "status", default="error")).lower()
        if status != "success":
            err = _text(get_value(response, "error", default="ScrapeGraphAI search failed"))
            print(f"WARN: query failed ({query!r}): {err}", file=sys.stderr)
            continue
        data = get_value(response, "data", default={})
        payload = get_value(data, "json_data", "result", "results", default=data)
        records = extract_records(payload)
        cited_urls = _get_ref_urls(data)
        for raw in records:
            candidates.append(normalize_listing(raw, cited_urls, now, query))
    return dedupe_candidates(candidates)


def write_csv(rows: list[dict[str, Any]], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover DFW public listing candidates using ScrapeGraphAI Search v2.")
    parser.add_argument("--query", action="append", dest="queries", help="Search query (repeat to add queries). Defaults to three DFW listing searches.")
    parser.add_argument("--max-results", type=int, default=5, help="Results per search, 1-20. Defaults to 5 to cap spend.")
    parser.add_argument("--out", default="out/scrapegraph_candidates.csv", help="Separate research-only output CSV.")
    args = parser.parse_args(argv)
    if not 1 <= args.max_results <= 20:
        parser.error("--max-results must be between 1 and 20")
    try:
        rows = run_searches(args.queries or DEFAULT_QUERIES, args.max_results)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_csv(rows, args.out)
    cited = sum(1 for row in rows if row["source_is_cited"] == "true" and row["verification_status"] == "SOURCE_CITED_REVIEW_REQUIRED")
    print(f"Wrote {len(rows)} deduplicated research candidates to {args.out}; {cited} have cited sources and minimum required fields.")
    print("No canonical lead DB writes, contact harvesting, outreach, or offers were performed.")
    return 0
