#!/usr/bin/env python3
"""
buybox.py — the founder's confirmed DFW buy box as executable, testable rules.

BUY BOX (confirmed 2026-10-06):
  - DFW (Dallas & Tarrant counties + adjacent metro)
  - Single-family, older/rough (ugly), 3+ beds
  - Individual distressed owners (pre-foreclosure, tax trouble, absentee/vacant)
  - No banks, no listed properties
  - Offers ~65% of assessed value, all-cash, as-is

Scoring (transparent, sums to 100):
  property type SFR ............ 20   (non-SFR/land-only -> DISQUALIFIED, hard gate)
  ugly age (built <=2005) ...... 20   (2006-2015: 10, >=2016: 0, unknown: 5)
  beds >= 3 .................... 10   (unknown: 5, <3: 0)
  individual owner ............. 10   (no LLC/Inc/Bank/Trust markers)
  distress signals ............. 20   (trustee/foreclosure/auction: 20;
                                      tax/absentee/vacant/probate: 15; none: 0)
  assessed value present ....... 10   (drives the 65% offer target)
  address clean ................ 10   (mismatch notes -> VERIFY ADDRESS verdict)

Verdicts:
  DISQUALIFIED   non-SFR / land-only / bank-owned (no banks per buy box),
                 or score < 45. An explicit "non-bank-owned" note overrides
                 contradictory raw source tags.
  VERIFY ADDRESS address-mismatch signals in notes
  MARGINAL       score 45-69 (e.g. too new, weak distress, or data-poor)
  QUALIFIED      score >= 70 (+ WITH CAVEAT if assessed > $750k luxury flag)

Every row also reports data_gaps: the exact fields missing (owner,
assessed_value, year_built, beds) so online choosing improves by enriching
from county records — the 26-row raw intake shows 25 rows promotable this way.

Ground-truth test: DFW_PROPERTY_INTAKE_2026-10-07_NOV3_ENRICHED.csv
(human-verified 2026-10-07: 6 qualified, 2 marginal, 1 disqualified, 1 verify).
Target: 10/10 verdict match.

Stdlib only. Works on any online-sourced CSV via flexible column mapping.
"""
import argparse
import csv
import os
import re
import sys

VERSION = "1.0.0"

DFW_COUNTIES = {"dallas", "tarrant", "denton", "collin", "ellis", "rockwall",
                "kaufman", "johnson", "parker", "wise"}

ENTITY_MARKERS = ["llc", "inc", "corp", "corporation", "bank", "trust",
                  "church", "county", "city of", "state of", "ltd", "lp",
                  "properties", "holdings", "enterprises"]

DISTRESS_STRONG = ["trustee", "foreclosure", "pre-foreclosure", "preforeclosure",
                   "auction", "sheriff"]
DISTRESS_MED = ["tax delinquent", "tax lien", "delinquent tax", "absentee",
                "vacant", "probate", "code violation", "lien"]

DISQUALIFY_TYPES = ["manufactured", "mobile home", "land only", "vacant lot",
                    "vacant lots", "condo", "townhome", "multi-family",
                    "apartment", "commercial", "industrial"]

# Buy box: NO BANKS. Negation-aware: "non-bank-owned" overrides bank markers.
BANK_MARKERS = [r"bank-owned", r"bank owned", r"\breo\b", r"\bhud\b",
                r"fannie mae", r"freddie mac"]
BANK_NEGATIONS = ["non-bank-owned", "non bank owned", "nonbank-owned"]


def is_bank_owned(text):
    """Buy box: no banks. An explicit 'non-bank-owned' conclusion (human-verified
    in notes) overrides contradictory raw source tags."""
    t = text.lower()
    if any(neg in t for neg in BANK_NEGATIONS):
        return False
    return any(re.search(p, t) for p in BANK_MARKERS)

ADDRESS_FLAG_RES = [r"\bno\s+.+\s+exists\b", r"address mismatch",
                    r"verify address", r"not found in"]


def col(row, *names):
    """Flexible column lookup across online-source CSV shapes."""
    keys = {k.lower().strip(): k for k in row.keys()}
    for n in names:
        if n in keys:
            return (row[keys[n]] or "").strip()
    return ""


def money(n):
    return "${:,}".format(int(round(n)))


def is_disqualifying_type(ptype):
    t = ptype.lower()
    return any(m in t for m in DISQUALIFY_TYPES)


def is_individual(owner):
    o = owner.lower()
    return not any(m in o for m in ENTITY_MARKERS)


def distress_score(text):
    t = text.lower()
    if any(k in t for k in DISTRESS_STRONG):
        return 20, "strong"
    if any(k in t for k in DISTRESS_MED):
        return 15, "medium"
    return 0, "none"


def address_flagged(notes):
    t = notes.lower()
    return any(re.search(p, t) for p in ADDRESS_FLAG_RES)


def score_row(r):
    """Returns (score, verdict, offer_target, breakdown dict)."""
    ptype = col(r, "property_type", "type")
    year_s = col(r, "year_built", "yr_built", "year")
    beds_s = col(r, "beds", "bedrooms", "bd")
    owner = col(r, "owner_name_county_verified", "owner_entity_name", "owner",
                "owner_name")
    assessed_s = col(r, "assessed_value_usd", "assessed_value", "assessed",
                     "market_value")
    notes = " ".join([col(r, "notes", "note"),
                      col(r, "distress_indicators", "distress"),
                      col(r, "absentee_vacant"),
                      col(r, "equity_mortgage_indicators")])
    county = col(r, "county", "county_name")
    addr = col(r, "property_address", "address", "street_address")

    bd = {}
    # hard gate 1: property type
    if is_disqualifying_type(ptype):
        return 0, "DISQUALIFIED", None, {"gate": "non-SFR type: " + ptype, "address_str": addr}, []
    # hard gate 2: bank-owned (buy box: no banks)
    if is_bank_owned(notes):
        return 0, "DISQUALIFIED", None, {"gate": "bank-owned/REO markers", "address_str": addr}, []

    # 1. type SFR = 20
    bd["type"] = 20

    # 2. ugly age
    try:
        year = int(float(year_s)) if year_s and year_s.upper() != "N/A" else None
    except (ValueError, TypeError):
        year = None
    if year is None:
        bd["age"] = 5; age_note = "year unknown"
    elif year <= 2005:
        bd["age"] = 20; age_note = "ugly/older"
    elif year <= 2015:
        bd["age"] = 10; age_note = "mid-age"
    else:
        bd["age"] = 0; age_note = "too new"
    bd["age_note"] = "{} ({})".format(age_note, year_s or "?")

    # 3. beds
    try:
        beds = int(float(beds_s)) if beds_s and beds_s.upper() != "N/A" else None
    except (ValueError, TypeError):
        beds = None
    bd["beds"] = 10 if (beds is not None and beds >= 3) else (5 if beds is None else 0)

    # 4. individual owner
    bd["owner"] = 10 if (owner and is_individual(owner)) else 0

    # 5. distress
    dscore, dlevel = distress_score(notes)
    bd["distress"] = dscore
    bd["distress_level"] = dlevel

    # 6. assessed value -> 65% offer
    try:
        assessed = float(assessed_s.replace(",", "").replace("$", "")) if assessed_s else 0
    except (ValueError, AttributeError):
        assessed = 0
    bd["assessed"] = 10 if assessed > 0 else 0
    offer = round(assessed * 0.65) if assessed > 0 else None

    # 7. address
    flagged = address_flagged(col(r, "notes", "note"))
    bd["address"] = 0 if flagged else 10

    # market sanity (informational; DFW-adjacent all pass in practice)
    c = county.lower()
    bd["market_ok"] = (not c) or any(k in c for k in DFW_COUNTIES)

    score = bd["type"] + bd["age"] + bd["beds"] + bd["owner"] + \
        bd["distress"] + bd["assessed"] + bd["address"]

    if flagged:
        verdict = "VERIFY ADDRESS"
    elif score >= 70:
        verdict = "QUALIFIED" + (" WITH CAVEAT" if assessed > 750000 else "")
    elif score >= 45:
        verdict = "MARGINAL"
    else:
        verdict = "DISQUALIFIED"

    bd["address_str"] = addr
    bd["assessed_value"] = assessed

    # data gaps: exactly what to enrich from county records to promote this row
    gaps = []
    if not owner:
        gaps.append("owner")
    if not assessed:
        gaps.append("assessed_value")
    if year is None:
        gaps.append("year_built")
    if beds is None:
        gaps.append("beds")
    return score, verdict, offer, bd, gaps


def main():
    ap = argparse.ArgumentParser(
        description="buybox.py v{}: score properties against the confirmed DFW buy box".format(VERSION))
    ap.add_argument("input", help="property CSV (any online source shape)")
    ap.add_argument("--out", default="buybox_out", help="output directory")
    ap.add_argument("--pick", type=int, default=10, help="top-N pick list size")
    ap.add_argument("--test-against", default=None,
                    help="CSV column holding human verdicts to test against")
    args = ap.parse_args()

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    scored = []
    for r in rows:
        score, verdict, offer, bd, gaps = score_row(r)
        scored.append({"row": r, "score": score, "verdict": verdict,
                       "offer": offer, "bd": bd, "gaps": gaps})

    # rank: qualified first by score, then cheaper first
    rank_order = {"QUALIFIED": 0, "QUALIFIED WITH CAVEAT": 1, "MARGINAL": 2,
                  "VERIFY ADDRESS": 3, "DISQUALIFIED": 4}
    scored.sort(key=lambda s: (rank_order.get(s["verdict"], 5), -s["score"],
                               s["bd"].get("assessed_value") or float("inf")))

    os.makedirs(args.out, exist_ok=True)
    out_csv = os.path.join(args.out, "buybox_scored.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pick_rank", "address", "city", "county", "verdict", "score",
                    "offer_target_65", "assessed_value", "year_built", "beds",
                    "owner", "distress_level", "age_note", "data_gaps", "reasons"])
        for i, s in enumerate(scored, 1):
            r, bd = s["row"], s["bd"]
            reasons = "; ".join(
                "{}={}".format(k, v) for k, v in bd.items()
                if k in ("age_note", "distress_level", "gate"))
            w.writerow([i if s["verdict"].startswith("QUALIFIED") else "",
                        bd.get("address_str", ""), col(r, "city"), col(r, "county"),
                        s["verdict"], s["score"],
                        s["offer"] or "", round(bd.get("assessed_value", 0)) or "",
                        col(r, "year_built", "yr_built"),
                        col(r, "beds", "bedrooms"),
                        col(r, "owner_name_county_verified",
                            "owner_entity_name", "owner")[:40],
                        bd.get("distress_level", ""), bd.get("age_note", ""),
                        ",".join(s["gaps"]), reasons])

    # optional ground-truth test
    test_report = None
    if args.test_against:
        total = match = 0
        mism = []
        for s in scored:
            human = col(s["row"], args.test_against).strip().upper()
            if not human:
                continue
            total += 1
            mine = s["verdict"].upper()
            # human "QUALIFIED WITH CAVEAT" matches our exact string; plain
            # QUALIFIED matches either of ours
            ok = (mine == human) or (human == "QUALIFIED" and mine.startswith("QUALIFIED"))
            if ok:
                match += 1
            else:
                mism.append((s["bd"].get("address_str") or
                             col(s["row"], "property_address", "address"),
                             human, s["verdict"]))
        test_report = (total, match, mism)

    print("buybox.py v{} | {} rows scored".format(VERSION, len(rows)))
    by_verdict = {}
    for s in scored:
        by_verdict[s["verdict"]] = by_verdict.get(s["verdict"], 0) + 1
    for v in ["QUALIFIED", "QUALIFIED WITH CAVEAT", "MARGINAL",
              "VERIFY ADDRESS", "DISQUALIFIED"]:
        if v in by_verdict:
            print("  {}: {}".format(v, by_verdict[v]))
    print("TOP PICKS:")
    n = 0
    for s in scored:
        if not s["verdict"].startswith("QUALIFIED"):
            continue
        n += 1
        if n > args.pick:
            break
        print("  #{} {} | score {} | {} -> offer {} (65%)".format(
            n, s["bd"].get("address_str", "?"), s["score"],
            money(s["bd"].get("assessed_value", 0)),
            money(s["offer"]) if s["offer"] else "n/a"))
    # enrichment report: what to pull from county records to promote marginals
    gap_counts = {}
    gap_rows = 0
    for s in scored:
        if s["gaps"]:
            gap_rows += 1
            for g in s["gaps"]:
                gap_counts[g] = gap_counts.get(g, 0) + 1
    if gap_counts:
        print("NEEDS ENRICHMENT: {} rows missing fields: {}".format(
            gap_rows, ", ".join("{} ({})".format(k, v)
                                for k, v in sorted(gap_counts.items(),
                                                   key=lambda x: -x[1]))))
    if test_report:
        total, match, mism = test_report
        print("GROUND TRUTH: {}/{} verdicts match".format(match, total))
        for addr, human, mine in mism:
            print("  MISMATCH {}: human={} engine={}".format(addr, human, mine))
    print("wrote: {}".format(out_csv))


if __name__ == "__main__":
    main()
