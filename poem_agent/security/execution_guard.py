"""Enforce an explicit bounded path set and reject private-network destinations."""
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import socket


class ExecutionGuard:
    def __init__(self, max_retries=3, timeout_seconds=30):
        self.max_retries = max(0, min(int(max_retries), 5))
        self.timeout_seconds = max(1, min(int(timeout_seconds), 120))

    @staticmethod
    def within_root(root, candidate):
        try:
            Path(candidate).resolve().relative_to(Path(root).resolve())
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def validate_public_https(url):
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                return False
            host = parsed.hostname.rstrip(".").lower()
            if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
                return False
            addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            if not addresses:
                return False
            for item in addresses:
                address = ipaddress.ip_address(item[4][0])
                if not address.is_global:
                    return False
            return True
        except (OSError, ValueError):
            return False
