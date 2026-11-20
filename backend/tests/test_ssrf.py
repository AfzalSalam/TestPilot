"""SSRF guard. Protects against: calling internal services, cloud metadata, DNS rebinding tricks."""

import pytest

from app.services.ssrf import InvalidURLError, SSRFError, validate_url


def fake_resolver(mapping):
    return lambda host, port: mapping[host]


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.10", "169.254.169.254", "100.64.0.1",
        "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.1.2.3",
        "64:ff9b::7f00:1",
    ],
)  # fmt: skip
def test_non_public_addresses_are_blocked(ip):
    with pytest.raises(SSRFError):
        validate_url("http://target.test/", resolver=fake_resolver({"target.test": [ip]}))


def test_public_address_is_allowed_and_pinned():
    target = validate_url("https://api.example.com/v1/x?a=1", resolver=fake_resolver({"api.example.com": ["93.184.216.34"]}))
    assert target.ip == "93.184.216.34"
    assert target.pinned_url == "https://93.184.216.34:443/v1/x?a=1"
    assert target.host_header == "api.example.com"


def test_one_private_record_among_public_ones_blocks_the_request():
    """DNS answers are attacker-controlled; a mixed answer must not slip through."""
    with pytest.raises(SSRFError):
        validate_url("http://rebind.test/", resolver=fake_resolver({"rebind.test": ["93.184.216.34", "127.0.0.1"]}))


@pytest.mark.parametrize("url", ["http://localhost/", "http://LOCALHOST./", "http://metadata.google.internal/", "http://db.internal/", "http://x.localhost/"])
def test_blocked_hostnames(url):
    with pytest.raises(SSRFError):
        validate_url(url, resolver=lambda h, p: ["93.184.216.34"])


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f.0.0.1/", "http://017700000001/"])
def test_obfuscated_loopback_forms_are_blocked_after_resolution(url):
    import ipaddress  # a resolver that mimics inet_aton behaviour

    def resolver(host, port):
        return ["127.0.0.1"]

    with pytest.raises(SSRFError):
        validate_url(url, resolver=resolver)
    assert ipaddress.ip_address("127.0.0.1").is_loopback


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://x/", "javascript:alert(1)", "//example.com"])
def test_unsafe_schemes_rejected(url):
    with pytest.raises(InvalidURLError):
        validate_url(url, resolver=lambda h, p: ["93.184.216.34"])


def test_credentials_in_url_rejected():
    with pytest.raises(SSRFError):
        validate_url("http://user:pw@example.com/", resolver=lambda h, p: ["93.184.216.34"])


def test_allowlisted_host_bypasses_private_check():
    target = validate_url("http://demo-api:9000/x", allowed_hosts={"demo-api"}, resolver=lambda h, p: ["10.0.0.9"])
    assert target.ip == "10.0.0.9"


def test_unresolvable_host_is_invalid_url():
    import socket

    def boom(host, port):
        raise socket.gaierror("nope")

    with pytest.raises(InvalidURLError):
        validate_url("http://no-such-host.test/", resolver=boom)
