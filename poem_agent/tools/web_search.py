"""Optional web search via a configured endpoint; no implicit scraping."""
import os
import json
import urllib.parse
import urllib.request


class WebSearch:
    def __init__(self, endpoint=None, api_key=None):
        self.endpoint = endpoint or os.getenv("WEB_SEARCH_ENDPOINT", "")
        self.api_key = api_key or os.getenv("WEB_SEARCH_API_KEY", "")

    def search(self, query, limit=5):
        if not self.endpoint or not self.api_key:
            raise RuntimeError("A permitted search endpoint and API key must be configured")
        url = self.endpoint + "?" + urllib.parse.urlencode({"q": query, "limit": max(1, min(limit, 10))})
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read())
        return data.get("results", [])
