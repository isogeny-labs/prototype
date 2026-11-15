"""Address safety: strict host:port parsing, one-time name resolution, loopback check.

Nothing here opens a connection to the address being checked.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME_RE = re.compile(rf"{_LABEL}(?:\.{_LABEL})*")
_ADDRESS_RE = re.compile(r"(?P<host>\[[0-9A-Fa-f:.]+\]|[^\[\]:\s]+):(?P<port>[0-9]{1,5})")


class AddressError(ValueError):
    """The text is not a host:port we are willing to connect to."""


@dataclass(frozen=True)
class HostPort:
    host: str
    port: int

    @property
    def address(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    @property
    def is_ip(self) -> bool:
        try:
            ipaddress.ip_address(self.host)
            return True
        except ValueError:
            return False


def validate_host(host: str) -> str:
    if not isinstance(host, str) or not host or len(host) > 253:
        raise AddressError("The host name is missing or too long")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if host.startswith("-") or not _HOSTNAME_RE.fullmatch(host):
        raise AddressError(
            f"{host!r} is not a valid host name (letters, digits, dots and hyphens only) or IP address"
        )
    if re.fullmatch(r"[0-9.]+", host):
        raise AddressError(f"{host!r} is not a valid IP address")
    return host.lower()


def validate_port(port: object) -> int:
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        raise AddressError("The port must be a whole number from 1 to 65535")
    if isinstance(port, str):
        if not re.fullmatch(r"[0-9]{1,5}", port):
            raise AddressError(f"The port {port!r} must be a whole number from 1 to 65535")
        port = int(port)
    if not 1 <= port <= 65535:
        raise AddressError(f"The port {port} must be a whole number from 1 to 65535")
    return port


def parse_address(text: str) -> HostPort:
    """Parse 'host:port' (or '[ipv6]:port'). Raises AddressError for anything else."""
    if not isinstance(text, str) or len(text) > 300:
        raise AddressError("The address must look like host:port, for example localhost:8443")
    m = _ADDRESS_RE.fullmatch(text)
    if not m:
        raise AddressError(f"{text!r} is not an address like host:port (for example localhost:8443)")
    host = m.group("host")
    if host.startswith("["):
        host = host[1:-1]
    return HostPort(validate_host(host), validate_port(m.group("port")))


def is_loopback_ip(ip: str) -> bool:
    """Loopback means 127.0.0.0/8 or ::1 only."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv4Address):
        return addr in ipaddress.ip_network("127.0.0.0/8")
    return addr == ipaddress.ip_address("::1")


def resolve_all(host: str) -> list[str]:
    """Every IP the name currently points to (IPv4 first). An IP literal resolves to itself."""
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise AddressError(f"The name {host} could not be looked up ({exc.__class__.__name__})") from exc
    v4 = [i[4][0] for i in infos if i[0] == socket.AF_INET]
    v6 = [i[4][0] for i in infos if i[0] == socket.AF_INET6]
    ips = list(dict.fromkeys(v4 + v6))
    if not ips:
        raise AddressError(f"The name {host} did not resolve to an IP address")
    return ips


def resolve_one(host: str) -> str:
    return resolve_all(host)[0]
