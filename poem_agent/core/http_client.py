
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from core.errors import HTTPError


log = logging.getLogger(__name__)

MAX_BODY = 20 * 1024 * 1024
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

Transport = Callable[
    [str, str, dict, bytes | None, float],
    tuple[int, dict, bytes],
]


def validate_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise HTTPError(0, "URL must not be empty")

    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise HTTPError(0, "invalid URL") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPError(0, "unsupported URL scheme")

    if not parsed.hostname:
        raise HTTPError(0, "URL hostname is missing")

    if parsed.username or parsed.password:
        raise HTTPError(0, "URL credentials are not allowed")

    return url


def urllib_transport(
    method: str,
    url: str,
    headers: dict,
    body: bytes | None,
    timeout: float,
) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_BODY + 1)

            if len(data) > MAX_BODY:
                raise HTTPError(0, "response exceeds maximum size")

            return response.status, dict(response.headers), data

    except urllib.error.HTTPError as exc:
        data = exc.read(MAX_BODY + 1)

        if len(data) > MAX_BODY:
            raise HTTPError(exc.code, "error response exceeds maximum size")

        return exc.code, dict(exc.headers or {}), data


class HttpClient:
    def __init__(
        self,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 1.0,
        user_agent: str = "PoemAgent/1.0 (poetry channel assistant)",
        transport: Transport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retries < 0:
            raise ValueError("retries cannot be negative")
        if backoff < 0:
            raise ValueError("backoff cannot be negative")

        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.user_agent = user_agent
        self._transport = transport or urllib_transport
        self._sleep = sleep or asyncio.sleep

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> tuple[int, dict, bytes]:
        url = validate_url(url)
        method = method.upper().strip()

        if not method:
            raise HTTPError(0, "HTTP method is empty")

        if params:
            parsed = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            query.extend(
                (key, value)
                for key, values in params.items()
                for value in (
                    values if isinstance(values, (list, tuple)) else [values]
                )
            )

            url = urllib.parse.urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urllib.parse.urlencode(query, doseq=True),
                    parsed.fragment,
                )
            )

        request_headers = {
            "User-Agent": self.user_agent,
            **dict(headers or {}),
        }

        body = None

        if json_body is not None:
            try:
                body = json.dumps(
                    json_body,
                    ensure_ascii=False,
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise HTTPError(0, f"invalid JSON request body: {exc}") from exc

            request_headers.setdefault(
                "Content-Type",
                "application/json",
            )

        retryable_method = method in {"GET", "HEAD", "OPTIONS"}
        attempts = self.retries + 1 if retryable_method else 1
        last_error: HTTPError | None = None

        for attempt in range(attempts):
            try:
                status, response_headers, data = await asyncio.to_thread(
                    self._transport,
                    method,
                    url,
                    request_headers,
                    body,
                    self.timeout,
                )

                if not isinstance(data, bytes):
                    raise HTTPError(0, "invalid transport response")

                if len(data) > MAX_BODY:
                    raise HTTPError(0, "response exceeds maximum size")

                if 200 <= status < 400:
                    return status, dict(response_headers), data

                message = data[:500].decode(
                    "utf-8",
                    errors="replace",
                )
                last_error = HTTPError(status, message)

                if status not in RETRYABLE_STATUS:
                    raise last_error

            except HTTPError as exc:
                if exc.status not in RETRYABLE_STATUS and exc.status != 0:
                    raise
                last_error = exc

            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = HTTPError(0, str(exc))

            if attempt < attempts - 1:
                delay = self.backoff * (2 ** attempt)

                log.warning(
                    "HTTP request failed; retrying in %.1fs",
                    delay,
                )
                await self._sleep(delay)

        if last_error is None:
            raise HTTPError(0, "request failed")

        raise last_error

    async def json(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        _, _, data = await self.request(method, url, **kwargs)

        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPError(200, f"invalid JSON response: {exc}") from exc

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        return await self.json("GET", url, **kwargs)

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        return await self.json("POST", url, **kwargs)

    async def download_image(
        self,
        url: str,
        dest_dir: Path,
        stem: str,
    ) -> tuple[Path, str]:
        _, headers, data = await self.request("GET", url)

        content_type = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == "content-type"
            ),
            "",
        ).split(";", 1)[0].strip().lower()

        extension = IMAGE_TYPES.get(content_type)

        if extension is None:
            raise HTTPError(
                200,
                f"unsupported image type: {content_type or 'unknown'}",
            )

        safe_stem = re.sub(
            r"[^a-zA-Z0-9_.-]+",
            "_",
            str(stem),
        ).strip("._")

        if not safe_stem:
            raise HTTPError(0, "invalid image filename")

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        path = dest_dir / f"{safe_stem}{extension}"
        path.write_bytes(data)

        digest = hashlib.sha256(data).hexdigest()

        return path, digest

    async def head_ok(self, url: str) -> bool:
        try:
            await self.request("HEAD", url)
            return True
        except HTTPError:
            return False
      
