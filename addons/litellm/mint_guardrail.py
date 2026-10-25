"""LiteLLM MCP 도구 호출 직전에 MINT 판정을 거는 커스텀 가드레일 (D-191).

설치: 이 파일을 LiteLLM config.yaml 옆에 두고 아래처럼 등록한다.
    guardrails:
      - guardrail_name: mint
        litellm_params: {guardrail: mint_guardrail.MintGuardrail, mode: pre_mcp_call, default_on: true}
환경 변수: MINT_GATEWAY_URL(예 https://gateway.corp:443), 사설 CA면 MINT_CA_FILE.

직원은 `Authorization: Bearer <본인 MINT 토큰>` + `x-litellm-api-key: <LiteLLM 키>`로 호출한다. LiteLLM이
가드레일에 넘기는 `incoming_bearer_token`(proxy/utils.py `_convert_mcp_to_llm_format`)이 그 토큰이다.
LiteLLM이 주장하는 사용자·팀(`user_api_key_*`)은 MINT에 기록만 되고 판정에는 쓰이지 않는다.
MINT가 답하지 못하거나 허용이 아니면 호출을 막는다(fail-closed).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os

import httpx
from fastapi import HTTPException
from litellm.integrations.custom_guardrail import CustomGuardrail

log = logging.getLogger("mint_guardrail")
PENDING_MAX = 10000


def _deny(message: str) -> None:
    raise HTTPException(status_code=403, detail={"error": f"[MINT] {message}"})


def _digest(result) -> tuple[str, int]:
    try:
        if isinstance(result, (list, tuple)):
            raw = json.dumps([c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in result],
                             sort_keys=True, default=str)
        else:
            raw = result.model_dump_json()
    except Exception:
        raw = repr(result)
    data = raw.encode("utf-8", "replace")
    return hashlib.sha256(data).hexdigest(), len(data)


class MintGuardrail(CustomGuardrail):
    def __init__(self, **kwargs):
        self._url = os.environ["MINT_GATEWAY_URL"].rstrip("/")  # 없으면 기동 단계에서 실패시킨다
        self._verify = os.getenv("MINT_CA_FILE") or True
        self._timeout = float(os.getenv("MINT_TIMEOUT_SECONDS", "10"))
        self._client: httpx.AsyncClient | None = None
        # 판정→사후 기록 연결용. 프로세스 안에만 두고 토큰은 로그·spend 기록에 싣지 않는다.
        # ponytail: LiteLLM 복제본이 여러 개여도 같은 호출의 pre/post는 한 프로세스에서 끝난다.
        self._pending: dict[str, tuple[str, int]] = {}
        super().__init__(**kwargs)

    async def _post(self, path: str, token: str, body: dict) -> dict:
        if self._client is None:
            self._client = httpx.AsyncClient(verify=self._verify, timeout=self._timeout)
        response = await self._client.post(self._url + path, json=body, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if "mcp_tool_name" not in data:
            return data  # MCP 호출이 아니면 관여하지 않는다
        # 1.105는 tools/list 때도 같은 훅으로 도구 설명을 검사한다(tool_catalog_guard). 목록은 실행이 아니므로 판정하지
        # 않는다 — 여기서 막으면 모든 도구가 목록에서 사라진다(CI 실측). 호출(call_mcp_tool 등)은 그대로 판정한다.
        if str(getattr(call_type, "value", call_type)) == "list_mcp_tools":
            return data
        token = data.get("incoming_bearer_token")
        if not token:
            _deny("직원 MINT 토큰(Authorization: Bearer)이 없어 도구 호출을 막았습니다.")
        logging_obj = data.get("litellm_logging_obj")
        call_id = getattr(logging_obj, "litellm_call_id", None)
        asserted = {key: str(data[f"user_api_key_{key}"]) for key in ("user_id", "team_id", "end_user_id")
                    if data.get(f"user_api_key_{key}")}
        try:
            verdict = await self._post("/api/addon/v1/mcp-decision", token, {
                "server_id": data.get("mcp_server_name") or "", "tool": data["mcp_tool_name"],
                "arguments": data.get("mcp_arguments") or {}, "gateway": "litellm",
                "asserted": asserted, "call_ref": call_id})
        except httpx.HTTPStatusError as exc:
            _deny(f"MINT가 판정을 거부했습니다(HTTP {exc.response.status_code}). 토큰이 유효한 직원 MCP 토큰인지 확인하세요.")
        except (httpx.HTTPError, ValueError) as exc:
            _deny(f"MINT 판정을 받지 못해 도구 호출을 막았습니다({type(exc).__name__}).")
        if verdict.get("allow") is not True:
            _deny(f"{verdict.get('decision')} · {verdict.get('policy_id')} · {verdict.get('reason')}")
        if call_id and verdict.get("decision_id"):
            if len(self._pending) >= PENDING_MAX:
                self._pending.pop(next(iter(self._pending)))
            self._pending[call_id] = (token, int(verdict["decision_id"]))
        if verdict.get("effective_arguments") is not None:
            data["modified_arguments"] = verdict["effective_arguments"]
        return data

    async def async_post_mcp_tool_call_hook(self, kwargs, response_obj, start_time, end_time):
        """LiteLLM이 도구를 실제로 보낸 뒤. 기록 실패는 이미 나간 호출을 되돌리지 못하므로 로그만 남긴다."""
        pending = self._pending.pop(kwargs.get("litellm_call_id"), None)
        if not pending:
            return None
        token, decision_id = pending
        result = getattr(response_obj, "mcp_tool_call_response", response_obj)
        digest, size = _digest(result)
        try:
            answer = await self._post("/api/addon/v1/mcp-result", token, {
                "decision_id": decision_id, "outcome": "executed", "is_error": bool(getattr(result, "isError", False)),
                "result_sha256": digest, "result_bytes": size})
        except Exception as exc:
            log.warning("MINT 결과 기록 실패(decision %s): %s", decision_id, type(exc).__name__)
            return None
        # 200이어도 MINT가 기록을 거절할 수 있다(다른 직원의 판정 등). 조용히 사라지지 않게 남긴다.
        if answer.get("recorded") is not True:
            log.warning("MINT가 결과 기록을 거절(decision %s): %s", decision_id, str(answer.get("reason"))[:120])
        return None
