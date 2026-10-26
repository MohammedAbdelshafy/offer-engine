# ScrapeGraphAI: DFW listing candidate discovery

This is a research-only discovery adapter for the existing `offer-engine` workflow. It uses the official ScrapeGraphAI Python SDK's v2 Search API to find public listing pages and extract a small, auditable property record.

## Setup

```bash
python -m pip install scrapegraph-py
export SGAI_API_KEY="your-key-from-the-ScrapeGraphAI-dashboard"
```

Do not paste the key into source, a notebook, a CSV, or a GitHub issue. For CI, store it as a repository/environment secret named `SGAI_API_KEY`.

## Run a limited first batch

```bash
python scrapegraph_leads.py --max-results 5 --out out/scrapegraph_candidates.csv
```

The default run uses three DFW searches, five results each. Search with structured extraction costs 5 credits per result according to ScrapeGraphAI's current public pricing, so 15 successful result pages are approximately 75 credits before any other account-side usage. Start small; check your live plan/credits in the ScrapeGraphAI dashboard before scaling.

You can override the search phrases, one per `--query` argument:

```bash
python scrapegraph_leads.py \
  --query 'Dallas TX single family fixer upper price reduced' \
  --query 'Fort Worth TX as-is listing back on market' \
  --max-results 5 \
  --out out/dfw_candidates.csv
```

## Run from GitHub Actions (after the pull request is merged)

1. Open repository **Settings → Secrets and variables → Actions**.
2. Add a repository secret named `SGAI_API_KEY` with your ScrapeGraphAI key. Never commit the key or put it in a workflow input.
3. Open **Actions → ScrapeGraph DFW Lead Discovery → Run workflow** and choose a result cap (start with 1–3 per query to conserve credits).
4. Download the `scrapegraph-dfw-candidates-<run number>` artifact and review the source URLs before moving anything into the offer workflow.

The workflow is manual-only. It does not send outreach or write to the canonical lead database. It will fail closed if the secret is missing. The workflow is only available in Actions after the PR's workflow file has been merged into the default branch.

## Output and operating contract

- Writes to a separate CSV by default. It does **not** update the canonical MBM lead database.
- Each row carries the source URL, query, first-seen UTC timestamp, observed signals, and a deterministic research-priority score. The score is not a probability of seller intent.
- A result must have a URL matching the Search API's returned source URLs, plus address, city, state, and price, before it earns `SOURCE_CITED_REVIEW_REQUIRED`. Other rows are quarantined as `QUARANTINE_UNCITED_OR_INCOMPLETE`.
- `seller_intent` is always `NOT_INFERRED`. `contact_status` is always `NOT_COLLECTED`. This adapter does not collect private homeowner phone numbers or emails, send outreach, generate offers, or write to databases.
- Before any candidate is used: manually confirm that the listing is live on the source page, verify current ask and days-on-market, check ownership/listing authority as applicable, gather defensible recent sold comps, estimate repairs and costs, and qualify the agent/seller. Then move only approved, evidenced rows through the established `offer-engine` flow.
- Use only sources and pages you are authorized to access. Do not bypass login walls, access controls, or site restrictions. A search result is a research lead, not proof the property is currently available or that the seller will accept an offer.

## Test

```bash
python -m unittest discover -s tests
python -m py_compile scrapegraph_leads.py
```

The tests use a fake SDK response and do not spend API credits.

## Official references

- ScrapeGraphAI Search v2 docs: https://docs.scrapegraphai.com/services/search
- Python SDK: https://github.com/ScrapeGraphAI/scrapegraph-py
- Current public pricing: https://scrapegraphai.com/pricing
