"""AI brain (main file 04/10).

* Talks to Anthropic, OpenAI-compatible and Gemini APIs through one `complete()`.
* Each task (analysis, classification, conversation ...) has its own model chain
  from settings; if one provider fails the next one in the chain is tried.
* The brain only ANALYSES: prompts forbid writing, changing or translating poems,
  and author names are never invented.
* Everything the AI returns is validated; bad output raises AIError instead of
  leaking into the database.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any, Iterable, Mapping

from config.constants import CATEGORIES, EMOTIONS, EMOTION_VISUALS, INTENTS
from config.settings import Settings
from core import prompts
from core.errors import AIError, HTTPError
from core.http_client import HttpClient
from core.intent_rules import rule_intent
from core.models import Intent, PoemAnalysis

log = logging.getLogger(__name__)
UNKNOWN_MESSAGE = "နားမလည်သေးဘူးခင်ဗျာ၊ နည်းနည်းပြန်ရှင်းပြပေးပါဦး။"
_QUERY_OK = re.compile(r"^[A-Za-z][A-Za-z \-]{2,38}$")


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array found in model output (handles ``` fences)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise AIError("AI output contained no valid JSON")


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


class AIBrain:
    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http
        self.extra_categories: set[str] = set()
        self.usage: Counter[str] = Counter()

    # ------------------------------------------------------------------
    # provider layer
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self.settings.ai_keys)

    async def complete(self, task: str, system: str, user: str, *, max_tokens: int = 900,
                       temperature: float = 0.2) -> tuple[str, str]:
        """Returns (text, 'provider:model'). Tries each provider in the task's chain."""
        routes = self.settings.task_routes.get(task, ())
        errors: list[str] = []
        for provider, model in routes:
            key = self.settings.ai_keys.get(provider)
            if not key:
                continue
            try:
                text = await self._call(provider, model, key, system, user, max_tokens, temperature)
            except (HTTPError, AIError, KeyError, IndexError, TypeError) as exc:
                errors.append(f"{provider}:{model} -> {exc}")
                log.warning("AI call failed (%s:%s): %s", provider, model, exc)
                continue
            self.usage[task] += 1
            return text, f"{provider}:{model}"
        raise AIError("no AI provider could answer: " + ("; ".join(errors) or "no API key configured"))

    async def _call(self, provider: str, model: str, key: str, system: str, user: str,
                    max_tokens: int, temperature: float) -> str:
        base = self.settings.ai_base_urls[provider].rstrip("/")
        if provider == "anthropic":
            data = await self.http.post_json(
                f"{base}/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json_body={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                           "system": system, "messages": [{"role": "user", "content": user}]})
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        elif provider == "openai":
            data = await self.http.post_json(
                f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                json_body={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            text = data["choices"][0]["message"]["content"] or ""
        elif provider == "gemini":
            data = await self.http.post_json(
                f"{base}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                json_body={"systemInstruction": {"parts": [{"text": system}]},
                           "contents": [{"role": "user", "parts": [{"text": user}]}],
                           "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}})
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        else:
            raise AIError(f"unknown provider {provider}")
        if not text.strip():
            raise AIError("empty AI response")
        return text

    async def _json_task(self, task: str, system: str, user: str, **kwargs: Any) -> tuple[Any, str]:
        """complete() + JSON parsing, with one stricter retry."""
        text, model = await self.complete(task, system, user, **kwargs)
        try:
            return extract_json(text), model
        except AIError:
            text, model = await self.complete(task, system, user + "\n\nReturn ONLY valid JSON.", **kwargs)
            return extract_json(text), model

    # ------------------------------------------------------------------
    # poetry understanding
    # ------------------------------------------------------------------
    def _category_keys(self) -> set[str]:
        return set(CATEGORIES) | self.extra_categories

    async def analyze_poem(self, text: str) -> PoemAnalysis:
        user = (f"Allowed emotion keys: {', '.join(EMOTIONS)}\n"
                f"Allowed category keys: {', '.join(sorted(self._category_keys()))}\n\n"
                f'Poem:\n"""\n{text[:2000]}\n"""')
        data, model = await self._json_task("poetry_analysis", prompts.ANALYZE_SYSTEM, user, max_tokens=700)
        return self.validate_analysis(data, model)

    def validate_analysis(self, data: Any, model: str = "") -> PoemAnalysis:
        if not isinstance(data, dict):
            raise AIError("analysis is not a JSON object")
        emotions: list[dict[str, Any]] = []
        for item in data.get("emotions") or []:
            if isinstance(item, dict) and item.get("name") in EMOTIONS:
                emotions.append({"name": item["name"], "score": round(_clamp(item.get("score"), 0, 1, 0.5), 2)})
        emotions = sorted({e["name"]: e for e in emotions}.values(), key=lambda e: -e["score"])[:4]
        valid_cats = self._category_keys()
        cats = [c for c in (data.get("categories") or []) if isinstance(c, str) and c in valid_cats][:3]
        quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}
        themes = [t.strip() for t in (data.get("visual_themes") or []) if isinstance(t, str) and _QUERY_OK.match(t.strip())][:4]
        return PoemAnalysis(
            emotions=emotions, categories=cats or ["free_verse"],
            quality_score=round(_clamp(quality.get("score"), 0, 100, 50.0), 1),
            quality_notes=str(quality.get("notes", ""))[:300], visual_themes=themes, model_used=model)

    async def judge_duplicate(self, text_a: str, text_b: str) -> tuple[bool, float]:
        """Semantic check for borderline-similar poems. Returns (same, confidence)."""
        user = f'Poem A:\n"""\n{text_a[:1200]}\n"""\n\nPoem B:\n"""\n{text_b[:1200]}\n"""'
        data, _ = await self._json_task("semantic", prompts.DUPLICATE_SYSTEM, user, max_tokens=120)
        if not isinstance(data, dict):
            raise AIError("duplicate verdict is not an object")
        return bool(data.get("same")), _clamp(data.get("confidence"), 0, 1, 0.0)

    # ------------------------------------------------------------------
    # images
    # ------------------------------------------------------------------
    async def image_queries(self, poem_text: str, emotions: Iterable[Mapping[str, Any]],
                            visual_themes: Iterable[str] = (), avoid: Iterable[str] = ()) -> list[str]:
        """Search queries for stock-photo sites. Works offline via built-in fallbacks."""
        emo_names = [e["name"] for e in emotions if e.get("name") in EMOTIONS]
        avoid_words = [a.lower() for a in avoid if a]
        queries: list[str] = []
        if self.available:
            user = (f"Emotions: {', '.join(emo_names) or 'unknown'}\nSuggested themes: {', '.join(visual_themes)}\n"
                    f"Avoid: {', '.join(avoid_words) or 'nothing'}\nPoem:\n{poem_text[:600]}")
            try:
                data, _ = await self._json_task("image_query", prompts.IMAGE_QUERY_SYSTEM, user, max_tokens=150)
                queries += [q.strip() for q in (data.get("queries") or []) if isinstance(q, str) and _QUERY_OK.match(q.strip())]
            except (AIError, AttributeError) as exc:
                log.info("image query AI unavailable, using fallback: %s", exc)
        queries += list(visual_themes)
        for name in emo_names[:2]:
            queries += EMOTION_VISUALS.get(name, [])
        queries += ["calm landscape", "quiet morning light"]
        seen: set[str] = set()
        out: list[str] = []
        for q in queries:
            key = q.lower()
            if key in seen or any(w in key for w in avoid_words):
                continue
            seen.add(key)
            out.append(q)
        return out[:4]

    async def judge_image_match(self, poem_text: str, description: str) -> float | None:
        """0-100 fit between a poem and a photo *description* (text only). None if unavailable."""
        if not self.available or not description.strip():
            return None
        user = f"Poem:\n{poem_text[:600]}\n\nPhoto description: {description[:300]}"
        try:
            data, _ = await self._json_task("image_query", prompts.IMAGE_MATCH_SYSTEM, user, max_tokens=60)
            return _clamp(data.get("score"), 0, 100, 0.0) if isinstance(data, dict) else None
        except AIError:
            return None

    # ------------------------------------------------------------------
    # owner conversation
    # ------------------------------------------------------------------
    async def parse_owner_message(self, text: str, *, awaiting_confirm: bool = False,
                                  context: Mapping[str, Any] | None = None) -> Intent:
        """Rules first (fast, safe); the AI handles everything else."""
        hit = rule_intent(text, awaiting_confirm=awaiting_confirm)
        if hit:
            return hit
        if not self.available:
            return Intent("unknown", clarification=UNKNOWN_MESSAGE)
        user = f"Context: {json.dumps(context or {}, ensure_ascii=False, default=str)[:1500]}\n\nOwner message: {text[:500]}"
        try:
            data, _ = await self._json_task("conversation", prompts.INTENT_SYSTEM, user, max_tokens=300)
        except AIError as exc:
            log.warning("intent AI failed: %s", exc)
            return Intent("unknown", clarification=UNKNOWN_MESSAGE)
        return self.validate_intent(data)

    @staticmethod
    def validate_intent(data: Any) -> Intent:
        if not isinstance(data, dict):
            return Intent("unknown", clarification=UNKNOWN_MESSAGE)
        name = data.get("intent")
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        conf = _clamp(data.get("confidence"), 0, 1, 0.0)
        clarification = data.get("clarification") if isinstance(data.get("clarification"), str) else None
        if name not in INTENTS or name in ("confirm", "cancel_confirm"):
            return Intent("unknown", clarification=clarification or UNKNOWN_MESSAGE, source="ai")
        # Safety: the AI alone may not publish, and weak guesses become questions.
        if (name == "approve" and conf < 0.9) or conf < 0.6:
            return Intent("unknown", confidence=conf, source="ai",
                          clarification=clarification or UNKNOWN_MESSAGE)
        return Intent(name, params, conf, clarification, "ai")

