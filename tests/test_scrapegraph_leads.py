import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from scrapegraph_leads import (
    normalize_listing,
    normalize_url,
    extract_records,
    dedupe_candidates,
    run_searches,
)


class ScrapeGraphLeadTests(unittest.TestCase):
    def test_requires_source_url_cited_by_search_results(self):
        raw = {
            "address": "123 Oak St",
            "city": "Dallas",
            "state": "TX",
            "asking_price": "$185,000",
            "days_on_market": "93",
            "description": "as-is fixer needs work",
            "source_url": "https://example.com/listings/123-oak?utm_source=search",
        }
        candidate = normalize_listing(
            raw,
            cited_urls={"https://example.com/listings/123-oak"},
            first_seen_at="2026-10-21T16:00:00Z",
        )
        self.assertTrue(candidate["source_is_cited"])
        self.assertEqual(candidate["verification_status"], "SOURCE_CITED_REVIEW_REQUIRED")
        self.assertEqual(candidate["asking_price"], "185000")

    def test_uncited_or_incomplete_record_is_quarantined(self):
        raw = {"address": "123 Oak St", "city": "Dallas", "state": "TX", "source_url": "https://fake.example/house"}
        candidate = normalize_listing(raw, cited_urls=set(), first_seen_at="2026-10-21T16:00:00Z")
        self.assertEqual(candidate["verification_status"], "QUARANTINE_UNCITED_OR_INCOMPLETE")
        self.assertEqual(candidate["contact_status"], "NOT_COLLECTED")
        self.assertEqual(candidate["seller_intent"], "NOT_INFERRED")

    def test_extract_records_accepts_common_payload_shapes(self):
        self.assertEqual(extract_records({"listings": [{"address": "A"}]}), [{"address": "A"}])
        self.assertEqual(extract_records('{"properties":[{"address":"B"}]}'), [{"address": "B"}])
        self.assertEqual(extract_records({"other": "value"}), [])

    def test_url_normalization_removes_tracking_query(self):
        self.assertEqual(
            normalize_url("https://example.com/listing/7/?utm_source=x&fbclid=abc"),
            normalize_url("https://example.com/listing/7"),
        )

    def test_dedupe_keeps_stronger_candidate_for_same_address(self):
        a = {"address": "123 Oak Street", "city": "Dallas", "state": "TX", "source_url": "https://a.example/1", "signal_score": 30}
        b = {"address": "123 Oak St.", "city": "Dallas", "state": "TX", "source_url": "https://b.example/1", "signal_score": 50}
        result = dedupe_candidates([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["signal_score"], 50)

    def test_run_searches_uses_sdk_results_as_citation_gate(self):
        result_url = "https://example.com/listing/321"
        payload = {"listings": [{
            "source_url": result_url,
            "address": "321 Maple St",
            "city": "Dallas",
            "state": "TX",
            "asking_price": 200000,
            "days_on_market": 95,
            "description": "as-is fixer needs work",
        }]}

        class FakeClient:
            def __init__(self, api_key=None):
                self.api_key = api_key

            def search(self, query, **kwargs):
                self.query = query
                self.kwargs = kwargs
                return SimpleNamespace(
                    status="success",
                    error=None,
                    data=SimpleNamespace(
                        json_data=payload,
                        results=[SimpleNamespace(url=result_url, title="Public listing")],
                    ),
                )

        fake_module = SimpleNamespace(ScrapeGraphAI=FakeClient)
        with patch.dict(sys.modules, {"scrapegraph_py": fake_module}):
            rows = run_searches(["Dallas fixer"], 3, api_key="test-key")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verification_status"], "SOURCE_CITED_REVIEW_REQUIRED")
        self.assertEqual(rows[0]["contact_status"], "NOT_COLLECTED")


if __name__ == "__main__":
    unittest.main()
