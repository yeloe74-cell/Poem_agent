"""Strict metadata validation before use; downloads require separate safe handling."""
from urllib.parse import urlsplit


class ImageValidator:
    ALLOWED_LICENSES = {"cc0", "by", "by-sa", "pdm", "cc-by", "cc-by-sa"}

    def metadata_valid(self, image: dict) -> bool:
        url = image.get("url", "")
        parsed = urlsplit(url)
        license_name = (image.get("license") or "").casefold().replace(" ", "-")
        return bool(parsed.scheme == "https" and parsed.hostname and image.get("source")
                    and image.get("license") and license_name in self.ALLOWED_LICENSES
                    and image.get("title"))

    def validate_bytes(self, content: bytes, content_type: str, max_bytes=8_000_000):
        if not content or len(content) > max_bytes:
            return False
        signatures = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",),
                      "image/gif": (b"GIF87a", b"GIF89a"), "image/webp": (b"RIFF",)}
        valid = signatures.get(content_type.split(";")[0].lower(), ())
        return any(content.startswith(signature) for signature in valid)
