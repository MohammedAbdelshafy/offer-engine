---
type: repository
status: active
owner_repo: MohammedAbdelshafy/offer-engine
product_name: Offer Engine
source_of_truth: https://github.com/MohammedAbdelshafy/offer-engine
---

# Offer Engine CONTEXT

One job: turn a supplied listing file and explicit buy-box criteria into ranked candidates and draft offer materials for human review.

## Inputs
- Usage and safeguards: [README](README.md)
- Full operating loop: [WORKFLOW](WORKFLOW.md)
- Scoring/filters: [buybox.py](buybox.py)
- Implementation: [offer_engine.py](offer_engine.py)

## Process
1. Read the listing file and optional contact log.
2. Apply the stated buy-box/discount rules and rank candidates.
3. Generate draft messages and follow-up queue records.
4. Produce the supported contract-data packet and checklist.
5. Require human review before any contact, offer or contract action.

## Output
Ranked candidate CSV, draft message sequences, a follow-up queue and a review checklist.

## Check
Run the current tests and compare the output against known sample verdicts. Confirm quiet hours, DNC/suppression and legal disclosure requirements before using any draft. The tool does not scrape listings, send messages or guarantee deals.
