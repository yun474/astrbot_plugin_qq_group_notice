from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .events import QQGroupMemberEvent


NoticeHandler = Callable[[str, Any, Any], Awaitable[None]]
LogHandler = Callable[[str], None]


@dataclass(slots=True)
class _Binding:
    client: Any
    attribute: str
    original: Any
    wrapper: Any


@dataclass(slots=True)
class _IntentPatch:
    client: Any
    original: int
    patched: int


class QQOfficialNoticeBridge:
    """为 AstrBot 原生 QQ 适配器补齐群生命周期回调。"""

    GROUP_MEMBER_INTENT = 1 << 24
    SUPPORTED_PLATFORMS = {"qq_official", "qq_official_webhook"}
    CALLBACKS = {
        "group_add_robot": "bot_join",
        "group_member_add": "member_join",
        "group_member_remove": "member_leave",
    }

    def __init__(self, handler: NoticeHandler, log: LogHandler) -> None:
        self.handler = handler
        self.log = log
        self._bindings: list[_Binding] = []
        self._intent_patches: list[_IntentPatch] = []
        self._bound_clients: set[int] = set()
        self._adapters: list[Any] = []
        self._connection_state_cls: Any = None
        self._class_originals: dict[str, Any] = {}
        self._owned_class_methods: set[str] = set()

    @staticmethod
    def _member_parser(event_type: str):
        def parser(state: Any, payload: dict[str, Any]) -> None:
            event = QQGroupMemberEvent.from_payload(state.api, event_type, payload)
            state._dispatch(event_type.lower(), event)

        parser.__name__ = f"parse_{event_type.lower()}"
        parser.__qualname__ = f"ConnectionState.{parser.__name__}"
        setattr(parser, "__qq_group_notice_bridge__", True)
        return parser

    def install_parser_patch(self) -> None:
        try:
            from botpy.connection import ConnectionState
        except Exception as exc:
            self.log(f"[QQ群通知] 无法加载 botpy 事件解析器：{exc}")
            return
        self._connection_state_cls = ConnectionState
        for event_type in ("GROUP_MEMBER_ADD", "GROUP_MEMBER_REMOVE"):
            attr = f"parse_{event_type.lower()}"
            if hasattr(ConnectionState, attr):
                continue
            self._class_originals[attr] = None
            setattr(ConnectionState, attr, self._member_parser(event_type))
            self._owned_class_methods.add(attr)
        if self._owned_class_methods:
            self.log("[QQ群通知] 已安装普通成员进退群事件解析桥。")

    @staticmethod
    def _platform_name(adapter: Any) -> str:
        try:
            return str(adapter.meta().name)
        except Exception:
            return ""

    async def bind_platforms(self, context: Any) -> int:
        manager = getattr(context, "platform_manager", None)
        if manager is None:
            return 0
        try:
            adapters = list(manager.get_insts())
        except Exception:
            adapters = list(getattr(manager, "platform_insts", ()) or ())
        count = 0
        for adapter in adapters:
            if self._platform_name(adapter) not in self.SUPPORTED_PLATFORMS:
                continue
            client = getattr(adapter, "client", None)
            if client is None or id(client) in self._bound_clients:
                continue
            self._enable_group_member_intent(client, adapter)
            self._bind_client(client, adapter)
            self._ensure_existing_parsers(adapter)
            self._bound_clients.add(id(client))
            self._adapters.append(adapter)
            count += 1
        return count

    def _enable_group_member_intent(self, client: Any, adapter: Any) -> bool:
        """在 WSS identify 前补上普通群成员进退事件订阅位。"""
        if self._platform_name(adapter) != "qq_official":
            return False
        intents = getattr(client, "intents", None)
        if not isinstance(intents, int):
            self.log("[QQ群通知] 无法读取 QQ WebSocket Intents，成员进退事件可能不会下发。")
            return False
        if intents & self.GROUP_MEMBER_INTENT:
            return False
        patched = intents | self.GROUP_MEMBER_INTENT
        client.intents = patched
        self._intent_patches.append(_IntentPatch(client, intents, patched))
        self.log("[QQ群通知] 已启用 GROUP_MEMBER Intents（1 << 24）。")
        if getattr(client, "_connection", None) is not None:
            self.log("[QQ群通知] QQ 连接已经建立，请重载 QQ 平台或重启 AstrBot 使新 Intents 生效。")
        return True

    @staticmethod
    def _connections(adapter: Any) -> list[Any]:
        candidates = [getattr(getattr(adapter, "client", None), "_connection", None)]
        webhook = getattr(adapter, "webhook_helper", None)
        candidates.append(getattr(webhook, "_connection", None))
        result: list[Any] = []
        seen: set[int] = set()
        for connection in candidates:
            if connection is not None and id(connection) not in seen:
                seen.add(id(connection))
                result.append(connection)
        return result

    def _ensure_existing_parsers(self, adapter: Any) -> None:
        """兼容平台已运行后才热重载插件的场景。"""
        for connection in self._connections(adapter):
            parser_map = getattr(connection, "parser", None)
            state = getattr(connection, "state", None)
            if not isinstance(parser_map, dict) or state is None:
                continue
            for event_type in ("GROUP_MEMBER_ADD", "GROUP_MEMBER_REMOVE"):
                key = event_type.lower()
                if key in parser_map:
                    continue
                parser = self._member_parser(event_type).__get__(state, type(state))
                parser_map[key] = parser

    def _bind_client(self, client: Any, adapter: Any) -> None:
        for botpy_event, notice_type in self.CALLBACKS.items():
            attr = f"on_{botpy_event}"
            original = getattr(client, attr, None)

            async def wrapper(
                event: Any,
                *,
                _notice_type: str = notice_type,
                _adapter: Any = adapter,
                _original: Any = original,
            ) -> None:
                try:
                    await self.handler(_notice_type, event, _adapter)
                except Exception as exc:
                    self.log(
                        f"[QQ群通知] 通知处理异常，继续执行原回调："
                        f"type={_notice_type}, error={exc}"
                    )
                if _original is not None:
                    result = _original(event)
                    if inspect.isawaitable(result):
                        await result

            setattr(wrapper, "__qq_group_notice_bridge__", True)
            setattr(client, attr, wrapper)
            self._bindings.append(_Binding(client, attr, original, wrapper))
        self.log(f"[QQ群通知] 已接入平台实例：{self._platform_name(adapter)}")

    async def uninstall(self) -> None:
        for binding in reversed(self._bindings):
            if getattr(binding.client, binding.attribute, None) is not binding.wrapper:
                continue
            if binding.original is None:
                try:
                    delattr(binding.client, binding.attribute)
                except AttributeError:
                    pass
            else:
                setattr(binding.client, binding.attribute, binding.original)
        self._bindings.clear()
        self._bound_clients.clear()

        for patch in reversed(self._intent_patches):
            if getattr(patch.client, "intents", None) == patch.patched:
                patch.client.intents = patch.original
        self._intent_patches.clear()

        for adapter in self._adapters:
            for connection in self._connections(adapter):
                parser_map = getattr(connection, "parser", None)
                if not isinstance(parser_map, dict):
                    continue
                for key in ("group_member_add", "group_member_remove"):
                    parser = parser_map.get(key)
                    func = getattr(parser, "__func__", parser)
                    if getattr(func, "__qq_group_notice_bridge__", False):
                        parser_map.pop(key, None)
        self._adapters.clear()

        cls = self._connection_state_cls
        if cls is not None:
            for attr in self._owned_class_methods:
                current = getattr(cls, attr, None)
                if getattr(current, "__qq_group_notice_bridge__", False):
                    delattr(cls, attr)
        self._owned_class_methods.clear()
