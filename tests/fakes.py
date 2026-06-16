"""In-memory fakes for the downstream clients (no network in tests)."""

PARSE_FIXTURE = {
    "primary": {"id": "data_science", "label": "Data Science", "type": "field",
                "score": 0.68, "matched_terms": []},
    "secondary": {"id": "software_industry", "label": "Software Industry",
                  "type": "sector", "score": 0.23, "matched_terms": []},
    "emphases": [
        {"id": "data_science", "label": "Data Science", "type": "field", "score": 0.68},
        {"id": "software_industry", "label": "Software Industry", "type": "sector",
         "score": 0.23},
    ],
    "keywords": [
        {"term": "etl", "display": "ETL", "score": 1.0, "source": "lexicon",
         "related_emphasis": "Data Science", "related_emphasis_id": "data_science"},
        {"term": "cicd", "display": "CI/CD", "score": 0.9, "source": "rake+lexicon",
         "related_emphasis": "Software Industry", "related_emphasis_id": "software_industry"},
        {"term": "kubernetes", "display": "Kubernetes", "score": 0.8, "source": "lexicon",
         "related_emphasis": "DevOps", "related_emphasis_id": "devops"},
        {"term": "support data platforms", "display": "Support Data Platforms",
         "score": 0.5, "source": "rake", "related_emphasis": "Data Science",
         "related_emphasis_id": "data_science"},
    ],
    "meta": {"version": "0.3.0"},
}


class FakeParser:
    def __init__(self, response=None, error=None):
        self.response = response if response is not None else PARSE_FIXTURE
        self.error = error
        self.calls = 0

    def parse(self, text, max_keywords=30):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response

    def health(self):
        return {"status": "ok", "version": "0.3.0"}


class FakeResearcher:
    def __init__(self, results_by_intent=None, error=None):
        self.results_by_intent = results_by_intent or {}
        self.error = error
        self.batch_calls = 0
        self.last_requests = None

    def batch(self, requests):
        self.batch_calls += 1
        self.last_requests = requests
        if self.error:
            raise self.error
        return [self._envelope(r["intent"], r["params"]) for r in requests]

    def _envelope(self, intent, params):
        data = self.results_by_intent.get(intent, {})
        return {
            "intent": intent, "data": data,
            "sources": [{"name": "Wikipedia", "url": "https://en.wikipedia.org",
                         "license": "CC BY-SA 4.0",
                         "attribution": "Wikipedia — CC BY-SA 4.0"}] if data else [],
            "attribution_required": bool(data),
            "degraded": False, "warnings": [], "cache": {"hit": False, "age_s": None},
            "meta": {"version": "1.0.0"},
        }

    def health(self):
        return {"status": "ok", "version": "1.0.0"}
