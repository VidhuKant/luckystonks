"""LuckyStonks Bloomberg-style web: trading BFF + ops control plane."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from web.grpc_client import (  # noqa: E402
    connect_insight,
    connect_trading,
    get_data,
    get_insight,
    login,
    logout,
    order_payload,
    post_cluster,
    post_order_cluster,
    probe_trading_port,
)
from web.ops_state import (  # noqa: E402
    build_cluster_status,
    classify_log_line,
    default_peers,
    infer_leader_from_logs,
    tail_log_file,
)

WEB_ROOT = Path(__file__).resolve().parent
STATIC_DIR = WEB_ROOT / "static"
RUNTIME = _ROOT / "data" / "runtime" / "demo-ui"
LOG_DIR = RUNTIME / "logs"
PID_FILE = RUNTIME / "pids.json"

HOST = os.getenv("UI_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("UI_WEB_PORT", "8765"))
TRADING_HOST = os.getenv("UI_TRADING_HOST", "127.0.0.1")
TRADING_PORT = int(os.getenv("UI_CLIENT_TRADING_PORT", "50052"))
INSIGHT_HOST = os.getenv("UI_INSIGHT_HOST", "127.0.0.1")
INSIGHT_PORT = int(os.getenv("UI_INSIGHT_PORT", "50070"))

app = FastAPI(title="LuckyStonks Terminal")
_sessions: dict[str, dict[str, Any]] = {}


def _session_token(request: Request) -> str | None:
    return request.cookies.get("ls_session")


def _require_session(request: Request) -> dict[str, Any]:
    sid = _session_token(request)
    if not sid or sid not in _sessions:
        raise HTTPException(status_code=401, detail="not authenticated")
    return _sessions[sid]


def _require_admin(request: Request) -> dict[str, Any]:
    sess = _require_session(request)
    if sess.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return sess


def _leader_port_hint() -> int | None:
    alive = {
        p["peer_id"]
        for p in default_peers(TRADING_HOST)
        if probe_trading_port(TRADING_HOST, p["trading_port"])
    }
    leader_id = infer_leader_from_logs(LOG_DIR, [0, 1, 2], alive_peer_ids=alive or None)
    return (50051 + leader_id) if leader_id is not None else None


def _stub_for_session(sess: dict[str, Any]):
    return connect_trading(sess["host"], sess["port"])


def _probe_raft(host: str, port: int) -> bool:
    return probe_trading_port(host, port)


class LoginBody(BaseModel):
    username: str
    password: str


class OrderBody(BaseModel):
    side: str
    symbol: str
    price: int = Field(gt=0)
    qty: int = Field(gt=0)


class InsightBody(BaseModel):
    query: str


class ClusterChangeBody(BaseModel):
    action: str = Field(pattern="^(add|remove)$")
    peer_id: int = Field(ge=0, le=99)
    raft_addr: str = ""
    trading_addr: str = ""


@app.post("/api/auth/login")
def api_login(body: LoginBody) -> JSONResponse:
    stub = connect_trading(TRADING_HOST, TRADING_PORT)
    try:
        session = login(stub, body.username.strip(), body.password)
    except ValueError as err:
        raise HTTPException(status_code=401, detail=str(err)) from err
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = {
        "token": session.token,
        "user_id": session.user_id,
        "role": session.role,
        "username": body.username.strip(),
        "password": body.password,
        "host": TRADING_HOST,
        "port": TRADING_PORT,
    }
    out = {
        "user_id": session.user_id,
        "role": session.role,
        "connected_peer": TRADING_PORT - 50051,
        "connected_port": TRADING_PORT,
    }
    resp = JSONResponse(out)
    resp.set_cookie("ls_session", sid, httponly=True, samesite="lax", max_age=86400)
    return resp


@app.post("/api/auth/logout")
def api_logout(request: Request) -> JSONResponse:
    sid = _session_token(request)
    if sid and sid in _sessions:
        sess = _sessions.pop(sid)
        try:
            logout(_stub_for_session(sess), sess["token"])
        except Exception:
            pass
    resp = JSONResponse({"status": "OK"})
    resp.delete_cookie("ls_session")
    return resp


@app.get("/api/auth/me")
def api_me(request: Request) -> dict[str, Any]:
    sess = _require_session(request)
    return {
        "user_id": sess["user_id"],
        "role": sess["role"],
        "connected_peer": sess["port"] - 50051,
        "connected_port": sess["port"],
    }


@app.get("/api/trade/portfolio")
def api_portfolio(request: Request) -> Any:
    sess = _require_session(request)
    return get_data(_stub_for_session(sess), sess["token"], "PORTFOLIO")


@app.get("/api/trade/orders")
def api_orders(request: Request) -> Any:
    sess = _require_session(request)
    return get_data(_stub_for_session(sess), sess["token"], "ORDERS")


@app.get("/api/trade/trades")
def api_trades(request: Request) -> Any:
    sess = _require_session(request)
    return get_data(_stub_for_session(sess), sess["token"], "TRADES")


@app.get("/api/trade/book")
def api_book(request: Request, symbol: str = "") -> Any:
    sess = _require_session(request)
    return get_data(_stub_for_session(sess), sess["token"], "BOOK", symbol.strip().upper())


@app.post("/api/trade/order")
def api_order(body: OrderBody, request: Request) -> dict[str, Any]:
    sess = _require_session(request)
    stub = _stub_for_session(sess)
    data = order_payload(body.side, body.symbol, body.price, body.qty)
    leader_hint = _leader_port_hint()
    try:
        result = post_order_cluster(
            stub,
            sess["token"],
            data,
            connected_host=sess["host"],
            connected_port=sess["port"],
            username=sess["username"],
            password=sess["password"],
            leader_port_hint=leader_hint,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return result


@app.post("/api/trade/insight")
def api_insight(body: InsightBody, request: Request) -> dict[str, str]:
    _require_session(request)
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    try:
        stub = connect_insight(INSIGHT_HOST, INSIGHT_PORT)
        answer = get_insight(stub, query)
    except Exception as err:
        raise HTTPException(status_code=503, detail=f"insight unavailable: {err}") from err
    return {"answer": answer}


@app.get("/api/admin/portfolios")
def api_admin_portfolios(request: Request) -> Any:
    sess = _require_admin(request)
    return get_data(_stub_for_session(sess), sess["token"], "ADMIN_PORTFOLIOS")


@app.get("/api/admin/order-log")
def api_admin_order_log(request: Request) -> Any:
    sess = _require_admin(request)
    return get_data(_stub_for_session(sess), sess["token"], "ORDER_LOG")


@app.post("/api/admin/reset")
def api_admin_reset(request: Request, response: Response) -> dict[str, Any]:
    sess = _require_admin(request)
    sid = _session_token(request)
    try:
        result = post_cluster(
            _stub_for_session(sess),
            sess["token"],
            "ADMIN_RESET",
            b"{}",
            connected_host=sess["host"],
            connected_port=sess["port"],
            username=sess["username"],
            password=sess["password"],
            leader_port_hint=_leader_port_hint(),
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if sid and sid in _sessions:
        del _sessions[sid]
    response.delete_cookie("ls_session")
    return result


@app.post("/api/admin/cluster-change")
def api_admin_cluster_change(body: ClusterChangeBody, request: Request) -> dict[str, Any]:
    sess = _require_admin(request)
    payload = json.dumps(
        {
            "action": body.action,
            "peer_id": body.peer_id,
            "raft_addr": body.raft_addr.strip(),
            "trading_addr": body.trading_addr.strip(),
        }
    ).encode("utf-8")
    try:
        return post_cluster(
            _stub_for_session(sess),
            sess["token"],
            "CLUSTER_CHANGE",
            payload,
            connected_host=sess["host"],
            connected_port=sess["port"],
            username=sess["username"],
            password=sess["password"],
            leader_port_hint=_leader_port_hint(),
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/api/ops/cluster")
def api_ops_cluster() -> dict[str, Any]:
    return build_cluster_status(
        root=_ROOT,
        log_dir=LOG_DIR,
        pid_file=PID_FILE,
        host=TRADING_HOST,
        probe_trading=probe_trading_port,
        probe_raft=_probe_raft,
    )


@app.get("/api/ops/logs/{peer_id}")
def api_ops_logs(peer_id: int, lines: int = 300) -> dict[str, Any]:
    path = LOG_DIR / f"peer{peer_id}.log"
    return {"peer_id": peer_id, "entries": tail_log_file(path, max_lines=min(lines, 800))}


@app.get("/api/ops/parity")
def api_ops_parity() -> dict[str, Any]:
    admin_user = os.getenv("UI_ADMIN_USER", "admin")
    admin_pass = os.getenv("UI_ADMIN_PASS", "admin")
    tapes: dict[str, Any] = {}
    ok = True
    ref = None
    for p in default_peers(TRADING_HOST):
        port = p["trading_port"]
        if not probe_trading_port(TRADING_HOST, port):
            tapes[str(port)] = {"status": "DOWN"}
            ok = False
            continue
        try:
            stub = connect_trading(TRADING_HOST, port)
            sess = login(stub, admin_user, admin_pass)
            data = get_data(stub, sess.token, "TRADES")
            payload = json.dumps(data, sort_keys=True)
            tapes[str(port)] = {"status": "OK", "count": len(data)}
            if ref is None:
                ref = payload
            elif payload != ref:
                ok = False
                tapes[str(port)]["status"] = "MISMATCH"
        except Exception as err:
            tapes[str(port)] = {"status": "ERR", "detail": str(err)}
            ok = False
    return {"parity": ok, "ports": tapes}


@app.post("/api/ops/peers/{peer_id}/stop")
def api_stop_peer(peer_id: int) -> dict[str, Any]:
    pids = json.loads(PID_FILE.read_text()) if PID_FILE.is_file() else {}
    pid = pids.get(str(peer_id))
    if not pid:
        raise HTTPException(status_code=404, detail="peer not managed by demo launcher")
    try:
        os.kill(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    pids.pop(str(peer_id), None)
    PID_FILE.write_text(json.dumps(pids, indent=2))
    return {"stopped": peer_id}


@app.post("/api/ops/peers/{peer_id}/start")
def api_start_peer(peer_id: int) -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"peer{peer_id}.log"
    pids = json.loads(PID_FILE.read_text()) if PID_FILE.is_file() else {}
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, str(_ROOT / "scripts" / "run_trading_peer.py"), str(peer_id)],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        cwd=str(_ROOT),
        env=env,
        start_new_session=True,
    )
    pids[str(peer_id)] = proc.pid
    PID_FILE.write_text(json.dumps(pids, indent=2))
    return {"started": peer_id, "pid": proc.pid}


@app.websocket("/ws/logs/{peer_id}")
async def ws_logs(websocket: WebSocket, peer_id: int) -> None:
    await websocket.accept()
    path = LOG_DIR / f"peer{peer_id}.log"
    last_size = 0
    try:
        while True:
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > last_size:
                    chunk = text[last_size:]
                    last_size = len(text)
                    for line in chunk.splitlines():
                        if line.strip():
                            await websocket.send_json(
                                {"line": line, "kind": classify_log_line(line)}
                            )
            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "web.server:app",
        host=os.getenv("UI_BIND", "0.0.0.0"),
        port=WEB_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
