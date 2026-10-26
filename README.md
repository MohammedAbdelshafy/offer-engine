# Offer Calculator

A command-line tool that filters a supplied listings file using your buy box, ranks candidates, estimates offer numbers from the rules you choose, and drafts follow-up messages for human review.
Drafts only. It does not scrape listings, send messages, sign contracts, or guarantee that a property is a deal.

Customer-facing name: **Offer Calculator**. The repository, package and command identifiers remain unchanged.

Pipeline:

1. **Tell it what you want** — criteria: ugly houses, min list price,
   days-on-market window, TLC/as-is keywords, nothing turnkey/flipped,
   fixed discount under list OR LAO mode (offer = list × (1 − discount %)).
2. **It drafts offers** — filters listings, ranks by discount depth, dedupes
   against your contact log.
3. **3-text SMS sequences** — day 1 opener / day 2 bump + written-offer pitch /
   day 4 backup-position touch, two rotating human-written variants per touch.
   **Drafts only — never sent by this tool.**
4. **Follow-up queue** — scheduled touches (followup_queue.csv).
5. **Contract data** — TREC 1-4-shaped packet per candidate (Texas) with the
   equitable-interest disclosure rule and a before-send checklist. Written
   offers beat texts: a texted number isn't an offer.
6. **Funnel tracker** — weekly metrics template (reply % / opt-out % /
   offer-to-contract % per list type).

See WORKFLOW.md for the full operating loop (daily/weekly cadence, the honest
money math, and what kills profit).

## buybox.py — the off-market lane

The confirmed DFW buy box as executable rules (Dallas/Tarrant, SFR, ugly/older,
3+ beds, individual distressed owners, no banks, no listed properties, 65% of
assessed, cash, as-is):

```bash
python3 buybox.py properties.csv --out picks/ --pick 10
```

Scores every row 0-100 across 7 transparent criteria, emits a verdict
(QUALIFIED / MARGINAL / DISQUALIFIED / VERIFY ADDRESS), the 65%-of-assessed
offer target, a ranked pick list, and — the key enhancement — a `data_gaps`
column naming exactly which fields each row is missing (owner, assessed value,
year built, beds) so you know what to enrich from county records before
choosing. Tested 10/10 against human-verified verdicts
(`--test-against <verdict-column>`).

## Install

Stdlib only. No dependencies.

```bash
python3 offer_engine.py listings.csv --contact-log contacted.csv \
  --buyer-name "Your LLC" --offer-mode lao --discount-pct 0.30 --out out/
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
- `sms_sequences.md` — day 1/2/4 agent text sequences, A/B variants.
  **Not sent.** The founder approves BOTH the message and the recipient batch
  before anything goes out. Compliance banner on every file: quiet hours,
  DNC scrub, A2P 10DLC, global suppression.
- `followup_queue.csv` — scheduled day-1/day-2/day-4 touches.
- `contract_data.json` — TREC 1-4 field packets + TX compliance checklist
  (equitable-interest disclosure delivered BEFORE assignment) + POF/EMD
  before-send checklist. Underwrite any candidate with
  comps via [re-deal-packet](https://github.com/MohammedAbdelshafy/re-deal-packet)
  (ARV / 70%-rule MAO) before you commit.
- `funnel.md` — weekly metrics template.

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
