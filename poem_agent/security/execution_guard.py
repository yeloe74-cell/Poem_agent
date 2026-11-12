"""Bound execution time, retries, and URL/file safety checks."""
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import socket


class ExecutionGuard:
    def __init__(self, max_retries=3, timeout_seconds=30):
        self.max_retries = max(0, min(max_retries, 5))
        self.timeout_seconds = max(1, min(timeout_seconds, 120))

    @staticmethod
    def within_root(root, candidate):
        try:
            Path(candidate).resolve().relative_to(Path(root).resolve())
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def validate_public_https(url):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        try:
            addresses = socket.getaddrinfo(parsed.hostname, None)
            return all(not ipaddress.ip_address(item[4][0]).is_private and
                       not ipaddress.ip_address(item[4][0]).is_loopback and
                       not ipaddress.ip_address(item[4][0]).is_link_local and
                       not ipaddress.ip_address(item[4][0]).is_reserved for item in addresses)
        except (OSError, ValueError):
            return False
