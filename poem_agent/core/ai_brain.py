"""Provider-specific adapters and resilient, model-aware request routing."""
from __future__ import annotations
import asyncio
import json
import time
import urllib.error
import urllib.request


class ProviderAdapter:
    def __init__(self, provider, api_key, model, timeout=25, max_retries=2):
        self.provider, self.api_key, self.model = provider, api_key, model
        self.timeout, self.max_retries = max(1, timeout), max(0, min(max_retries, 4))

    async def complete(self, prompt, system=""):
        if not self.api_key:
            raise RuntimeError(f"{self.provider} key not configured")
        if self.provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        elif self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
            body = {"model": self.model, "max_tokens": 1200, "system": system, "messages": [{"role": "user", "content": prompt}]}
        else:
            raise ValueError("Unsupported provider adapter")
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        def send():
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())
            if self.provider == "openai":
                return data["choices"][0]["message"]["content"]
            return "".join(part.get("text", "") for part in data.get("content", []))
        delay = .5
        for attempt in range(self.max_retries + 1):
            try:
                return await asyncio.to_thread(send)
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.max_retries:
                    raise RuntimeError(f"{self.provider} returned HTTP {exc.code}") from exc
            except (TimeoutError, urllib.error.URLError):
                if attempt == self.max_retries:
                    raise
            await asyncio.sleep(delay)
            delay *= 2


class AIBrain:
    def __init__(self, router, adapters):
        self.router, self.adapters, self.usage = router, adapters, []

    async def complete(self, prompt, task="general", language="en", complexity=.4,
                       context_tokens=0, system=""):
        tried, last_error = set(), None
        for _ in range(max(1, len(self.router.candidates))):
            candidate = self.router.choose(task, language, complexity, context_tokens, tried)
            if candidate is None:
                break
            key = (candidate.provider, candidate.model)
            tried.add(key)
            adapter = self.adapters.get(key) or self.adapters.get(candidate.provider)
            if adapter is None:
                self.router.record_failure(candidate)
                last_error = RuntimeError(f"Adapter missing for {candidate.provider}/{candidate.model}")
                continue
            if getattr(adapter, "model", candidate.model) != candidate.model:
                last_error = RuntimeError("Adapter model does not match routed model")
                self.router.record_failure(candidate)
                continue
            started = time.monotonic()
            try:
                answer = await asyncio.wait_for(adapter.complete(prompt, system), timeout=35)
                self.router.record_success(candidate)
                self.usage.append({"provider": candidate.provider, "model": candidate.model,
                    "task": task, "ok": True, "latency_ms": int((time.monotonic()-started)*1000)})
                return answer
            except Exception as exc:
                last_error = exc
                self.router.record_failure(candidate)
                self.usage.append({"provider": candidate.provider, "model": candidate.model,
                    "task": task, "ok": False, "latency_ms": int((time.monotonic()-started)*1000)})
        raise RuntimeError("No configured model completed the request") from last_error

    def performance(self):
        count = len(self.usage)
        return {"calls": count, "success_rate": (sum(row["ok"] for row in self.usage) / count if count else None),
                "mean_latency_ms": (sum(row["latency_ms"] for row in self.usage) // count if count else None)}
