"""Server-Side Request Forgery (SSRF) protection.

TestPilot sends HTTP requests to URLs chosen by its users, so an attacker could try to
make *our server* call internal services (databases, admin panels, cloud metadata at
169.254.169.254 ...). Defences implemented here:

1. Only http/https schemes.
2. No credentials embedded in the URL (``http://user:pass@host``).
3. The hostname is resolved *by us* and EVERY resulting IP must be globally routable
   (this rejects loopback, RFC1918 private ranges, link-local/metadata, CGNAT,
   multicast, reserved, unspecified, IPv4-mapped IPv6 tricks and NAT64 embeddings).
4. The request is sent to the IP we validated (pinned), not re-resolved by the HTTP
   library, which closes the DNS-rebinding window between "check" and "use".
5. Every redirect hop is validated again (done by the engine, using this module).

Hosts listed in TESTPILOT_SSRF_ALLOWED_HOSTS are exempt from step 3 (for local demos).
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata", "instance-data"}
BLOCKED_SUFFIXES = (".localhost", ".internal", ".local", ".localdomain")
NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")

Resolver = Callable[[str, int], list[str]]


class SSRFError(Exception):
    """The target is not allowed."""


class InvalidURLError(Exception):
    """The URL is malformed or unsupported."""


@dataclass(frozen=True)
class SafeTarget:
    url: str
    scheme: str
    host: str
    port: int
    ip: str
    request_uri: str  # path + query

    @property
    def host_header(self) -> str:
        default = 443 if self.scheme == "https" else 80
        return self.host if self.port == default else f"{self.host}:{self.port}"

    @property
    def pinned_url(self) -> str:
        ip = f"[{self.ip}]" if ":" in self.ip else self.ip
        return f"{self.scheme}://{ip}:{self.port}{self.request_uri}"


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


def assert_public_ip(raw_ip: str) -> None:
    ip = ipaddress.ip_address(raw_ip.split("%")[0])  # strip IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in NAT64_PREFIX:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if not ip.is_global or ip.is_multicast:
        raise SSRFError(f"Target resolves to a non-public address ({ip}); request blocked")


def validate_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    resolver: Resolver | None = None,
) -> SafeTarget:
    allowed_hosts = allowed_hosts or set()
    resolver = resolver or default_resolver

    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise InvalidURLError(f"Malformed URL: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidURLError(f"Unsupported URL scheme '{scheme or '(none)'}'; only http and https are allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise InvalidURLError("URL has no hostname")
    if parts.username or parts.password:
        raise SSRFError("Credentials inside the URL are not allowed")

    port = port or (443 if scheme == "https" else 80)
    allowed = host in allowed_hosts

    if not allowed and (host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES)):
        raise SSRFError(f"Hostname '{host}' is not allowed")

    try:
        ips = resolver(host, port)
    except socket.gaierror as exc:
        raise InvalidURLError(f"Could not resolve hostname '{host}'") from exc
    if not ips:
        raise InvalidURLError(f"Could not resolve hostname '{host}'")

    if not allowed:
        for ip in ips:  # ALL answers must be public, so mixed records cannot sneak through
            assert_public_ip(ip)

    request_uri = parts.path or "/"
    if parts.query:
        request_uri += "?" + parts.query
    return SafeTarget(url=url, scheme=scheme, host=host, port=port, ip=ips[0], request_uri=request_uri)
