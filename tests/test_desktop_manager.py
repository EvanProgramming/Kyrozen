"""Desktop task routing must choose a receive-capable connection."""

from kyrozen.desktop.manager import DesktopClientManager


class _Socket:
    async def send_json(self, _message):
        return None


def test_pick_client_ignores_rest_presence_without_websocket():
    manager = DesktopClientManager()
    rest_presence = manager.register("user-1", current_project_id="project-1")
    websocket_client = manager.register("user-1", current_project_id="project-1", websocket=_Socket())

    selected = manager.pick_client_for_task("user-1", "project-1")

    assert selected is websocket_client
    assert selected is not rest_presence
