#!/usr/bin/env python3
"""
offer-engine v2 — the money-maximizing wholesale offer loop.

Pipeline:
  listings.csv --[criteria filter]--> ranked offers (under-list or LAO mode)
      --[dedupe vs contact log]--> candidates
      --> sms_sequences.md   (3-text day 1/2/4, rotating A/B copy, DRAFT ONLY)
      --> followup_queue.csv (scheduled touches)
      --> contract_data.json (TREC 1-4 packet + TX compliance checklist)
      --> funnel.md          (weekly metrics template)

Upgrades from the influencer research (2026-10-19):
  1. Written offers beat texts -> every candidate ships a contract-data packet
     and the day-2 text offers to send real paper ("backup offer" positioning).
  2. LAO mode (least allowable offer) alongside fixed-discount mode.
  3. 3-text sequence (days 1/2/4), two rotating human-written variants per touch
     (carriers flag repeated identical copy).
  4. Compliance block on every SMS output: quiet hours, DNC scrub, A2P 10DLC,
     global suppression (one STOP stops everything).
  5. Texas TREC 1-4 packet carries the equitable-interest disclosure rule:
     disclosure must be DELIVERED before assignment.

Stdlib only. No network. NOTHING IS SENT by this tool — drafts only.
The founder approves BOTH the message and the recipient batch before any send.
"""
import argparse
import csv
import json
import os
import re
from datetime import date, timedelta

VERSION = "2.0.0"

DEFAULTS = {
    "offer_mode": "under",    # "under" = list - under_list | "lao" = list * (1 - discount_pct)
    "under_list": 70000,
    "discount_pct": 0.30,     # LAO mode: offer = 70% of list
    "min_list_price": 130000,
    "dom_min": 45,
    "dom_max": 200,
    "close_days": 21,
    "earnest_pct": 0.01,
    "option_days": 7,
}

UGLY_KEYWORDS = ["tlc", "as-is", "as is", "fixer", "handyman", "needs work",
                 "cash only", "teardown", "distressed", "investor special",
                 "bring offers", "priced to sell"]
TURNKEY_KEYWORDS = ["turnkey", "renovated", "remodeled", "new construction",
                    "flipped", "move-in ready", "fully updated"]

COMPLIANCE_BANNER = (
    "COMPLIANCE (read before any send): texting hours 8am-9pm recipient local time; "
    "scrub every batch against the DNC registry and your global suppression list; "
    "one STOP/opt-out stops ALL campaigns for that contact within 10 business days; "
    "register A2P 10DLC before volume texting; keep opt-out language in every text; "
    "never cold-text homeowners without prior express consent. "
    "Penalties run $500-$1,500 per text federally. When unsure, ask a telecom attorney."
)


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


def compute_offer(price, cfg):
    if cfg["offer_mode"] == "lao":
        return price * (1.0 - cfg["discount_pct"])
    return price - cfg["under_list"]


def filter_listings(rows, cfg):
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
        offer = compute_offer(price, cfg)
        kept.append({
            "row": r, "list_price": price, "dom": dom, "offer": offer,
            "discount_pct": round(100.0 * (price - offer) / price, 1),
            "ugly_hits": hit_count(desc, UGLY_KEYWORDS),
        })
    kept.sort(key=lambda c: (-c["discount_pct"], -c["dom"], -c["ugly_hits"]))
    return kept, rejected

# --- 3-text sequence, days 1/2/4, rotating A/B variants -----------------------
# Research-backed: 3 texts outperform 1/2/4/10-text campaigns; carriers flag
# repeated identical copy, so every touch ships two human-written variants.
# Pick ONE variant per touch per campaign and rotate across campaigns.

def seq_texts(c, buyer_name, cfg):
    r = c["row"]
    addr = r.get("address", "")
    full = "{}, {}, {} {}".format(addr, r.get("city", ""), r.get("state", ""),
                                  r.get("zip", ""))
    agent = r.get("listing_agent", "there")
    offer = money(c["offer"])
    days = cfg["close_days"]
    opt = "(Reply STOP to opt out)"
    return [
        ("Day 1 - opener", [
            "Hey {a}! I came across your listing on {f}. I reviewed the numbers "
            "and spoke to my lender; I'd be at {o} cash with a {d}-day close. If "
            "your client is interested, let me know and I can get the contract "
            "sent over. - {b} {x}".format(a=agent, f=full, o=offer, d=days, b=buyer_name, x=opt),
            "Hi {a}, {b} here - cash buyer looking at fixer-uppers in {city}. "
            "Your listing at {ad} caught my eye. I could do {o} cash, close in "
            "{d} days, as-is. Worth a conversation? {x}".format(
                a=agent, b=buyer_name, city=r.get("city", ""), ad=addr, o=offer, d=days, x=opt),
        ]),
        ("Day 2 - bump + written offer", [
            "Hey {a}, floating my note on {ad} back up - {o} cash, {d}-day close "
            "still stands if your seller wants a clean as-is exit. - {b} {x}".format(
                a=agent, ad=addr, o=offer, d=days, b=buyer_name, x=opt),
            "{a} - quick follow-up on {ad}. Happy to send a WRITTEN offer today "
            "at {o} cash so your seller has real paper, not just a text. "
            "Interested? - {b} {x}".format(a=agent, ad=addr, o=offer, b=buyer_name, x=opt),
        ]),
        ("Day 4 - breakup / backup position", [
            "{a}, last note on {ad} - if things fall through with your current "
            "buyer, keep my {o} cash / {d}-day close as a BACKUP. I'll move fast. "
            "- {b} {x}".format(a=agent, ad=addr, o=offer, d=days, b=buyer_name, x=opt),
            "Closing the loop on {ad}, {a}. My {o} cash offer stands as a backup "
            "if anything changes - one text and I'll send the contract over. "
            "- {b} {x}".format(ad=addr, a=agent, o=offer, b=buyer_name, x=opt),
        ]),
    ]


def contract_data(c, buyer_name, cfg):
    """TREC 1-4-shaped packet (Texas) + compliance checklist. DATA ONLY."""
    r = c["row"]
    offer = round(c["offer"])
    close = date.today() + timedelta(days=cfg["close_days"])
    return {
        "form": "TREC 1-4 Residential Contract (Texas) - DATA ONLY, fill into the official form",
        "version": "offer-engine v" + VERSION,
        "buyer": buyer_name,
        "assignment_intent": True,
        "seller": r.get("seller_name", "per listing / to be confirmed"),
        "property": {
            "address": r.get("address", ""), "city": r.get("city", ""),
            "state": r.get("state", ""), "zip": r.get("zip", ""),
            "county": r.get("county", "Tarrant or Dallas - verify"),
        },
        "sales_price": offer,
        "earnest_money": round(offer * cfg["earnest_pct"]),
        "earnest_money_holder": "title company (never the seller)",
        "option_days": cfg["option_days"],
        "option_fee": "TBD ($100-$500 typical)",
        "financing": "cash",
        "closing_date": close.isoformat(),
        "listing_agent": r.get("listing_agent", ""),
        "agent_phone": r.get("agent_phone", ""),
        "brokerage": r.get("brokerage", ""),
        "list_price": round(c["list_price"]),
        "offer_basis": ("LAO: {:.0f}% of list".format((1 - cfg["discount_pct"]) * 100)
                        if cfg["offer_mode"] == "lao"
                        else "fixed discount: {} under list".format(money(cfg["under_list"]))),
        "texas_compliance": [
            "Equitable-interest DISCLOSURE must be DELIVERED to the seller BEFORE any assignment "
            "(not just signed) - failure = unlicensed brokerage, Class A misdemeanor (Occ. Code 1101.758). "
            "Keep timestamped proof of delivery.",
            "TREC 1-4 was not designed for assignment - have a TX attorney review wholesaling "
            "provisions before any seller signs. AI adapts attorney-drafted bases; it never creates contracts.",
            "Confirm the title company handles assignments BEFORE you need one.",
        ],
        "before_send_checklist": [
            "Proof-of-funds letter ready (transactional funder or program POF)",
            "End buyer funds EMD (~1% at title); option fee terms set",
            "All owners on title identified; APN verified",
            "Every signature + initials on every page at e-sign",
        ],
        "notes": "as-is; verify escrow/title agent before execution",
    }


FUNNEL_TEMPLATE = """# Weekly funnel - {week}

Track per list type (stale MLS / pre-foreclosure / absentee / etc.). If reply rate
is low or opt-out rate is high, it is almost always the copy - rotate variants.

| stage | count | rate |
|---|---|---|
| texts sent (day 1) |  |  |
| replies |  | reply % |
| opt-outs |  | opt-out % (watch this) |
| day-2 follow-ups sent |  |  |
| day-4 backup touches sent |  |  |
| WRITTEN offers sent |  |  |
| contracts executed |  | offer-to-contract % |
| closed / assigned |  |  |
| gross assignment fees |  |  |
| est. TCPA/DNC incidents | 0 | must stay 0 |

Copy rotation log:
- week of {week}: variants used -> 
- next rotation due:
"""

def main():
    ap = argparse.ArgumentParser(
        description="offer-engine v{}: listings -> ranked cash offers -> "
                    "3-text sequences -> TREC contract packets".format(VERSION))
    ap.add_argument("listings", help="listings CSV")
    ap.add_argument("--contact-log", default=None, help="already-contacted CSV (dedupe)")
    ap.add_argument("--buyer-name", default="BUYER LLC")
    ap.add_argument("--offer-mode", choices=["under", "lao"], default=DEFAULTS["offer_mode"],
                    help="under: list - fixed discount | lao: list * (1 - discount_pct)")
    ap.add_argument("--under", type=float, default=DEFAULTS["under_list"])
    ap.add_argument("--discount-pct", type=float, default=DEFAULTS["discount_pct"],
                    help="LAO mode: fraction under list, e.g. 0.30")
    ap.add_argument("--min-price", type=float, default=DEFAULTS["min_list_price"])
    ap.add_argument("--dom-min", type=int, default=DEFAULTS["dom_min"])
    ap.add_argument("--dom-max", type=int, default=DEFAULTS["dom_max"])
    ap.add_argument("--close-days", type=int, default=DEFAULTS["close_days"])
    ap.add_argument("--out", default="out", help="output directory")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    cfg.update({"offer_mode": args.offer_mode, "under_list": args.under,
                "discount_pct": args.discount_pct, "min_list_price": args.min_price,
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
    today = date.today()

    # 1) candidates.csv -> lead-scoring-cli
    cand_path = os.path.join(args.out, "candidates.csv")
    with open(cand_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "address", "city", "state", "zip", "list_price",
                    "offer", "discount_pct", "offer_mode", "dom", "beds", "baths",
                    "sqft", "year_built", "listing_agent", "agent_phone",
                    "brokerage", "signals"])
        for i, c in enumerate(deduped, 1):
            r = c["row"]
            w.writerow([i, r.get("address"), r.get("city"), r.get("state"), r.get("zip"),
                        round(c["list_price"]), round(c["offer"]), c["discount_pct"],
                        cfg["offer_mode"], c["dom"], r.get("beds"), r.get("baths"),
                        r.get("sqft"), r.get("year_built"), r.get("listing_agent"),
                        r.get("agent_phone"), r.get("brokerage"),
                        r.get("description", "")[:80]])

    # 2) sms_sequences.md - DRAFTS ONLY, founder approves message + batch first
    sms_path = os.path.join(args.out, "sms_sequences.md")
    with open(sms_path, "w", encoding="utf-8") as f:
        f.write("# Agent SMS sequences - DRAFTS ONLY, NOTHING SENT\n\n")
        f.write("Outreach gate: the founder must approve BOTH the message and the "
                "recipient batch before anything is sent.\n\n")
        f.write("> " + COMPLIANCE_BANNER + "\n\n")
        f.write("Rotate variants across campaigns; never blast identical copy twice.\n\n")
        for i, c in enumerate(deduped, 1):
            r = c["row"]
            f.write("## #{i} {addr} - {agent} ({phone})\n\n".format(
                i=i, addr=r.get("address"), agent=r.get("listing_agent"),
                phone=r.get("agent_phone")))
            f.write("Offer: {offer} ({pct}% under list, {mode}) - {dom} DOM\n\n".format(
                offer=money(c["offer"]), pct=c["discount_pct"],
                mode=cfg["offer_mode"], dom=c["dom"]))
            for touch, variants in seq_texts(c, args.buyer_name, cfg):
                f.write("### {t}\n\n".format(t=touch))
                for v, text in enumerate(variants, 1):
                    f.write("Variant {v}:\n```\n{text}\n```\n\n".format(v=v, text=text))

    # 3) followup_queue.csv - the 24/7 follow-up discipline, as a schedule
    q_path = os.path.join(args.out, "followup_queue.csv")
    with open(q_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "address", "listing_agent", "agent_phone", "offer",
                    "day1_date", "day2_date", "day4_date", "variant_set", "status"])
        for i, c in enumerate(deduped, 1):
            r = c["row"]
            w.writerow([i, r.get("address"), r.get("listing_agent"), r.get("agent_phone"),
                        round(c["offer"]),
                        (today).isoformat(), (today + timedelta(days=1)).isoformat(),
                        (today + timedelta(days=3)).isoformat(),
                        "A" if i % 2 else "B", "queued"])

    # 4) contract_data.json - written-offer packets (texts are not offers)
    con_path = os.path.join(args.out, "contract_data.json")
    with open(con_path, "w", encoding="utf-8") as f:
        json.dump([contract_data(c, args.buyer_name, cfg) for c in deduped], f, indent=2)

    # 5) funnel.md - weekly metrics template
    fun_path = os.path.join(args.out, "funnel.md")
    with open(fun_path, "w", encoding="utf-8") as f:
        f.write(FUNNEL_TEMPLATE.format(week=today.strftime("%Y-%m-%d")))

    print("offer-engine v{} | mode={}".format(VERSION, cfg["offer_mode"]))
    print("listings in: {}".format(len(rows)))
    print("rejected by criteria: {}".format(len(rejected)))
    for r, why in rejected:
        print("  x {} -> {}".format(r.get("address"), why))
    print("deduped vs contact log: {}".format(len(skipped)))
    print("OFFER CANDIDATES: {}".format(len(deduped)))
    for i, c in enumerate(deduped, 1):
        r = c["row"]
        print("  #{i} {addr} | list {lp} -> offer {ofr} ({pct}% under) | "
              "{dom} DOM | {agent} {phone}".format(
                  i=i, addr=r.get("address"), lp=money(c["list_price"]),
                  ofr=money(c["offer"]), pct=c["discount_pct"], dom=c["dom"],
                  agent=r.get("listing_agent"), phone=r.get("agent_phone")))
    print("wrote: {}, {}, {}, {}, {}".format(
        cand_path, sms_path, q_path, con_path, fun_path))


if __name__ == "__main__":
    main()
