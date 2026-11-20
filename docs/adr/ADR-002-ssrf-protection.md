# ADR-002: SSRF protection design
**Status:** Accepted
**Context:** Users choose URLs the server fetches. Without controls, that reaches cloud metadata, localhost and private networks.
**Decision:** Validate scheme (http/https), reject URL credentials, resolve the hostname, require every resolved IP to be `is_global` (unwrap IPv4-mapped IPv6 and NAT64), block known internal hostnames/suffixes, connect to the vetted IP (Host header and TLS SNI preserved) to defeat DNS rebinding, re-validate each redirect hop, disable `trust_env`. An explicit allow-list exists for demos only.
**Consequences:** Legitimate internal targets are blocked unless allow-listed. Cost of an extra DNS resolution per request.
**Alternatives:** Egress firewall only (recommended in addition, not instead).
