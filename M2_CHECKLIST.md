# M2 checklist (team)

- [x] Raft log + apply on engine
- [x] Leader election (RequestVote)
- [x] AppendEntries replication + heartbeats
- [x] 3-peer script (`run_trading_peer.py`)
- [x] Trading writes via leader + NOT_LEADER hints
- [x] Raft + engine persistence per peer
- [x] Admin reset replicated through log
- [x] nextIndex backtrack + same-term commit
- [x] Cross-peer fingerprint tests + stress (in-memory 100 orders + `test_stress_and_edges.py`)
- [x] Live stress + edges (`scripts/cluster_stress_live.sh`)
- [x] Live kill-leader demo (`scripts/cluster_live_verify.sh` — automated terminal run)
- [x] Majority replication + follower catch-up after restart
- [x] Log compaction + InstallSnapshot RPC
- [x] Cluster membership changes (add/remove via replicated CLUSTER_CHANGE)
- [ ] Post-M2: quote / P&L / market orders
