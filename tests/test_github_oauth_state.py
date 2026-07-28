from kyrozen.api.server import _decode_github_oauth_state, _encode_github_oauth_state


def test_github_oauth_state_survives_process_local_storage() -> None:
    state = _encode_github_oauth_state("https://kyrozen.chat/api/auth/github/login-callback", "secret")

    decoded = _decode_github_oauth_state(state, "secret")

    assert decoded is not None
    assert decoded["redirect_uri"] == "https://kyrozen.chat/api/auth/github/login-callback"


def test_github_oauth_state_rejects_tampering_and_expiry() -> None:
    state = _encode_github_oauth_state("https://kyrozen.chat/callback", "secret")
    assert _decode_github_oauth_state(state + "x", "secret") is None

    expired = _encode_github_oauth_state("https://kyrozen.chat/callback", "secret", ttl_seconds=-1)
    assert _decode_github_oauth_state(expired, "secret") is None
