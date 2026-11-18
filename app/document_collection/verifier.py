from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urljoin, urlsplit

from .contracts import PageCapture


class UnsafeDestination(ValueError):
    pass


class _RateGate:
    def __init__(self):
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def wait(self, host: str, interval: float) -> None:
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next.get(host, now) - now)
            self._next[host] = max(now, self._next.get(host, now)) + interval
        if wait:
            time.sleep(wait)


_RATE_GATE = _RateGate()


class _CircuitBreakers:
    """Process-local source-host circuit; durable failures remain in run/event rows."""
    def __init__(self, *, threshold: int = 5, cooldown_seconds: int = 120):
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float]] = {}

    def remaining(self, host: str) -> int:
        with self._lock:
            count, opened_until = self._state.get(host, (0, 0.0))
            now = time.monotonic()
            if opened_until <= now:
                if opened_until:
                    self._state.pop(host, None)
                return 0
            return max(1, int(opened_until - now + 0.999))

    def temporary_failure(self, host: str) -> int:
        with self._lock:
            count, opened_until = self._state.get(host, (0, 0.0))
            now = time.monotonic()
            count = count + 1 if opened_until <= now else count
            if count >= self.threshold:
                opened_until = max(opened_until, now + self.cooldown_seconds)
            self._state[host] = (count, opened_until)
            return max(0, int(opened_until - now + 0.999))

    def success(self, host: str) -> None:
        with self._lock:
            self._state.pop(host, None)


def _retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            seconds = (target - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(1800, max(0, int(seconds + 0.999)))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection pinned to an address that was checked immediately before connect."""
    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip
        self.phase = "TCP_CONNECT"

    def connect(self):
        self.phase = "TCP_CONNECT"
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.phase = "TLS_HANDSHAKE"
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class SafeURLVerifier:
    """Bounded HTTPS GET verifier with exact host policy and DNS-pinned connections."""
    def __init__(self, *, timeout_seconds: float = 8.0, max_redirects: int = 4,
                 max_page_bytes: int = 2_000_000, request_interval_seconds: float = 0.75,
                 resolver=None):
        self.timeout_seconds = min(max(float(timeout_seconds), 1.0), 20.0)
        self.max_redirects = min(max(int(max_redirects), 0), 6)
        self.max_page_bytes = min(max(int(max_page_bytes), 4096), 4_000_000)
        self.request_interval_seconds = min(max(float(request_interval_seconds), 0.0), 5.0)
        self.resolver = resolver or socket.getaddrinfo
        self.circuits = _CircuitBreakers()

    @staticmethod
    def _host_allowed(host: str, allowed_hosts: tuple[str, ...] | list[str]) -> bool:
        host = host.rstrip(".").lower()
        return host in {allowed.rstrip(".").lower() for allowed in allowed_hosts}

    def _validate_and_pin(self, url: str, allowed_hosts: tuple[str, ...] | list[str]):
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").rstrip(".").lower()
            port = parts.port or 443
        except ValueError as exc:
            raise UnsafeDestination("MALFORMED_URL") from exc
        if (parts.scheme.lower() != "https" or not host or parts.username or parts.password
                or port != 443 or parts.fragment):
            raise UnsafeDestination("UNSAFE_URL_STRUCTURE")
        sensitive = {"access_token", "api_key", "apikey", "auth", "authorization", "client_secret",
                     "credential", "jwt", "key", "oauth_token", "secret", "session", "signature",
                     "sig", "token", "x-amz-credential", "x-amz-signature", "x-amz-security-token"}
        if any(key.casefold() in sensitive for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
            raise UnsafeDestination("SENSITIVE_URL_QUERY_REJECTED")
        if not self._host_allowed(host, allowed_hosts):
            raise UnsafeDestination("HOST_NOT_ALLOWLISTED")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
            raise UnsafeDestination("PRIVATE_HOSTNAME")
        try:
            address = ipaddress.ip_address(host)
            addresses = [address.compressed]
        except ValueError:
            try:
                records = self.resolver(host, 443, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise UnsafeDestination("DNS_RESOLUTION_FAILED") from exc
            addresses = list(dict.fromkeys(record[4][0] for record in records if record and record[4]))
        if not addresses:
            raise UnsafeDestination("DNS_NO_ADDRESSES")
        parsed_addresses = []
        for value in addresses:
            try:
                ip = ipaddress.ip_address(value.split("%", 1)[0])
            except ValueError as exc:
                raise UnsafeDestination("DNS_RETURNED_INVALID_ADDRESS") from exc
            if not ip.is_global:
                raise UnsafeDestination("DNS_RESOLVED_TO_NON_PUBLIC_ADDRESS")
            parsed_addresses.append(ip.compressed)
        # Validate every answer to prevent a mixed public/private DNS response. The
        # actual TCP socket is pinned to one of these validated addresses.
        return parts, host, parsed_addresses[0]

    @staticmethod
    def _listing_redirect(url: str) -> bool:
        path = urlsplit(url).path.casefold().rstrip("/")
        return path.endswith("/list-opportunities") or path == "/list-opportunities"

    @staticmethod
    def _login_redirect(url: str) -> bool:
        return any(token in urlsplit(url).path.casefold() for token in ("login", "signin", "account/sign"))

    @staticmethod
    def _payment_redirect(url: str) -> bool:
        path = urlsplit(url).path.casefold()
        return any(token in path for token in ("payment", "checkout", "purchase"))

    def verify(self, url: str, *, allowed_hosts: tuple[str, ...] | list[str],
               expected_kind: str = "DOCUMENT", expected_provider_id: str | None = None) -> PageCapture:
        current = url
        chain: list[str] = []
        body_limit = self.max_page_bytes if expected_kind == "PAGE" else 8192
        for redirect_count in range(self.max_redirects + 1):
            try:
                parts, host, pinned_ip = self._validate_and_pin(current, allowed_hosts)
            except UnsafeDestination as exc:
                if str(exc) in {"DNS_RESOLUTION_FAILED", "DNS_NO_ADDRESSES"}:
                    wait = self.circuits.temporary_failure((urlsplit(current).hostname or "").casefold())
                    return PageCapture(0, current, "", b"", chain, "TEMPORARY_FAILURE",
                                       {"error_class": str(exc), "retry_after_seconds": wait or None})
                return PageCapture(0, current, "", b"", chain, "UNSAFE_DESTINATION", {"reason": str(exc)})
            remaining = self.circuits.remaining(host)
            if remaining:
                return PageCapture(0, current, "", b"", chain, "CIRCUIT_OPEN",
                                   {"retry_after_seconds": remaining, "error_class": "SourceCircuitOpen"})
            _RATE_GATE.wait(host, self.request_interval_seconds)
            connection = _PinnedHTTPSConnection(host, parts.port or 443, pinned_ip, self.timeout_seconds)
            connection.phase = "HTTP_REQUEST"
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            try:
                connection.request("GET", path, headers={
                    "Host": host,
                    "User-Agent": "SharakatDocumentMetadataCollector/1.0 (+public read-only; no downloads stored)",
                    "Accept": "text/html,application/pdf,application/octet-stream;q=0.8,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                    "Range": "bytes=0-8191" if expected_kind == "DOCUMENT" else f"bytes=0-{body_limit - 1}",
                    "Connection": "close",
                })
                connection.phase = "HTTP_RESPONSE_HEADERS"
                response = connection.getresponse()
                status = response.status
                content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
                location = response.getheader("Location")
                retry_after = _retry_after_seconds(response.getheader("Retry-After"))
                if status in {301, 302, 303, 307, 308} and location:
                    destination = urljoin(current, location)
                    chain.append(destination)
                    response.read(1024)
                    connection.close()
                    if redirect_count >= self.max_redirects:
                        return PageCapture(status, current, content_type, b"", chain, "REDIRECT_LIMIT", {})
                    try:
                        self._validate_and_pin(destination, allowed_hosts)
                    except UnsafeDestination:
                        return PageCapture(status, destination, content_type, b"", chain, "UNSAFE_REDIRECT", {})
                    if self._listing_redirect(destination):
                        return PageCapture(status, destination, content_type, b"", chain, "LISTING_REDIRECT", {})
                    if self._login_redirect(destination):
                        return PageCapture(status, destination, content_type, b"", chain, "LOGIN_REDIRECT", {})
                    if self._payment_redirect(destination):
                        return PageCapture(status, destination, content_type, b"", chain, "PAYMENT_REDIRECT", {})
                    current = destination
                    continue
                if status in {401, 403}:
                    self.circuits.success(host)
                    return PageCapture(status, current, content_type, b"", chain, "AUTH_FAILURE", {})
                if status == 402:
                    self.circuits.success(host)
                    return PageCapture(status, current, content_type, b"", chain, "PAYMENT_REQUIRED", {})
                if status == 404 or status == 410:
                    self.circuits.success(host)
                    return PageCapture(status, current, content_type, b"", chain, "NOT_FOUND", {})
                if status == 429 or status == 408 or status >= 500:
                    wait = self.circuits.temporary_failure(host)
                    return PageCapture(status, current, content_type, b"", chain, "TEMPORARY_FAILURE",
                                       {"retry_after_seconds": retry_after or wait or None,
                                        "error_class": "HTTPRateLimited" if status == 429 else "HTTPTransientFailure"})
                if status not in {200, 206}:
                    self.circuits.success(host)
                    return PageCapture(status, current, content_type, b"", chain, "HTTP_FAILURE", {})
                connection.phase = "HTTP_RESPONSE_BODY"
                body = response.read(body_limit + 1)
                self.circuits.success(host)
                if len(body) > body_limit:
                    return PageCapture(status, current, content_type, body[:body_limit], chain, "RESPONSE_TOO_LARGE", {})
                connection.close()
                if self._listing_redirect(current):
                    return PageCapture(status, current, content_type, body, chain, "LISTING_REDIRECT", {})
                if self._login_redirect(current):
                    return PageCapture(status, current, content_type, body, chain, "LOGIN_REDIRECT", {})
                if self._payment_redirect(current):
                    return PageCapture(status, current, content_type, body, chain, "PAYMENT_REDIRECT", {})
                if expected_kind == "DOCUMENT":
                    if body.startswith(b"%PDF-"):
                        return PageCapture(status, current, content_type, body, chain, "CONFIRMED_DOCUMENT", {"signature": "%PDF-"})
                    if "text/html" in content_type or body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                        text = body.decode("utf-8", errors="replace")
                        if self._listing_redirect(current) or "list-opportunities" in text.casefold():
                            return PageCapture(status, current, content_type, body, chain, "LISTING_REDIRECT", {})
                        if self._login_redirect(current) or "تسجيل الدخول" in text or "sign in" in text.casefold():
                            return PageCapture(status, current, content_type, body, chain, "LOGIN_REDIRECT", {})
                    return PageCapture(status, current, content_type, body, chain, "INVALID_FILE_RESPONSE", {})
                text = body.decode("utf-8", errors="replace")
                parsed_provider = _provider_id_from_url(current)
                if (expected_provider_id and parsed_provider == expected_provider_id
                        and expected_provider_id in text):
                    return PageCapture(status, current, content_type, body, chain, "CONFIRMED_OFFICIAL_PAGE",
                                       {"provider_reference": expected_provider_id})
                return PageCapture(status, current, content_type, body, chain, "PAGE_IDENTITY_UNVERIFIED", {})
            except ssl.SSLCertVerificationError as exc:
                return PageCapture(0, current, "", b"", chain, "TLS_CERTIFICATE_INVALID",
                                   {"error_class": type(exc).__name__,
                                    "error_phase": getattr(connection, "phase", "TLS_HANDSHAKE")})
            except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException) as exc:
                wait = self.circuits.temporary_failure(host)
                return PageCapture(0, current, "", b"", chain, "TEMPORARY_FAILURE",
                                   {"error_class": type(exc).__name__,
                                    "error_phase": getattr(connection, "phase", "HTTP_REQUEST"),
                                    "retry_after_seconds": wait or None})
            finally:
                connection.close()
        return PageCapture(0, current, "", b"", chain, "REDIRECT_LIMIT", {})


def _provider_id_from_url(url: str) -> str | None:
    import re
    match = re.search(r"/opportunity/([^/?#]+)", urlsplit(url).path, re.I)
    return match.group(1) if match else None

