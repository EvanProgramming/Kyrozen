"""Small, secret-safe client for Afdian OAuth and Open API calls."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class AfdianError(RuntimeError):
    pass


@dataclass(frozen=True)
class AfdianAccount:
    user_id: str
    user_private_id: str


class AfdianClient:
    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    def configured(self) -> bool:
        return bool(self.config.afdian_client_id and self.config.afdian_client_secret)

    def plan_ids(self) -> dict[str, str]:
        return {
            "lite": str(self.config.afdian_plan_id_lite or ""),
            "pro": str(self.config.afdian_plan_id_pro or ""),
            "ultimate": str(self.config.afdian_plan_id_ultimate or ""),
        }

    def plan_for_id(self, plan_id: str) -> str | None:
        return next((plan for plan, value in self.plan_ids().items() if value and value == str(plan_id)), None)

    def checkout_url(self, plan_id: str) -> str:
        template = self.config.afdian_checkout_url_template or "https://afdian.com/a/Kyrozen/plan"
        try:
            return template.format(plan_id=urllib.parse.quote(str(plan_id), safe=""))
        except (KeyError, ValueError):
            return "https://afdian.com/a/Kyrozen/plan"

    def oauth_url(self, state: str, redirect_uri: str) -> str:
        params = {"client_id": self.config.afdian_client_id, "redirect_uri": redirect_uri, "response_type": "code", "state": state}
        return f"{self.config.afdian_oauth_authorize_url}?{urllib.parse.urlencode(params)}"

    def _json_request(self, url: str, payload: dict[str, Any], *, form: bool = False) -> dict[str, Any]:
        if form:
            body = urllib.parse.urlencode(payload).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise AfdianError("爱发电接口暂时不可用") from exc
        if not isinstance(result, dict) or result.get("ec") not in (0, 200):
            raise AfdianError("爱发电接口返回异常")
        return result

    def exchange_code(self, code: str, redirect_uri: str) -> AfdianAccount:
        result = self._json_request(
            "https://afdian.net/api/oauth2/access_token",
            {"client_id": self.config.afdian_client_id, "client_secret": self.config.afdian_client_secret, "code": code, "redirect_uri": redirect_uri},
            form=True,
        )
        data = result.get("data") or {}
        return AfdianAccount(str(data.get("user_id") or ""), str(data.get("user_private_id") or ""))

    def query_order(self, out_trade_no: str) -> dict[str, Any]:
        params = {"out_trade_no": out_trade_no}
        params_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        ts = __import__("time").time_ns() // 1_000_000_000
        user_id = str(self.config.afdian_open_user_id)
        sign_source = f"{self.config.afdian_open_api_token}params{params_json}ts{ts}user_id{user_id}"
        payload = {"params": params_json, "ts": ts, "user_id": user_id, "sign": hashlib.md5(sign_source.encode()).hexdigest()}
        result = self._json_request(f"{self.config.afdian_api_base_url.rstrip('/')}/open/query-order", payload)
        data = result.get("data") or {}
        orders = data.get("order") or data.get("orders") or []
        if isinstance(orders, dict):
            orders = [orders]
        for order in orders:
            if str(order.get("out_trade_no")) == str(out_trade_no):
                return order
        raise AfdianError("未找到爱发电订单")
