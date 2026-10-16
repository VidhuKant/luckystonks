import json
import uuid
from dataclasses import asdict, is_dataclass

from luckystonks.matching.models import Command
from luckystonks.pb import trading_pb2, trading_pb2_grpc

ADMIN_GET_TYPES = frozenset({"ADMIN_PORTFOLIOS", "ORDER_LOG"})

class LuckyStonksServicer(trading_pb2_grpc.TradingServicer):
    def __init__(self, engine, insight_read_token: str, seed_file: str = "", raft_runtime=None):
        self.engine = engine
        self.sessions = {}
        self.insight_read_token = insight_read_token
        self.seed_file = seed_file
        self.raft_runtime = raft_runtime

    def Login(self, request, context):
        user = self.engine.users.get(request.username)

        if user is None:
            return trading_pb2.LoginReply(status="ERR", token="",role="")

        if user.password != request.password:
            return trading_pb2.LoginReply(status="ERR", token="",role="")

        token = str(uuid.uuid4())
        self.sessions[token] = user.user_id
        return trading_pb2.LoginReply(status="OK", token=token, role= user.role)

    def Logout(self, request, context):
        if request.token in self.sessions:
            del self.sessions[request.token]
            return trading_pb2.LogoutReply(status="OK")
        return trading_pb2.LogoutReply(status="ERR")

    def Post(self, request, context):
        user_id = self.sessions.get(request.token)

        if user_id is None:
            return trading_pb2.PostReply(status="ERR", detail="invalid session")

        if request.type == "ADMIN_RESET":
            if not self._is_admin(user_id):
                return trading_pb2.PostReply(status="ERR", detail="admin only")
            if not self.seed_file:
                return trading_pb2.PostReply(status="ERR", detail="seed file not configured")
            if self.raft_runtime is not None:
                if not self.raft_runtime.is_leader():
                    return trading_pb2.PostReply(
                        status="ERR", detail=self.raft_runtime.not_leader_detail()
                    )
                if not self.raft_runtime.replicate_admin_reset(self.seed_file):
                    return trading_pb2.PostReply(status="ERR", detail="replication failed")
                return trading_pb2.PostReply(status="OK", detail="market reset to seed")
            self.engine.reset_from_seed(self.seed_file)
            self.sessions.clear()
            return trading_pb2.PostReply(status="OK", detail="market reset to seed")

        try:
            command = self._parse_order(user_id, request)
            if self.raft_runtime is not None:
                if not self.raft_runtime.is_leader():
                    return trading_pb2.PostReply(
                        status="ERR", detail=self.raft_runtime.not_leader_detail()
                    )
                if not self.raft_runtime.replicate_command(command):
                    return trading_pb2.PostReply(status="ERR", detail="replication failed")
                res = self.engine.results_by_request[command.client_request_id]
                return trading_pb2.PostReply(status=res.status, detail=res.message)
            res = self.engine.apply(command)
            return trading_pb2.PostReply(status=res.status, detail=res.message)
        except ValueError as err:
            return trading_pb2.PostReply(status="ERR", detail=str(err))

    def Get(self, request, context):
        user_id = self.sessions.get(request.token)
        if request.token == self.insight_read_token and request.type == "TRADES":
            data = self.engine.snapshot("TRADES")
        elif user_id is not None:
            if request.type in ADMIN_GET_TYPES and not self._is_admin(user_id):
                return trading_pb2.GetReply(status="ERR")
            data = self.engine.snapshot(request.type, user_id, request.params)
        else:
            return trading_pb2.GetReply(status="ERR")
        return self._make_get_reply(data)

    def _is_admin(self, user_id: str)-> bool:
        user= self.engine.users.get(user_id)
        return user is not None and user.role =="admin"
    

    def _parse_order(self, user_id, request):
        if request.type != "ORDER":
            raise ValueError("unsupported post type")

        try:
            payload = json.loads(request.data.decode("utf-8"))
            client_request_id = payload["client_request_id"]
            side = payload["side"]
            symbol = payload["symbol"]
            price = int(payload["price"])
            qty = int(payload["qty"])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid order payload") from error

        return Command(
            client_request_id=client_request_id,
            user_id=user_id,
            side=side,
            symbol=symbol,
            price=price,
            qty=qty,
        )

    def _make_get_reply(self, data):
        items = []

        if isinstance(data, dict):
            data = [data]
        for index, item in enumerate(data or []):
            payload = asdict(item) if is_dataclass(item) else item
            item_id = payload.get("trade_id", index) if isinstance(payload, dict) else index
            items.append(
                trading_pb2.GetItem(
                    id=str(item_id),
                    data=json.dumps(payload).encode("UTF-8"),
                )
            )

        return trading_pb2.GetReply(status="OK", items=items)
