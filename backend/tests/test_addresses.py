import pytest

from app.addresses import AddressError, is_loopback_ip, parse_address, resolve_all, validate_host, validate_port


@pytest.mark.parametrize("text,host,port", [
    ("localhost:8443", "localhost", 8443), ("Example.COM:443", "example.com", 443),
    ("127.0.0.1:1", "127.0.0.1", 1), ("[::1]:65535", "::1", 65535), ("a-b.example:8443", "a-b.example", 8443),
])
def test_good_addresses(text, host, port):
    hp = parse_address(text)
    assert (hp.host, hp.port) == (host, port)


@pytest.mark.parametrize("text", [
    "-connect:443", "a b:443", "x;rm:443", "../:443", "..:443", "localhost", "localhost:", ":443", "localhost:0",
    "localhost:65536", "localhost:99999", "localhost:-1", "localhost:44a", "localhost:443/path", "https://localhost:443",
    "host name:443", "host\n:443", "host:443\n", "$(id):443", "`id`:443", "a|b:443", "a&b:443", "-h:1", "a..b:443",
    ".a:443", "a-:443", "999.1.1.1:443", "1.2.3:443", "::1:443", "[::1]", "[zz]:443", "a" * 300 + ":443", "", " ",
    "user@host:443", "host:443:443", "ho\x00st:443", "hóst:443",
])
def test_hostile_or_malformed_addresses_are_rejected(text):
    with pytest.raises(AddressError):
        parse_address(text)


@pytest.mark.parametrize("host", ["-connect", "a b", "x;rm", "../", "", "a_b", "a/b", "*", "a,b"])
def test_hostile_hosts_are_rejected(host):
    with pytest.raises(AddressError):
        validate_host(host)


@pytest.mark.parametrize("port", [0, 65536, -1, "0", "abc", "", "44 3", None, 4.5, True, "１２３"])
def test_bad_ports(port):
    with pytest.raises(AddressError):
        validate_port(port)


def test_loopback_means_127_slash_8_or_colon_colon_1_only():
    assert is_loopback_ip("127.0.0.1") and is_loopback_ip("127.255.255.254") and is_loopback_ip("::1")
    for ip in ("10.0.0.1", "0.0.0.0", "128.0.0.1", "::", "::ffff:127.0.0.1", "169.254.1.1", "not-an-ip"):
        assert not is_loopback_ip(ip)


def test_ip_literals_resolve_to_themselves_and_localhost_is_loopback():
    assert resolve_all("127.0.0.1") == ["127.0.0.1"]
    assert all(is_loopback_ip(ip) for ip in resolve_all("localhost"))
