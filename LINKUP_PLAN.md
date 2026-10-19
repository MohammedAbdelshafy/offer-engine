# Muse Loop x MBM Real Estate - Link-Up Plan

**Date:** 2026-10-19 · **Source:** olivia_schremmer IG post ("Muse has completely changed the way I make money")

## The Muse loop (from the screenshots)

1. **Tell Muse what you want** - plain-English criteria: ugly houses, $130k+ list,
   45-200 days on market, TLC/as-is keywords, nothing turnkey/flipped, offers
   $70k under list, starting with Houston.
2. **Muse drafts offers** - candidate list: address, list -> offer, agent name +
   phone, DOM, notes (as-is fixer, short sale, cash-only teardown).
3. **Muse sends the text** - SMS to the listing agent: reviewed the numbers,
   $X cash, 21-day close, "I can get the contract sent over."
4. **Tell Muse to send a contract** - fills the state contract (FAR/BAR in FL;
   TREC 1-4 in TX): buyer LLC, property, $329,900 cash, $3,299 earnest (1%),
   escrow agent, 21-day close -> PDF.
5. **Executed contract** -> **Signatures** - buyer + seller sign, listing
   associate/broker on record.

## How the founder's existing stack maps to it

| Muse stage | Already built (his repos) | Gap closed today |
|---|---|---|
| Criteria -> candidates | lead-scoring-cli (scores leads) | **offer_engine.py**: criteria filter + $X-under-list offers + ranking |
| Dedupe vs contact log | MBM-Control LeadEngine (verification gate) | built into the engine |
| Agent SMS | MBM-Control Outreach (templates, opt-out) / Phound (manual click-to-send) | engine emits **drafts only** - outreach gate holds |
| Contract fill | - | engine emits **TREC 1-4 contract-data JSON** per candidate |
| Underwriting | re-deal-packet (ARV, 70%-rule MAO from comps) | candidates.csv feeds it directly |
| Buyer matching | lead-scoring-cli `match` | unchanged |

## Strategic note

His buy box is **off-market** distressed owners (no listed properties). The Muse
loop is the **on-market** lane: stale MLS listings -> text the listing agent ->
low cash offer. Both lanes feed the same wholesale machine (assignment fee
$5k-$20k/deal). No conflict - it's a second lane, and the listing agent's
number is published for business contact.

## Built today (v1, tested)

`~/workspace/muse-offer-engine/offer_engine.py` - stdlib only, no network, no sending.
Demo on 6 sample DFW listings: 6 in -> 2 rejected (turnkey, DOM<45) -> 1 deduped
(already contacted) -> **3 ranked offer candidates** with SMS drafts + TREC
contract data. Outputs: `demo_out/candidates.csv`, `sms_drafts.md`, `contract_data.json`.

## Still needed (founder taps)

1. **Real listings feed** - Zillow/Redfin have no free API; options: browser pulls
   from his preferred sources (auction.com, tranchi.ai, Zillow) into the listings
   CSV shape, or a paid vendor (PropStream/DealMachine ~$50-150/mo).
2. **Buyer LLC legal name** - drafts use a placeholder until he confirms it.
3. **Send layer** - Phound API still not provisioned; SMS stays manual/draft until
   he approves message + batch (outreach gate).
4. **TREC 1-4 PDF fill + e-sign** - contract_data.json is shaped for it; needs the
   official TREC form template and his title/escrow agent details.
5. **Repo decision** - push as a new public repo (his CLI pattern) or fold into
   MBM-Control. Awaiting his call.
