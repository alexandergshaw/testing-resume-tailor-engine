"""In-memory fakes for the downstream clients (no network in tests)."""
import json

# Parser API v1.0.0 lens-based response.
PARSE_FIXTURE = {
    "results": {
        "field": {
            "kind": "emphasis",
            "top": {"id": "data_science", "label": "Data Science", "score": 0.8802,
                    "matched_terms": ["ETL", "Spark"], "low_confidence": False},
            "ranked": [
                {"id": "data_science", "label": "Data Science", "score": 0.8802,
                 "matched_terms": ["ETL", "Spark"]},
                {"id": "devops", "label": "DevOps & Cloud Infrastructure",
                 "score": 0.1198, "matched_terms": ["AWS"]},
            ],
        },
        "sector": {
            "kind": "emphasis",
            "top": {"id": "software_industry", "label": "Software Industry",
                    "score": 1.0, "matched_terms": ["agile"], "low_confidence": False},
            "ranked": [{"id": "software_industry", "label": "Software Industry",
                        "score": 1.0, "matched_terms": ["agile"]}],
        },
        "technologies": {
            "kind": "lexicon",
            "matched": [
                {"term": "spark", "display": "Spark",
                 "related": {"id": "data_science", "label": "Data Science"}},
                {"term": "aws", "display": "AWS",
                 "related": {"id": "devops", "label": "DevOps & Cloud Infrastructure"}},
                {"term": "kubernetes", "display": "Kubernetes",
                 "related": {"id": "devops", "label": "DevOps & Cloud Infrastructure"}},
            ],
        },
        "keywords": {
            "kind": "keywords",
            "items": [
                {"term": "etl", "display": "ETL", "score": 1.0, "source": "rake+lexicon",
                 "related": {"id": "data_science", "label": "Data Science"}},
                {"term": "build scalable data pipelines",
                 "display": "Build scalable Data pipelines", "score": 0.9, "source": "rake",
                 "related": {"id": "data_science", "label": "Data Science"}},
            ],
        },
    },
    "meta": {"token_count": 26, "version": "1.0.0"},
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
    def __init__(self, results_by_intent=None, error=None, research_calls=0):
        self.results_by_intent = results_by_intent or {}
        self.error = error
        self.batch_calls = 0
        self.research_calls = research_calls
        self.last_requests = None
        self.last_research = None

    def batch(self, requests):
        self.batch_calls += 1
        self.last_requests = requests
        if self.error:
            raise self.error
        return [self._envelope(r["intent"], r["params"]) for r in requests]

    def research(self, intent, params):
        self.research_calls += 1
        self.last_research = (intent, params)
        if self.error:
            raise self.error
        return self._envelope(intent, params)

    def _envelope(self, intent, params):
        data = self.results_by_intent.get(intent, {})
        source = ("GDELT — open data" if intent == "company.news"
                  else "Wikipedia — CC BY-SA 4.0")
        return {
            "intent": intent, "data": data,
            "sources": [{"name": source.split(" — ")[0], "attribution": source}]
            if data else [],
            "attribution_required": bool(data),
            "degraded": False, "warnings": [], "cache": {"hit": False, "age_s": None},
            "meta": {"version": "1.1.0"},
        }

    def health(self):
        return {"status": "ok", "version": "1.1.0"}


# A company.news data payload with a clearly-favorable and a sub-threshold item.
NEWS_DATA = {
    "company": "Acme Insurance Group", "as_of": "2026-06-16",
    "articles": [
        {"title": "Acme named to Best Places to Work 2026", "source": "businesswire.com",
         "url": "https://example.com/a", "published": "2026-06-10T00:00:00Z",
         "tone": 5.4, "language": "en"},
        {"title": "Acme posts record quarterly growth", "source": "reuters.com",
         "url": "https://example.com/b", "published": "2026-06-01T00:00:00Z",
         "tone": 3.1, "language": "en"},
        {"title": "Acme faces routine regulatory review", "source": "example.org",
         "url": "https://example.com/c", "published": "2026-05-20T00:00:00Z",
         "tone": 0.4, "language": "en"},  # below FAVORABLE_MIN_TONE -> dropped
    ],
}


class FakeGenerator:
    """Records the generate() call; returns a sentinel docx-ish blob unless
    configured to fail."""

    def __init__(self, error=None, output=b"PK\x03\x04fake-generated-docx"):
        self.error = error
        self.output = output
        self.calls = []

    def generate(self, document_type, content_json, *, template_text=None,
                 template_file=None, filename=None, strict=None):
        self.calls.append({
            "document_type": document_type,
            "content": json.loads(content_json),
            "has_file": template_file is not None,
            "strict": strict,
        })
        if self.error:
            raise self.error
        return self.output

    def health(self):
        return {"version": "1.0.0"}
