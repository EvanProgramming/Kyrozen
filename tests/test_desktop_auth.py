"""Regression tests for desktop launch, REST, and pairing credentials."""

from kyrozen.desktop.auth import DesktopPairingManager, DesktopTokenManager


def test_open_token_preserves_launch_context_and_issues_rest_credentials():
    open_token = DesktopTokenManager.create_open_token(
        "user-open",
        "project-open",
        "supabase-access-token",
    )
    context = DesktopTokenManager.consume_open_token(open_token)

    assert context == {
        "user_id": "user-open",
        "project_id": "project-open",
        "access_token": "supabase-access-token",
    }
    assert DesktopTokenManager.consume_open_token(open_token) is None

    credentials = DesktopTokenManager.create_credentials(context["user_id"])
    assert DesktopTokenManager.verify_ws_token(credentials["ws_token"]) == "user-open"
    assert DesktopTokenManager.verify_api_token(credentials["api_token"]) == "user-open"


def test_pairing_issues_both_websocket_and_rest_credentials():
    code = DesktopPairingManager.create_code()
    assert DesktopPairingManager.confirm_code(code, "user-pair")

    result = DesktopPairingManager.poll_code(code)
    assert result is not None
    assert DesktopTokenManager.verify_ws_token(result["ws_token"]) == "user-pair"
    assert DesktopTokenManager.verify_api_token(result["access_token"]) == "user-pair"
