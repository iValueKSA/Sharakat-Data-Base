"""Local HTTP(S) calls from the runtime to its own API (health checks, verify)."""
from __future__ import annotations

import ssl
import urllib.request

from .config import Settings


def local_open(settings: Settings, path: str, timeout: float = 10):
    """Open settings.local_url + path. With TLS the request goes to 127.0.0.1,
    which the certificate doesn't name, so this one loopback health call skips
    certificate verification. Users' browsers still verify the real hostname."""
    url = settings.local_url + path
    context = None
    if url.startswith("https://"):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(url, timeout=timeout, context=context)
