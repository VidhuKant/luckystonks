import json

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.node.servicer import LuckyStonksServicer
from luckystonks.pb import trading_pb2


class _FakeRaft:
    def __init__(self, engine: Engine, *, leader: bool = True) -> None:
        self.engine = engine
        self._leader = leader

    def is_leader(self) -> bool:
        return self._leader

    def not_leader_detail(self) -> str:
        return "NOT_LEADER;trading=127.0.0.1:50051"

    def replicate_command(self, command: Command) -> bool:
        if not self._leader:
            return False
        self.engine.apply(command)
        return True

    def replicate_admin_reset(self, seed_path: str) -> bool:
        if not self._leader:
            return False
        self.engine.reset_from_seed(seed_path)
        return True


def _order_bytes(client_request_id: str = "req-1") -> bytes:
    return json.dumps(
        {
            "client_request_id": client_request_id,
            "side": "SELL",
            "symbol": "RELIANCE",
            "price": 2450,
            "qty": 10,
        }
    ).encode("utf-8")


def test_post_order_via_raft_leader() -> None:
    engine = Engine()
    engine.seed_demo_users()
    raft = _FakeRaft(engine, leader=True)
    servicer = LuckyStonksServicer(engine, insight_read_token="t", raft_runtime=raft)
    login = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)

    reply = servicer.Post(
        trading_pb2.PostRequest(token=login.token, type="ORDER", data=_order_bytes()),
        context=None,
    )
    assert reply.status == "RESTING"
    assert len(engine.books["RELIANCE"].asks) == 1


def test_post_order_not_leader() -> None:
    engine = Engine()
    engine.seed_demo_users()
    raft = _FakeRaft(engine, leader=False)
    servicer = LuckyStonksServicer(engine, insight_read_token="t", raft_runtime=raft)
    login = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)

    reply = servicer.Post(
        trading_pb2.PostRequest(token=login.token, type="ORDER", data=_order_bytes()),
        context=None,
    )
    assert reply.status == "ERR"
    assert reply.detail.startswith("NOT_LEADER;")
