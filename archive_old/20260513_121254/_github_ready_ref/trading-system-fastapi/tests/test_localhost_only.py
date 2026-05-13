from app.middleware.localhost_only import _is_allowed_host


def test_localhost_hosts_allowed() -> None:
    assert _is_allowed_host("127.0.0.1") is True
    assert _is_allowed_host("::1") is True
    assert _is_allowed_host("testclient") is True
    assert _is_allowed_host("192.168.1.10") is False
