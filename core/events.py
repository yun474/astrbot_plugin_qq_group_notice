from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _pick(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


@dataclass(slots=True)
class QQGroupMemberEvent:
    """botpy 目前缺少的普通群成员事件对象。"""

    _api: Any
    event_id: str
    event_type: str
    timestamp: str
    group_openid: str
    member_openid: str
    op_member_openid: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        api: Any,
        event_type: str,
        payload: dict[str, Any],
    ) -> "QQGroupMemberEvent":
        data = payload.get("d") if isinstance(payload.get("d"), dict) else payload
        return cls(
            _api=api,
            event_id=_pick(payload, "id", "event_id") or _pick(data, "event_id"),
            event_type=event_type,
            timestamp=_pick(data, "timestamp", "event_time", "time"),
            group_openid=_pick(data, "group_openid", "group_id", "groupId"),
            member_openid=_pick(
                data,
                "member_openid",
                "user_openid",
                "openid",
                "user_id",
                "userId",
            ),
            op_member_openid=_pick(
                data,
                "op_member_openid",
                "operator_openid",
                "op_user_id",
                "opUserId",
            ),
            raw_data=dict(data),
        )
