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
    assert "habr_search_vacancies" in names
    assert "habr_get_response_history" in names


def test_tools_call_wraps_result():
    response = server.handle_message(FakeApp(), {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "habr_form", "arguments": {"path": "/profile/specialization"}},
    })
    assert response["result"]["content"][0]["type"] == "text"
    assert "habr_form" in response["result"]["content"][0]["text"]


def test_readonly_search_routes_through_app():
    from types import SimpleNamespace

    class FakeClient:
        def get(self, path):
            assert path.startswith("/vacancies?")
            return SimpleNamespace(
                status=200,
                url="https://career.habr.com/vacancies?type=all&q=Go&page=1",
                text=(
                    '<div data-vacancy-list="">'
                    '<div class="vacancy-card">'
                    '<a href="/vacancies/1000168900" class="vacancy-card__backdrop-link"></a>'
                    '<a class="vacancy-card__title-link" href="/vacancies/1000168900">'
                    'Backend Engineer</a></div></div>'
                ),
            )

    app = server.App(FakeClient())
    result = app.call("habr_search_vacancies", {"query": "Go", "page": 1})
    assert result["vacancies"][0]["vacancy_id"] == "1000168900"
    assert result["search_complete"] is False
    assert len(result["page_fingerprint"]) == 16
