# THE WORKFLOW — maximum-money wholesale offer loop

**Blunt first:** no workflow guarantees money. Anyone who sells you a guarantee
is selling you something. What this does is maximize *expected* profit per the
research: more written offers, faster replies, relentless follow-up, and
compliance that keeps fines from eating the spread.

## The money math (why each piece exists)

Expected monthly profit ≈
**offers sent × reply % × written-offer accept % × avg spread − costs − fines**

- Written offers (not texts) → callbacks + backup-offer position when the first
  buyer falls through. Biggest single lever in the research.
- Reply in under 5 minutes → most deals die from slow follow-up, not bad leads.
- 3-text sequence (days 1/2/4) → beats 1-text blasts on reply rate.
- Rotating copy → carriers flag identical mass copy; flagged numbers die.
- DNC scrub + A2P 10DLC + opt-outs → one TCPA violation ($500–$1,500/text)
  wipes out an entire deal's profit. Compliance IS profit protection.

## The loop (7 stages)

```
1. PULL      stale listings -> listings.csv
             (Zillow stale / Assigns / XLeads free skip trace / county data)
             Criteria: $130k+, 45-200 DOM (tighter: 60-90+), TLC/as-is/fixer/
             handyman keywords, NEVER turnkey/renovated/flipped.
2. RUN       python3 offer_engine.py listings.csv --contact-log contacted.csv
             --offer-mode lao --discount-pct 0.30 --buyer-name "YOUR LLC" --out out/
             -> candidates.csv, sms_sequences.md, followup_queue.csv,
                contract_data.json, funnel.md
3. SCORE     lead-scoring-cli on candidates.csv; re-deal-packet underwrites
             top candidates with comps (ARV / 70%-rule MAO). Kill bad offers
             BEFORE they burn an agent relationship.
4. APPROVE   founder approves BOTH the message variants AND the recipient batch.
             (Outreach gate. Staged drafts are not authorization.)
5. SEND      day-1 texts, 8am-9pm recipient local, DNC-scrubbed, A2P-registered.
             Replies answered in <5 min. Day-2 bump. Day-4 backup-position touch.
6. PAPER     on any "yes": send the WRITTEN offer/contract the same hour.
             TX: TREC 1-4 + equitable-interest disclosure DELIVERED before any
             assignment (timestamped proof). POF letter ready; end buyer funds EMD.
7. MEASURE   weekly funnel review per list type; rotate copy; log opt-outs;
             every dead offer becomes a backup offer on the next fall-through.
```

## Daily cadence

- **Morning:** pull fresh stale listings, run engine, score + underwrite top 10.
- **Midday:** founder reviews batch, approves message + recipients.
- **Afternoon:** day-1 sends go out; replies handled in under 5 minutes.
- **Evening:** day-2/day-4 follow-ups per followup_queue.csv; log everything.

## Weekly cadence

- Funnel review: reply % / opt-out % / offer-to-contract % per list type.
- If reply rate is low or opt-out rate is high → it's the copy. Rotate variants.
- Suppression list hygiene: every STOP honored across ALL campaigns <10 days.
- One new list type tested per week (pre-foreclosure, tax-delinquent, absentee).

## What kills the money (avoid list)

1. Texting numbers instead of sending paper — texts don't close, paper does.
2. Slow replies — the 5-minute rule is the whole game after the send.
3. One-and-done texting — no day-2/day-4 sequence, no backup offers.
4. Identical copy blasts — burned numbers, zero deliverability.
5. Skipping DNC/A2P/opt-out — fines eat the spread.
6. Bad offers to good agents — underwrite with comps first, always.
7. No POF/EMD ready — the #1 objection on low cash offers.

## Founder taps (only he can clear these)

1. **Listings feed** — browser pulls work; a paid vendor (PropStream/DealMachine
   ~$50–150/mo) scales it.
2. **Send layer** — Phound API or A2P-registered SMS platform; until then,
   manual sends only, batch-approved.
3. **Buyer LLC legal name** — drafts carry a placeholder until confirmed.
4. **POF letter + EMD structure** — transactional funder or program POF.
5. **TX attorney review** of the TREC 1-4 wholesaling provisions — once, up front.
6. **Investor-friendly title company** confirmed for assignments — before the
   first deal, not during it.
