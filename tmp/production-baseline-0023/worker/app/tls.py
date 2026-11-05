"""Strict, source-scoped TLS trust configuration."""
from __future__ import annotations

import hashlib
import ssl
from pathlib import Path


_MWAN_INTERMEDIATE = Path(__file__).parent / "certificates" / "mwan-digicert-global-g2-tls-rsa-sha256-2020-ca1.pem"
_MWAN_INTERMEDIATE_SHA256 = "6601f41fceefbe7523a6a2e746938de57fc24e99426b7bea58d1867dbee1be5e"


def create_source_ssl_context(source_key: str) -> ssl.SSLContext:
    """Return normal strict TLS trust, with MWAN's verified missing issuer added only for MWAN.

    The official MWAN endpoints currently serve the leaf certificate without its
    DigiCert intermediate. The intermediate is obtained from the certificate's
    CA Issuers AIA and was verified to the system-trusted DigiCert Global Root G2.
    Pin the bundled PEM and use it as an additional, source-scoped trust anchor;
    certificate validation and hostname checking remain mandatory.
    """
    context = ssl.create_default_context()
    if source_key == "mwan":
        pem = _MWAN_INTERMEDIATE.read_bytes()
        if hashlib.sha256(pem).hexdigest() != _MWAN_INTERMEDIATE_SHA256:
            raise RuntimeError("Bundled MWAN issuer certificate fingerprint mismatch")
        context.load_verify_locations(cafile=str(_MWAN_INTERMEDIATE))
        partial_chain = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", None)
        if partial_chain is None:
            raise RuntimeError("OpenSSL does not support source-scoped partial-chain validation")
        context.verify_flags |= partial_chain
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context
