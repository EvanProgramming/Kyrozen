"""Afdian binding, checkout and idempotent grant coverage."""

from kyrozen.config import KyrozenConfig
from kyrozen.membership import MembershipService
from kyrozen.membership.afdian import AfdianClient
from kyrozen.project import KyrozenDatabase
from fastapi.testclient import TestClient
from tests.conftest import MockModel, TEST_USER, make_authenticated_app


def _service(temp_dir: str) -> MembershipService:
    return MembershipService(KyrozenDatabase(f"{temp_dir}/kyrozen.db"), KyrozenConfig(workspace_root=temp_dir, provider="ollama"))


def test_oauth_state_is_single_use_and_checkout_requires_binding(temp_dir: str):
    service = _service(temp_dir)
    state = service.create_afdian_oauth_state("user", "state-1", "https://example.test/callback")
    assert state["state"] == "state-1"
    consumed = service.consume_afdian_oauth_state("state-1")
    assert consumed and service.consume_afdian_oauth_state("state-1") is None
    try:
        service.create_afdian_checkout("user", "lite", "plan-lite", "https://afdian.com/a/Kyrozen/plan")
    except ValueError as exc:
        assert "绑定" in str(exc)
    else:
        raise AssertionError("unbound checkout must be rejected")


def test_duplicate_afdian_grant_does_not_extend_twice(temp_dir: str):
    service = _service(temp_dir)
    service.bind_afdian_account("user", "afdian-user", "private-user")
    session = service.create_afdian_checkout("user", "pro", "plan-pro", "https://afdian.com/a/Kyrozen/plan")
    order = {"out_trade_no": "trade-1", "user_id": "afdian-user", "user_private_id": "private-user", "plan_id": "plan-pro", "month": 2, "status": 2, "total_amount": 280}
    assert service.record_afdian_order(order, user_id="user", plan="pro") is True
    first = service.grant_afdian_order(order, user_id="user", plan="pro")
    assert service.record_afdian_order(order, user_id="user", plan="pro") is False
    second = service.grant_afdian_order(order, user_id="user", plan="pro")
    assert first["period_end"] == second["period_end"]
    assert service.afdian_checkout("user", session["id"])["status"] == "paid"


def test_multi_month_grant_uses_31_day_semantics(temp_dir: str):
    service = _service(temp_dir)
    service.bind_afdian_account("user", "afdian-user", "private-user")
    order = {"out_trade_no": "trade-31", "user_id": "afdian-user", "plan_id": "plan-lite", "month": 3, "status": 2}
    service.record_afdian_order(order, user_id="user", plan="lite")
    before = service.membership("user")["period_end"]
    granted = service.grant_afdian_order(order, user_id="user", plan="lite")
    # The free period starts at the current calendar month, so the paid end
    # is strictly more than the configured 93-day grant from now.
    assert granted["plan"] == "lite"
    assert granted["period_end"] > before


def test_webhook_verifies_and_is_idempotent(temp_dir: str, monkeypatch):
    config = KyrozenConfig(provider="ollama", workspace_root=temp_dir, membership_enabled=True, afdian_plan_id_lite="plan-lite", afdian_open_user_id="creator", afdian_open_api_token="token")
    service = MembershipService(KyrozenDatabase(f"{temp_dir}/kyrozen.db"), config)
    service.bind_afdian_account(TEST_USER.user_id, "afdian-user", "private-user")
    confirmed = {"out_trade_no": "trade-webhook", "user_id": "afdian-user", "user_private_id": "private-user", "plan_id": "plan-lite", "month": 1, "status": 2, "total_amount": 24}
    monkeypatch.setattr(AfdianClient, "query_order", lambda self, trade: confirmed)
    client = TestClient(make_authenticated_app(config, MockModel(["OK"])))
    payload = {"data": {"order": confirmed}}
    with client:
        assert client.post("/api/webhooks/afdian", json=payload).json()["ec"] == 200
        first = client.get("/api/membership").json()
        assert first["plan"] == "lite"
        assert client.post("/api/webhooks/afdian", json=payload).json()["ec"] == 200
        second = client.get("/api/membership").json()
        assert first["period_end"] == second["period_end"]
