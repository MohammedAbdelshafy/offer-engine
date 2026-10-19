# offer-engine

Muse-style real-estate offer engine: plain-English buying criteria in,
ranked cash offers out.

Pipeline (mirrors the wholesale "Muse" loop):

1. **Tell it what you want** — criteria: ugly houses, min list price,
   days-on-market window, TLC/as-is keywords, nothing turnkey/flipped,
   fixed discount under list.
2. **It drafts offers** — filters listings, ranks by discount depth, dedupes
   against your contact log.
3. **Agent SMS drafts** — one personalized text per candidate
   ("$X cash, 21-day close"). **Drafts only — never sent by this tool.**
4. **Contract data** — TREC 1-4-shaped data packet per candidate (Texas),
   ready to fill into the official form / e-sign.

## Install

Stdlib only. No dependencies.

```bash
python3 offer_engine.py listings.csv --contact-log contacted.csv \
  --buyer-name "Your LLC" --out out/
```

## Inputs

**listings.csv** — one row per listing:

```
address,city,state,zip,list_price,dom,beds,baths,sqft,year_built,
description,listing_agent,agent_phone,brokerage
```

**contacted.csv** (optional, dedupe) — already-contacted addresses/phones:

```
address,agent_phone,contacted_date,channel,outcome
```

## Outputs (in `--out`)

- `candidates.csv` — ranked offers. Feed it to
  [lead-scoring-cli](https://github.com/MohammedAbdelshafy/lead-scoring-cli)
  for scoring.
- `sms_drafts.md` — agent texts. **Not sent.** The founder approves BOTH the
  message and the recipient batch before anything goes out.
- `contract_data.json` — TREC 1-4 field packets. Underwrite any candidate with
  comps via [re-deal-packet](https://github.com/MohammedAbdelshafy/re-deal-packet)
  (ARV / 70%-rule MAO) before you commit.

## Criteria flags

```
--under 70000        discount under list price (offer = list - under)
--min-price 130000   minimum list price
--dom-min 45 --dom-max 200
--close-days 21      closing timeline used in drafts + contract data
```

## What it does not do

No listing scraping, no sending, no e-signing, no guaranteed deals.
It turns a listings CSV into ranked, ready-to-review offer packets —
the judgment and the send button stay human.

## License

MIT — Mohammed Abdelshafy
