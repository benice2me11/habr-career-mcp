import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location("habr_server", Path(__file__).parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class FakeApp:
    def call(self, name, args):
        return {"name": name, "args": args}


def test_initialize_and_tool_listing():
    init = server.handle_message(FakeApp(), {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    })
    assert init["result"]["serverInfo"]["name"] == "habr-career-mcp"
    listed = server.handle_message(FakeApp(), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert "habr_preview_update" in names
    assert "habr_apply_update" in names


def test_tools_call_wraps_result():
    response = server.handle_message(FakeApp(), {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "habr_form", "arguments": {"path": "/profile/specialization"}},
    })
    assert response["result"]["content"][0]["type"] == "text"
    assert "habr_form" in response["result"]["content"][0]["text"]
