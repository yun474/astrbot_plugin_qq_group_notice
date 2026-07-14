from __future__ import annotations

import re
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def parse_id_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        parts = value
    else:
        parts = re.split(r"[,;\s]+", str(value or ""))
    return {str(item).strip() for item in parts if str(item).strip()}


def parse_aliases(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {
            str(key).strip(): str(alias).strip()
            for key, alias in value.items()
            if str(key).strip() and str(alias).strip()
        }
    result: dict[str, str] = {}
    for line in str(value or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key, alias = line.split(separator, 1)
        if key.strip() and alias.strip():
            result[key.strip()] = alias.strip()
    return result


@dataclass(slots=True)
class NoticePolicy:
    enabled: bool
    filter_mode: str
    blacklist: set[str]
    whitelist: set[str]

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "NoticePolicy":
        mode = str(config.get("group_filter_mode", "disabled")).strip().lower()
        if mode not in {"disabled", "blacklist", "whitelist"}:
            mode = "disabled"
        return cls(
            enabled=bool(config.get("enabled", True)),
            filter_mode=mode,
            blacklist=parse_id_set(config.get("blacklist_groups", "")),
            whitelist=parse_id_set(config.get("whitelist_groups", "")),
        )

    def allows(self, group_id: str) -> bool:
        if not self.enabled or not group_id:
            return False
        if self.filter_mode == "blacklist":
            return group_id not in self.blacklist
        if self.filter_mode == "whitelist":
            return group_id in self.whitelist
        return True


class _PreservingDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class SafeTemplate:
    @staticmethod
    def render(template: str, values: Mapping[str, Any]) -> str:
        clean = _PreservingDict(
            {key: "" if value is None else str(value) for key, value in values.items()}
        )
        try:
            return str(template or "").format_map(clean).strip()
        except (ValueError, KeyError):
            return str(template or "").strip()


class TTLSeenCache:
    def __init__(self, ttl_seconds: float = 300, max_entries: int = 2048) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_entries = max(16, int(max_entries))
        self._items: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, key: str, now: float | None = None) -> bool:
        if not key:
            return False
        current = time.monotonic() if now is None else now
        while self._items:
            _, first_time = next(iter(self._items.items()))
            if current - first_time <= self.ttl_seconds:
                break
            self._items.popitem(last=False)
        if key in self._items:
            self._items.move_to_end(key)
            return True
        self._items[key] = current
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
        return False
