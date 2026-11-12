"""Provider adapter interface and OpenAI/Anthropic HTTP implementations."""
from __future__ import annotations
import asyncio
import json
import time
import urllib.request


class ProviderAdapter:
    def __init__(self, provider, api_key, model, timeout=25):
        self.provider, self.api_key, self.model, self.timeout = provider, api_key, model, timeout

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
            raise ValueError("Unsupported provider")
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        def send():
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())
            if self.provider == "openai":
                return data["choices"][0]["message"]["content"]
            return "".join(part.get("text", "") for part in data.get("content", []))
        return await asyncio.to_thread(send)


class AIBrain:
    def __init__(self, router, adapters):
        self.router, self.adapters, self.usage = router, adapters, []

    async def complete(self, prompt, task="general", language="en", complexity=.4, context_tokens=0, system=""):
        tried, last_error = set(), None
        for _ in range(len(self.router.candidates)):
            candidate = self.router.choose(task, language, complexity, context_tokens)
            if candidate is None or (candidate.provider, candidate.model) in tried:
                break
            tried.add((candidate.provider, candidate.model))
            adapter = self.adapters.get(candidate.provider)
            if not adapter:
                self.router.record_failure(candidate)
                continue
            start = time.monotonic()
            try:
                answer = await adapter.complete(prompt, system)
                self.router.record_success(candidate)
                self.usage.append({"provider": candidate.provider, "model": candidate.model, "ok": True, "latency": time.monotonic()-start})
                return answer
            except Exception as exc:
                last_error = exc
                self.router.record_failure(candidate)
                self.usage.append({"provider": candidate.provider, "model": candidate.model, "ok": False, "latency": time.monotonic()-start})
        raise RuntimeError("Configured model providers unavailable") from last_error
