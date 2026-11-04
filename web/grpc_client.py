"""gRPC helpers for the web BFF (mirrors luckystonks.client.cli cluster behavior)."""

from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from typing import Any

import grpc

from luckystonks.pb import llm_pb2, llm_pb2_grpc, trading_pb2, trading_pb2_grpc


@dataclass
class Session:
    token: str
    user_id: str
    role: str


def connect_trading(host: str, port: int) -> trading_pb2_grpc.TradingStub:
    channel = grpc.insecure_channel(f"{host}:{port}")
    return trading_pb2_grpc.TradingStub(channel)


def connect_insight(host: str, port: int) -> llm_pb2_grpc.InsightStub:
    channel = grpc.insecure_channel(f"{host}:{port}")
    return llm_pb2_grpc.InsightStub(channel)


def probe_port_listening(host: str, port: int, timeout: float = 0.15) -> bool:
    """Fast TCP connect check — used by Ops so DOWN peers don't stall the UI (~0.8s gRPC probes)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_trading_port(host: str, port: int, timeout: float = 0.8) -> bool:
    """gRPC channel readiness (login/routing). Prefer probe_port_listening for Ops polling."""
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=timeout)
        return True
    except Exception:
        return False


def login(stub: Any, username: str, password: str) -> Session:
    reply = stub.Login(
        trading_pb2.LoginRequest(username=username, password=password), timeout=5
    )
    if reply.status != "OK":
        raise ValueError("invalid username or password")
    return Session(token=reply.token, user_id=username, role=reply.role or "user")


def logout(stub: Any, token: str) -> None:
    stub.Logout(trading_pb2.LogoutRequest(token=token), timeout=5)


def parse_not_leader_trading(detail: str) -> tuple[str, int] | None:
    if not detail.startswith("NOT_LEADER;trading="):
        return None
    addr = detail.split("=", 1)[1].strip()
    if addr == "unknown" or ":" not in addr:
        return None
    host, port_s = addr.rsplit(":", 1)
    return host, int(port_s)


def order_payload(side: str, symbol: str, price: int, qty: int) -> bytes:
    return json.dumps(
        {
            "client_request_id": str(uuid.uuid4()),
            "side": side.upper(),
            "symbol": symbol.upper(),
            "price": price,
            "qty": qty,
        }
    ).encode("utf-8")


def _post_on_stub(
    stub: Any,
    token: str,
    post_type: str,
    data: bytes,
    username: str,
    password: str,
    leader_port: int,
) -> dict[str, Any]:
    reply = stub.Post(
        trading_pb2.PostRequest(token=token, type=post_type, data=data), timeout=8
    )
    if reply.status != "ERR":
        return {
            "status": reply.status,
            "detail": reply.detail,
            "leader_port": leader_port,
            "leader_peer": _port_to_peer(leader_port),
        }
    target = parse_not_leader_trading(reply.detail or "")
    if target is None:
        raise ValueError(reply.detail)
    lh, lp = target
    if lp == leader_port:
        raise ValueError(reply.detail)
    leader_stub = connect_trading(lh, lp)
    session = login(leader_stub, username, password)
    retry = leader_stub.Post(
        trading_pb2.PostRequest(token=session.token, type=post_type, data=data), timeout=8
    )
    if retry.status == "ERR":
        raise ValueError(retry.detail)
    return {
        "status": retry.status,
        "detail": retry.detail,
        "leader_port": lp,
        "leader_peer": _port_to_peer(lp),
    }


def post_cluster(
    stub: Any,
    token: str,
    post_type: str,
    data: bytes,
    *,
    connected_host: str,
    connected_port: int,
    username: str,
    password: str,
    leader_port_hint: int | None = None,
) -> dict[str, Any]:
    reply = stub.Post(
        trading_pb2.PostRequest(token=token, type=post_type, data=data), timeout=8
    )
    if reply.status != "ERR":
        return {
            "status": reply.status,
            "detail": reply.detail,
            "routed_to_leader": False,
            "connected_port": connected_port,
            "leader_port": connected_port,
        }

    detail = reply.detail or ""
    target = parse_not_leader_trading(detail)
    if target is not None:
        lh, lp = target
        if lp != connected_port:
            leader_stub = connect_trading(lh, lp)
            session = login(leader_stub, username, password)
            result = _post_on_stub(
                leader_stub, session.token, post_type, data, username, password, lp
            )
            return {
                **result,
                "routed_to_leader": True,
                "connected_port": connected_port,
            }

    from luckystonks.cluster_size import BASE_TRADING_PORT, peer_ids

    ports_to_try: list[int] = []
    if leader_port_hint is not None and leader_port_hint != connected_port:
        ports_to_try.append(leader_port_hint)
    for pid in peer_ids():
        p = BASE_TRADING_PORT + pid
        if p != connected_port and p not in ports_to_try:
            ports_to_try.append(p)

    last_err = detail or "no leader available; cluster may be electing"
    for port in ports_to_try:
        if not probe_trading_port(connected_host, port):
            continue
        try:
            leader_stub = connect_trading(connected_host, port)
            session = login(leader_stub, username, password)
            result = _post_on_stub(
                leader_stub, session.token, post_type, data, username, password, port
            )
            return {
                **result,
                "routed_to_leader": True,
                "connected_port": connected_port,
            }
        except (ValueError, grpc.RpcError) as err:
            last_err = str(err)
            continue

    raise ValueError(last_err)


def post_order_cluster(
    stub: Any,
    token: str,
    data: bytes,
    *,
    connected_host: str,
    connected_port: int,
    username: str,
    password: str,
    leader_port_hint: int | None = None,
) -> dict[str, Any]:
    return post_cluster(
        stub,
        token,
        "ORDER",
        data,
        connected_host=connected_host,
        connected_port=connected_port,
        username=username,
        password=password,
        leader_port_hint=leader_port_hint,
    )


def _port_to_peer(port: int) -> int | None:
    from luckystonks.cluster_size import BASE_TRADING_PORT, cluster_size

    if BASE_TRADING_PORT <= port < BASE_TRADING_PORT + cluster_size():
        return port - BASE_TRADING_PORT
    return None


def get_data(stub: Any, token: str, get_type: str, params: str = "") -> list[dict[str, Any]]:
    reply = stub.Get(
        trading_pb2.GetRequest(token=token, type=get_type, params=params), timeout=5
    )
    if reply.status != "OK":
        raise ValueError(f"get {get_type} failed")
    return [json.loads(item.data.decode("utf-8")) for item in reply.items]


def _parse_get_items(reply: Any) -> list[dict[str, Any]] | None:
    if reply.status != "OK":
        return None
    return [json.loads(item.data.decode("utf-8")) for item in reply.items]


def get_data_resilient(
    *,
    host: str,
    port: int,
    token: str,
    username: str,
    password: str,
    get_type: str,
    params: str = "",
    leader_port_hint: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch trading Get data, refreshing the session if the peer was restarted.

    Login tokens are in-memory per peer. After Ops Stop/Start of the client peer,
    the BFF cookie is still valid but the gRPC token is not. Re-login (same as
    order routing) and return session field updates for the caller to apply.
    """
    from luckystonks.cluster_size import BASE_TRADING_PORT, cluster_size

    # Prefer the leader so Trade reads match the peer that accepts/rejects orders.
    # A restarted follower can briefly (or chronically) serve a divergent book.
    ports: list[int] = []
    for candidate in (leader_port_hint, port, *[BASE_TRADING_PORT + i for i in range(cluster_size())]):
        if candidate is None:
            continue
        p = int(candidate)
        if p not in ports:
            ports.append(p)

    # Fast path: existing token only when the preferred peer is the session peer.
    preferred = ports[0] if ports else port
    if preferred == port and probe_port_listening(host, port):
        try:
            stub = connect_trading(host, port)
            reply = stub.Get(
                trading_pb2.GetRequest(token=token, type=get_type, params=params), timeout=5
            )
            parsed = _parse_get_items(reply)
            if parsed is not None:
                return parsed, {}
        except grpc.RpcError:
            pass

    last_err = f"get {get_type} failed (no reachable peer with a valid session)"
    for p in ports:
        if not probe_port_listening(host, p):
            continue
        try:
            stub = connect_trading(host, p)
            session = login(stub, username, password)
            reply = stub.Get(
                trading_pb2.GetRequest(token=session.token, type=get_type, params=params),
                timeout=5,
            )
            parsed = _parse_get_items(reply)
            if parsed is None:
                last_err = f"get {get_type} failed on :{p}"
                continue
            return parsed, {
                "token": session.token,
                "port": p,
                "host": host,
                "user_id": session.user_id,
                "role": session.role,
            }
        except (ValueError, grpc.RpcError) as err:
            last_err = str(err)
            continue
    raise ValueError(last_err)


def get_insight(stub: Any, query: str, context: str = "") -> str:
    reply = stub.GetInsight(
        llm_pb2.GetInsightRequest(
            request_id=str(uuid.uuid4()),
            query=query,
            context=context,
        ),
        timeout=30,
    )
    return reply.answer
