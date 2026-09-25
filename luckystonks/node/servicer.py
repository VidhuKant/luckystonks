import json
import uuid

from luckystonks.matching.models import Command
from luckystonks.pb import trading_pb2


class LuckyStonksServicer:
    def __init__(self, engine):
        self.engine = engine

        # map tokens and usernames
        self.sessions = {}

    def Login(self, request, ctx):
        user = self.engine.users.get(request.user_id)

        # invalid request
        if user is None:
            return trading_pb2.LoginReply(status="ERR", token="")

        # incorrect password
        if user.password != request.password:
            return trading_pb2.LoginReply(status="ERR", token="")

        # generate token
        token = str(uuid.uuid4())
        self.sessions[token] = user.user_id

        # respond with token
        return trading_pb2.LoginReply(status="OK", token=token)

    def Post(self, request, ctx):
        user_id = self.sessions.get(request.token)

        # invalid user
        if user_id is None:
            return trading_pb2.PostReply(status="ERR", detail="invalid session")

        try:
            command = self._parse_order(user_id, request)
            res = self.engine.apply(command)
            return trading_pb2.PostReply(status=res.status, detail=res.detail)
        except ValueError as err:
            return trading_pb2.PostReply(status="ERR", detail=str(err))

    def Get(self, request, ctx):
        user_id = self.sessions.get(request.token)

        # invalid user
        if user_id is None:
            return trading_pb2.GetReply(status="ERR", detail="invalid session")

        data = self.engine.snapshot(request.type, user_id, request.params)
        return self._make_get_reply(data)

    def _parse_order(self, user_id, request):
        if request.type != "ORDER":
            raise ValueError("unsupported post type")

        payload = json.loads(request.data.decode("UTF-8"))

        return Command(
            client_request_id=payload["client_request_id"],
            user_id=user_id,
            side=payload["side"],
            symbol=payload["symbol"],
            price=int(payload["price"]),
            qty=int(payload["qty"]),
        )

    def _make_get_reply(self, data):
        items = []

        for item in data:
            items.append(
                trading_pb2.GetItem(
                    id=str(item["id"]),
                    data=json.dumps(item["data"]).encode("UTF-8"),
                )
            )

        return trading_pb2.GetReply(status="OK", items=items)
