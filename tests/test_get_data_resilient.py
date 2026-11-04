"""BFF Get reads must survive peer restart by refreshing the trading token."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from web.grpc_client import get_data_resilient


def _ok_reply(items: list[dict] | None = None):
    import json

    raw = items if items is not None else [{"cash": 1}]
    return SimpleNamespace(
        status="OK",
        items=[SimpleNamespace(data=json.dumps(row).encode("utf-8")) for row in raw],
    )


def test_get_data_resilient_uses_existing_token_when_valid():
    stub = MagicMock()
    stub.Get.return_value = _ok_reply([{"ok": True}])

    with (
        patch("web.grpc_client.probe_port_listening", return_value=True),
        patch("web.grpc_client.connect_trading", return_value=stub),
        patch("web.grpc_client.login") as login_mock,
    ):
        data, updates = get_data_resilient(
            host="127.0.0.1",
            port=50052,
            token="live-token",
            username="pratham",
            password="pratham",
            get_type="PORTFOLIO",
        )

    assert data == [{"ok": True}]
    assert updates == {}
    login_mock.assert_not_called()


def test_get_data_resilient_relogins_after_stale_token():
    stub = MagicMock()
    stub.Get.side_effect = [
        SimpleNamespace(status="ERR", items=[]),  # stale token
        _ok_reply([{"cash": 42}]),  # after re-login
    ]
    session = SimpleNamespace(token="fresh-token", user_id="pratham", role="user")

    with (
        patch("web.grpc_client.probe_port_listening", return_value=True),
        patch("web.grpc_client.connect_trading", return_value=stub),
        patch("web.grpc_client.login", return_value=session) as login_mock,
        patch("luckystonks.cluster_size.cluster_size", return_value=5),
    ):
        data, updates = get_data_resilient(
            host="127.0.0.1",
            port=50052,
            token="stale-token",
            username="pratham",
            password="pratham",
            get_type="PORTFOLIO",
        )

    assert data == [{"cash": 42}]
    assert updates["token"] == "fresh-token"
    assert updates["port"] == 50052
    login_mock.assert_called()


def test_get_data_resilient_raises_when_no_peer_up():
    with patch("web.grpc_client.probe_port_listening", return_value=False):
        with patch("luckystonks.cluster_size.cluster_size", return_value=3):
            with pytest.raises(ValueError, match="get PORTFOLIO failed"):
                get_data_resilient(
                    host="127.0.0.1",
                    port=50052,
                    token="x",
                    username="pratham",
                    password="pratham",
                    get_type="PORTFOLIO",
                )


def test_get_data_resilient_prefers_leader_port_hint():
    """Reads should hit the leader first so a stale follower book is not shown."""
    stub = MagicMock()
    stub.Get.return_value = _ok_reply([{"from": "leader"}])
    session = SimpleNamespace(token="leader-token", user_id="pratham", role="user")
    connected = []

    def connect(host, port):
        connected.append(port)
        return stub

    with (
        patch("web.grpc_client.probe_port_listening", return_value=True),
        patch("web.grpc_client.connect_trading", side_effect=connect),
        patch("web.grpc_client.login", return_value=session),
        patch("luckystonks.cluster_size.cluster_size", return_value=5),
    ):
        data, updates = get_data_resilient(
            host="127.0.0.1",
            port=50052,
            token="follower-token",
            username="pratham",
            password="pratham",
            get_type="ORDERS",
            leader_port_hint=50054,
        )

    assert data == [{"from": "leader"}]
    assert connected[0] == 50054
    assert updates["port"] == 50054
    assert updates["token"] == "leader-token"
