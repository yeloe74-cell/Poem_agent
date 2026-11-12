"""Openverse public search adapter; licensing metadata is retained for review."""
from __future__ import annotations
import asyncio
import json
import urllib.parse
import urllib.request


class OpenverseSource:
    endpoint = "https://api.openverse.org/v1/images/"

    async def search(self, keywords: str, limit: int = 5):
        query = urllib.parse.urlencode({"q": keywords, "page_size": max(1, min(limit, 20))})
        request = urllib.request.Request(self.endpoint + "?" + query, headers={"User-Agent": "PoemAgent/1.0"})
        def fetch():
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.loads(response.read())
            return [{"url": row.get("url"), "thumbnail": row.get("thumbnail"),
                     "title": row.get("title"), "creator": row.get("creator"),
                     "license": row.get("license"), "license_url": row.get("license_url"),
                     "source": "Openverse", "attribution": row.get("attribution")}
                    for row in payload.get("results", [])]
        return await asyncio.to_thread(fetch)
