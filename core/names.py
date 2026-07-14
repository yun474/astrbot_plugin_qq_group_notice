from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from .policy import parse_aliases


USER_NAME_KEYS = (
    "member_nickname",
    "member_nick",
    "user_nickname",
    "nickname",
    "nick",
    "display_name",
    "member_name",
    "username",
    "name",
)
GROUP_NAME_KEYS = (
    "group_name",
    "group_nickname",
    "group_nick",
    "group_title",
    "name",
)
OPERATOR_NAME_KEYS = (
    "operator_nickname",
    "op_member_nickname",
    "operator_name",
    "op_nickname",
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def pick_nested(data: Any, keys: tuple[str, ...], nested: tuple[str, ...] = ()) -> str:
    mapping = _as_mapping(data)
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for container in nested:
        found = pick_nested(mapping.get(container), keys)
        if found:
            return found
    return ""


class NameCache:
    """尽力缓存群消息中出现过的昵称，不承诺 QQ 事件一定提供昵称。"""

    def __init__(self, group_aliases: Any = "", max_entries: int = 4096) -> None:
        self.group_aliases = parse_aliases(group_aliases)
        self.max_entries = max(64, int(max_entries))
        self._members: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._groups: OrderedDict[str, str] = OrderedDict()

    @staticmethod
    def _valid_name(value: str, identifier: str = "") -> bool:
        text = str(value or "").strip()
        return bool(text and text != identifier and text.lower() not in {"unknown", "none"})

    def remember_member(self, group_id: str, member_id: str, nickname: str) -> None:
        if not group_id or not member_id or not self._valid_name(nickname, member_id):
            return
        key = (group_id, member_id)
        self._members[key] = nickname.strip()
        self._members.move_to_end(key)
        while len(self._members) > self.max_entries:
            self._members.popitem(last=False)

    def remember_group(self, group_id: str, group_name: str) -> None:
        if not group_id or not self._valid_name(group_name, group_id):
            return
        self._groups[group_id] = group_name.strip()
        self._groups.move_to_end(group_id)
        while len(self._groups) > self.max_entries:
            self._groups.popitem(last=False)

    def member_name(self, group_id: str, member_id: str, raw: Any = None) -> str:
        found = pick_nested(raw, USER_NAME_KEYS, ("member", "user", "author"))
        if found:
            self.remember_member(group_id, member_id, found)
            return found
        return self._members.get((group_id, member_id), "")

    def operator_name(self, group_id: str, operator_id: str, raw: Any = None) -> str:
        found = pick_nested(raw, OPERATOR_NAME_KEYS, ("operator", "op_member"))
        if found:
            self.remember_member(group_id, operator_id, found)
            return found
        return self.member_name(group_id, operator_id, raw)

    def group_name(self, group_id: str, raw: Any = None) -> str:
        if alias := self.group_aliases.get(group_id):
            return alias
        found = pick_nested(raw, GROUP_NAME_KEYS, ("group", "group_info"))
        if found:
            self.remember_group(group_id, found)
            return found
        return self._groups.get(group_id, "")
