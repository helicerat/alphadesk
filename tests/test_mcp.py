import io
import json

from alphadesk.mcp_server import Server
from alphadesk.workspace import init


def call(tmp_path, *msgs):
    init(tmp_path, data="synthetic", synthetic={"n_assets": 80, "n_days": 600})
    out = io.StringIO()
    Server(str(tmp_path)).serve(io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n"), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_handshake_and_tools(tmp_path):
    r = call(tmp_path,
             {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert r[0]["result"]["serverInfo"]["name"] == "alphadesk"
    names = {t["name"] for t in r[1]["result"]["tools"]}
    assert names == {"dsl_reference", "submit", "graveyard", "status"}


def test_submit_returns_a_verdict_and_hides_post_cutoff(tmp_path):
    card = {"id": "q", "formula": "cs_rank(quality)", "hold": 5,
            "reason": {"counterparty": "x", "edge_type": "behavioral", "decay": "y"},
            "expect": [{"field": "quality", "sign": "+"}]}
    r = call(tmp_path, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "submit", "arguments": {"card": card}}},
             {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "graveyard", "arguments": {}}})
    v = json.loads(r[0]["result"]["content"][0]["text"])
    assert "survived" in v and "checks" in v
    for c in v["checks"]:
        if c["n"] == 11:
            assert "IC" not in c["detail"]
    g = json.loads(r[1]["result"]["content"][0]["text"])
    assert g and g[0]["card"] == "q"


def test_lookahead_card_is_refused(tmp_path):
    card = {"id": "peek", "formula": "cs_rank(delay(quality, -1))", "hold": 5,
            "reason": {"counterparty": "x", "edge_type": "behavioral", "decay": "y"},
            "expect": [{"field": "quality", "sign": "+"}]}
    r = call(tmp_path, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "submit", "arguments": {"card": card}}})
    v = json.loads(r[0]["result"]["content"][0]["text"])
    assert v["died_at"] == 2
