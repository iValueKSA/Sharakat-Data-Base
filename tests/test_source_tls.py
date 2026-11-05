from urllib.parse import urlparse

import ssl

from app.adapters import MwanAdapter
from app.tls import create_source_ssl_context


def test_mwan_context_keeps_strict_tls_and_loads_only_pinned_source_issuer():
    context = create_source_ssl_context("mwan")
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
    assert len(context.get_ca_certs()) > len(ssl.create_default_context().get_ca_certs())


def test_non_mwan_sources_keep_the_default_strict_trust_configuration():
    context = create_source_ssl_context("ncp")
    default = ssl.create_default_context()
    assert context.verify_mode == default.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is default.check_hostname is True
    assert context.verify_flags == default.verify_flags
    assert len(context.get_ca_certs()) == len(default.get_ca_certs())


def test_mwan_configured_endpoints_remain_official_https_hosts():
    adapter = MwanAdapter()
    listing = urlparse(adapter.url)
    portal = urlparse(adapter.portal_url)
    assert (listing.scheme, listing.hostname, listing.path) == (
        "https", "mwan.gov.sa", "/en/investment-opportunities"
    )
    assert (portal.scheme, portal.hostname, portal.path) == (
        "https", "mwared.mwan.gov.sa", "/en/investor/opportunities/cards"
    )
