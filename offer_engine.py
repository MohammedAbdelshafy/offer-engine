#!/usr/bin/env python3
"""
Muse-style offer engine, wired to the founder's DFW wholesaling stack.

Pipeline (mirrors the olivia_schremmer "Muse" loop):
  listings.csv --[criteria filter]--> candidates --[dedupe]--> ranked offers
      --> agent SMS drafts (DRAFT ONLY, never sent by this tool)
      --> TREC 1-4 contract-data JSON per candidate (Texas, not FAR/BAR)

Plugs into existing repos:
  - lead-scoring-cli : score the candidates CSV it emits
  - re-deal-packet   : underwrite any candidate with comps (ARV / 70%-rule MAO)
  - MBM-Control Outreach/Phound : the gated send layer (founder approves batch first)

Stdlib only. No network. No sending.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date, timedelta

# --- Criteria: the "Tell Muse what you want" layer ---------------------------
DEFAULTS = {
    "under_list": 70000,      # offer = list_price - under_list
    "min_list_price": 130000,
    "dom_min": 45,
    "dom_max": 200,
    "close_days": 21,
    "earnest_pct": 0.01,      # earnest money as fraction of offer
}
# Ugly-house signals (listing copy), from the reference workflow
UGLY_KEYWORDS = ["tlc", "as-is", "as is", "fixer", "handyman", "needs work",
                 "cash only", "teardown", "distressed", "investor special",
                 "bring offers", "priced to sell"]
# Turnkey signals -> excluded ("Nothing turnkey, nothing flipped")
TURNKEY_KEYWORDS = ["turnkey", "renovated", "remodeled", "new construction",
                    "flipped", "move-in ready", "fully updated"]


def norm_addr(s):
    s = (s or "").lower()
    s = re.sub(r"\b(apt|unit|ste|suite)\s*\S*", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def norm_phone(s):
    return re.sub(r"\D", "", s or "")


def money(n):
    return "${:,}".format(int(round(n)))


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_contact_log(path):
    """Returns (set of normalized addresses, set of normalized phones)."""
    addrs, phones = set(), set()
    if not path or not os.path.exists(path):
        return addrs, phones
    for row in load_csv(path):
        a = row.get("address") or row.get("property_address")
        if a:
            addrs.add(norm_addr(a))
        p = row.get("agent_phone") or row.get("phone")
        if p:
            phones.add(norm_phone(p))
    return addrs, phones


def hit_count(text, keywords):
    t = (text or "").lower()
    return sum(1 for k in keywords if k in t)


def filter_listings(rows, cfg):
    """Apply the 'Tell Muse what you want' criteria. Returns (kept, rejected)."""
    kept, rejected = [], []
    for r in rows:
        reasons = []
        try:
            price = float(str(r.get("list_price", "")).replace(",", "").replace("$", ""))
            dom = int(float(str(r.get("dom", "0"))))
        except (ValueError, TypeError):
            rejected.append((r, "bad price/DOM"))
            continue
        desc = r.get("description", "")
        if price < cfg["min_list_price"]:
            reasons.append("below min price")
        if not (cfg["dom_min"] <= dom <= cfg["dom_max"]):
            reasons.append("DOM out of range")
        if hit_count(desc, TURNKEY_KEYWORDS):
            reasons.append("turnkey/flipped")
        if hit_count(desc, UGLY_KEYWORDS) == 0:
            reasons.append("no ugly-house keywords")
        if reasons:
            rejected.append((r, "; ".join(reasons)))
            continue
        offer = price - cfg["under_list"]
        kept.append({
            "row": r, "list_price": price, "dom": dom,
            "offer": offer,
            "discount_pct": round(100.0 * cfg["under_list"] / price, 1),
            "ugly_hits": hit_count(desc, UGLY_KEYWORDS),
        })
    # Rank: deepest discount % first, then longest DOM, then most ugly signals
    kept.sort(key=lambda c: (-c["discount_pct"], -c["dom"], -c["ugly_hits"]))
    return kept, rejected


def sms_draft(c, buyer_name, cfg):
    r = c["row"]
    addr = "{}, {}, {} {}".format(
        r.get("address", ""), r.get("city", ""), r.get("state", ""), r.get("zip", ""))
    return (
        "Hey {agent}! I came across your listing on {addr}. I reviewed the "
        "numbers and spoke to my lender; I'd be at {offer} cash with a "
        "{days}-day close. If your client is interested, let me know and I "
        "can get the contract sent over. - {buyer} "
        "(Reply STOP to opt out)"
    ).format(agent=r.get("listing_agent", "there"), addr=addr,
             offer=money(c["offer"]), days=cfg["close_days"], buyer=buyer_name)


def contract_data(c, buyer_name, cfg):
    """TREC 1-4-shaped contract data (Texas). Fill into the real TREC form / e-sign."""
    r = c["row"]
    offer = round(c["offer"])
    close = date.today() + timedelta(days=cfg["close_days"])
    return {
        "form": "TREC 1-4 Residential Contract (Texas) - DATA ONLY, fill into official form",
        "buyer": buyer_name,
        "seller": r.get("seller_name", "per listing / to be confirmed"),
        "property": {
            "address": r.get("address", ""),
            "city": r.get("city", ""), "state": r.get("state", ""),
            "zip": r.get("zip", ""), "county": r.get("county", "Tarrant or Dallas - verify"),
        },
        "sales_price": offer,
        "earnest_money": round(offer * cfg["earnest_pct"]),
        "financing": "cash",
        "closing_date": close.isoformat(),
        "listing_agent": r.get("listing_agent", ""),
        "agent_phone": r.get("agent_phone", ""),
        "brokerage": r.get("brokerage", ""),
        "list_price": round(c["list_price"]),
        "discount_under_list": cfg["under_list"],
        "notes": "as-is; verify title/escrow agent before execution",
    }

def main():
    ap = argparse.ArgumentParser(
        description="Muse-style offer engine: listings -> ranked offers -> SMS drafts -> TREC contract data")
    ap.add_argument("listings", help="listings CSV")
    ap.add_argument("--contact-log", default=None, help="already-contacted CSV (dedupe)")
    ap.add_argument("--buyer-name", default="BUYER LLC",
                    help="buyer entity shown on drafts/contract data")
    ap.add_argument("--under", type=float, default=DEFAULTS["under_list"])
    ap.add_argument("--min-price", type=float, default=DEFAULTS["min_list_price"])
    ap.add_argument("--dom-min", type=int, default=DEFAULTS["dom_min"])
    ap.add_argument("--dom-max", type=int, default=DEFAULTS["dom_max"])
    ap.add_argument("--close-days", type=int, default=DEFAULTS["close_days"])
    ap.add_argument("--out", default="out", help="output directory")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    cfg.update({"under_list": args.under, "min_list_price": args.min_price,
                "dom_min": args.dom_min, "dom_max": args.dom_max,
                "close_days": args.close_days})

    rows = load_csv(args.listings)
    kept, rejected = filter_listings(rows, cfg)
    log_addrs, log_phones = load_contact_log(args.contact_log)

    deduped, skipped = [], []
    for c in kept:
        r = c["row"]
        if norm_addr(r.get("address")) in log_addrs or \
           norm_phone(r.get("agent_phone")) in log_phones:
            skipped.append(c)
        else:
            deduped.append(c)

    os.makedirs(args.out, exist_ok=True)

    # 1) candidates.csv -- feed this to lead-scoring-cli
    cand_path = os.path.join(args.out, "candidates.csv")
    with open(cand_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "address", "city", "state", "zip", "list_price",
                    "offer", "discount_pct", "dom", "beds", "baths", "sqft",
                    "year_built", "listing_agent", "agent_phone", "brokerage", "signals"])
        for i, c in enumerate(deduped, 1):
            r = c["row"]
            w.writerow([i, r.get("address"), r.get("city"), r.get("state"), r.get("zip"),
                        round(c["list_price"]), round(c["offer"]), c["discount_pct"],
                        c["dom"], r.get("beds"), r.get("baths"), r.get("sqft"),
                        r.get("year_built"), r.get("listing_agent"),
                        r.get("agent_phone"), r.get("brokerage"),
                        r.get("description", "")[:80]])

    # 2) sms_drafts.md -- DRAFTS ONLY. Founder approves message + batch before any send.
    sms_path = os.path.join(args.out, "sms_drafts.md")
    with open(sms_path, "w", encoding="utf-8") as f:
        f.write("# Agent SMS drafts - NOT SENT - founder approval required\n\n")
        f.write("Outreach gate: the founder must approve BOTH the message and the "
                "recipient batch before anything is sent.\n\n")
        for i, c in enumerate(deduped, 1):
            r = c["row"]
            f.write("## #{i} {addr} - {agent} ({phone})\n\n".format(
                i=i, addr=r.get("address"), agent=r.get("listing_agent"),
                phone=r.get("agent_phone")))
            f.write("Offer: {offer} ({pct}% under list) - {dom} DOM\n\n".format(
                offer=money(c["offer"]), pct=c["discount_pct"], dom=c["dom"]))
            f.write("```\n" + sms_draft(c, args.buyer_name, cfg) + "\n```\n\n")

    # 3) contract_data.json -- one TREC 1-4 data packet per candidate
    con_path = os.path.join(args.out, "contract_data.json")
    with open(con_path, "w", encoding="utf-8") as f:
        json.dump([contract_data(c, args.buyer_name, cfg) for c in deduped],
                  f, indent=2)

    # stdout summary
    print("listings in: {}".format(len(rows)))
    print("rejected by criteria: {}".format(len(rejected)))
    for r, why in rejected:
        print("  x {} -> {}".format(r.get("address"), why))
    print("matched criteria: {}".format(len(kept)))
    print("deduped vs contact log: {}".format(len(skipped)))
    print("OFFER CANDIDATES: {}".format(len(deduped)))
    for i, c in enumerate(deduped, 1):
        r = c["row"]
        print("  #{i} {addr} | list {lp} -> offer {ofr} ({pct}% under) | "
              "{dom} DOM | {agent} {phone}".format(
                  i=i, addr=r.get("address"), lp=money(c["list_price"]),
                  ofr=money(c["offer"]), pct=c["discount_pct"],
                  dom=c["dom"], agent=r.get("listing_agent"),
                  phone=r.get("agent_phone")))
    print("wrote: {}, {}, {}".format(cand_path, sms_path, con_path))


if __name__ == "__main__":
    main()
