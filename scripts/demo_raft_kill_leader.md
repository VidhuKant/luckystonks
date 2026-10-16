# Raft 3-peer demo (kill leader)

## Start peers (three terminals)

```bash
cd luckystonks && source .venv/bin/activate
python scripts/run_trading_peer.py 0
python scripts/run_trading_peer.py 1
python scripts/run_trading_peer.py 2
```

Watch startup logs for `role=leader` on one peer (changes after elections).

## Client

Connect to any trading port (50051–50053). Orders auto-redirect to the leader and re-login.

```bash
python -m luckystonks.client.cli --host 127.0.0.1 --port 50052
```

Place Ved SELL / Pratham BUY RELIANCE @ 2450 × 10.

## Verify parity

On each peer (change `--port`):

```bash
python -m luckystonks.client.cli view admin admin TRADES
```

## Kill leader

Stop the terminal that shows `role=leader`. Wait ~1s for a new election.

Place another order via the CLI (same as above).

## Reset demo (admin)

Menu **8** on the leader after login as `admin` / `admin`.
