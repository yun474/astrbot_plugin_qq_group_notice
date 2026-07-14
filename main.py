from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig

from .core import NameCache, NoticePolicy, QQOfficialNoticeBridge, SafeTemplate, TTLSeenCache


PLUGIN_NAME = "astrbot_plugin_qq_group_notice"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _first_attr(obj: Any, *names: str) -> str:
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            continue
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _raw_event_data(event: Any) -> dict[str, Any]:
    raw = getattr(event, "raw_data", None)
    result = dict(raw) if isinstance(raw, Mapping) else {}
    for key in (
        "event_id",
        "timestamp",
        "group_openid",
        "member_openid",
        "op_member_openid",
        "nickname",
        "member_nickname",
        "group_name",
    ):
        value = getattr(event, key, None)
        if value is not None and key not in result:
            result[key] = value
    return result


def _format_time(value: Any) -> str:
    text = _text(value)
    if not text:
        return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    try:
        number = float(text)
        if number > 10_000_000_000:
            number /= 1000
        return dt.datetime.fromtimestamp(number).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return text


class QQGroupNoticePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self.policy = NoticePolicy.from_config(self.config)
        self.names = NameCache(
            self.config.get("group_aliases", ""),
            max_entries=int(self.config.get("nickname_cache_size", 4096) or 4096),
        )
        self.seen = TTLSeenCache(ttl_seconds=300, max_entries=2048)
        self.debug = bool(self.config.get("debug_log", False))
        self.bridge = QQOfficialNoticeBridge(self._handle_notice, logger.info)
        # 插件实例化早于平台实例化，此时补类方法，WebSocket/Webhook 后续建立的
        # ConnectionState 才会自动把普通成员事件收进 parser 表。
        self.bridge.install_parser_patch()
        logger.info("[QQ群通知] 插件已加载，云云开始蹲群门口记人啦。")

    @filter.on_platform_loaded()
    async def on_platform_loaded(self) -> None:
        await self.bridge.bind_platforms(self.context)

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self) -> None:
        await self.bridge.bind_platforms(self.context)

    @filter.on_plugin_loaded()
    async def on_plugin_loaded(self, _metadata: Any) -> None:
        """兼容在 AstrBot 已启动后安装、更新或热重载本插件。"""
        await self.bridge.bind_platforms(self.context)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=-1000)
    async def cache_visible_names(self, event: AstrMessageEvent) -> None:
        """从普通群消息尽力积累群员昵称和群名称。"""
        try:
            if event.get_platform_name() not in self.bridge.SUPPORTED_PLATFORMS:
                return
            group_id = _text(event.get_group_id())
            if not group_id:
                return
            member_id = _text(event.get_sender_id())
            nickname = _text(event.get_sender_name())
            self.names.remember_member(group_id, member_id, nickname)

            message_obj = getattr(event, "message_obj", None)
            raw = getattr(message_obj, "raw_message", None)
            group_name = _first_attr(
                message_obj,
                "group_name",
                "group_nickname",
                "group_title",
            ) or _first_attr(raw, "group_name", "group_nickname", "group_title")
            self.names.remember_group(group_id, group_name)
        except Exception as exc:
            if self.debug:
                logger.warning(f"[QQ群通知] 昵称缓存更新失败：{exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("群通知信息")
    async def group_notice_info(self, event: AstrMessageEvent):
        """查看当前群 OpenID、群名称解析结果和过滤状态。"""
        if event.get_platform_name() not in self.bridge.SUPPORTED_PLATFORMS:
            yield event.plain_result("当前不是 QQ 官方机器人会话。")
            return
        group_id = _text(event.get_group_id())
        if not group_id:
            yield event.plain_result("请在 QQ 官方群聊中使用这个指令。")
            return
        group_name = self.names.group_name(group_id) or "未取得（可在群名称映射中填写）"
        allowed = "允许发送" if self.policy.allows(group_id) else "已被群过滤器拦截"
        yield event.plain_result(
            "QQ群通知信息\n"
            f"群 OpenID：{group_id}\n"
            f"群名称：{group_name}\n"
            f"过滤结果：{allowed}\n"
            f"过滤模式：{self.policy.filter_mode}"
        )

    def _notice_enabled(self, notice_type: str) -> bool:
        key = {
            "bot_join": "enable_bot_join",
            "member_join": "enable_member_join",
            "member_leave": "enable_member_leave",
        }.get(notice_type)
        return bool(key and self.config.get(key, True))

    def _template(self, notice_type: str) -> str:
        defaults = {
            "bot_join": "大家好，云云来啦～以后请多关照。",
            "member_join": "欢迎 {member_at} 加入 {group_display}！",
            "member_leave": "{member_display} 已退出 {group_display}。",
        }
        key = {
            "bot_join": "bot_join_message",
            "member_join": "member_join_message",
            "member_leave": "member_leave_message",
        }.get(notice_type, "")
        return _text(self.config.get(key, defaults.get(notice_type, "")))

    @staticmethod
    def _bot_name(adapter: Any) -> str:
        client = getattr(adapter, "client", None)
        robot = getattr(client, "robot", None)
        return _first_attr(robot, "username", "name", "nick") or "机器人"

    def _template_values(
        self,
        notice_type: str,
        event: Any,
        adapter: Any,
    ) -> dict[str, str]:
        raw = _raw_event_data(event)
        group_id = _first_attr(event, "group_openid", "group_id") or _text(
            raw.get("group_openid") or raw.get("group_id")
        )
        member_id = _first_attr(
            event,
            "member_openid",
            "user_openid",
            "openid",
        ) or _text(
            raw.get("member_openid")
            or raw.get("user_openid")
            or raw.get("openid")
        )
        operator_id = _first_attr(
            event,
            "op_member_openid",
            "operator_openid",
        ) or _text(raw.get("op_member_openid") or raw.get("operator_openid"))

        member_name = self.names.member_name(group_id, member_id, raw)
        operator_name = self.names.operator_name(group_id, operator_id, raw)
        group_name = self.names.group_name(group_id, raw)
        member_display = member_name or member_id or "未知成员"
        operator_display = operator_name or operator_id or "未知操作人"
        group_display = group_name or group_id or "当前群聊"
        event_id = _first_attr(event, "event_id") or _text(raw.get("event_id"))
        timestamp = _first_attr(event, "timestamp") or _text(raw.get("timestamp"))

        return {
            "event_type": notice_type,
            "event_id": event_id,
            "event_time": _format_time(timestamp),
            "timestamp": timestamp,
            "group_id": group_id,
            "group_openid": group_id,
            "group_name": group_name or group_id,
            "group_nickname": group_name or group_id,
            "group_display": group_display,
            "member_openid": member_id,
            "user_id": member_id,
            "user_openid": member_id,
            "member_nickname": member_name or member_id,
            "user_nickname": member_name or member_id,
            "member_display": member_display,
            "member_at": (
                f'<qqbot-at-user id="{member_id}" />' if member_id else ""
            ),
            "operator_openid": operator_id,
            "op_member_openid": operator_id,
            "operator_nickname": operator_name or operator_id,
            "operator_display": operator_display,
            "operator_at": (
                f'<qqbot-at-user id="{operator_id}" />' if operator_id else ""
            ),
            "bot_name": self._bot_name(adapter),
        }

    async def _handle_notice(self, notice_type: str, event: Any, adapter: Any) -> None:
        values = self._template_values(notice_type, event, adapter)
        group_id = values["group_id"]
        event_id = values["event_id"]
        dedup_key = event_id or "|".join(
            (
                notice_type,
                group_id,
                values["member_openid"],
                values["operator_openid"],
                values["timestamp"],
            )
        )
        if self.seen.is_duplicate(dedup_key):
            if self.debug:
                logger.info(f"[QQ群通知] 跳过重复事件：{dedup_key}")
            return
        if not self._notice_enabled(notice_type) or not self.policy.allows(group_id):
            if self.debug:
                logger.info(
                    f"[QQ群通知] 事件被开关或群过滤器忽略：type={notice_type}, group={group_id}"
                )
            return

        template = self._template(notice_type)
        content = SafeTemplate.render(template, values)
        if not content:
            if self.debug:
                logger.info(f"[QQ群通知] 消息模板为空，跳过：type={notice_type}")
            return
        api = getattr(event, "_api", None) or getattr(
            getattr(adapter, "client", None), "api", None
        )
        if api is None or not hasattr(api, "post_group_message"):
            logger.error("[QQ群通知] QQ 官方发送 API 尚未就绪。")
            return

        uses_at = "<qqbot-at-user" in content
        payload: dict[str, Any] = {"group_openid": group_id}
        if uses_at:
            # QQ 官方的新 @ 标签用 Markdown 发送最稳定；普通文本可能显示裸 ID。
            payload.update(msg_type=2, markdown={"content": content})
        else:
            payload.update(msg_type=0, content=content)
        # QQ 群消息接口不接受 GROUP_MEMBER_REMOVE 作为被动回复事件，
        # 退群通知必须走主动消息；入群打招呼/欢迎仍保留事件上下文。
        if event_id and notice_type != "member_leave":
            payload["event_id"] = event_id
        try:
            await api.post_group_message(**payload)
            logger.info(
                f"[QQ群通知] 已发送：type={notice_type}, group={group_id}, event={event_id or '-'}"
            )
        except TypeError:
            # 兼容不接受 event_id 的旧版 SDK；退化成主动群消息。
            payload.pop("event_id", None)
            await api.post_group_message(**payload)
            logger.info(
                f"[QQ群通知] 已用兼容模式发送：type={notice_type}, group={group_id}"
            )
        except Exception as exc:
            if uses_at:
                fallback_values = {
                    **values,
                    "member_at": values["member_display"],
                    "operator_at": values["operator_display"],
                }
                fallback_content = SafeTemplate.render(template, fallback_values)
                fallback_payload: dict[str, Any] = {
                    "group_openid": group_id,
                    "msg_type": 0,
                    "content": fallback_content,
                }
                if event_id and notice_type != "member_leave":
                    fallback_payload["event_id"] = event_id
                try:
                    await api.post_group_message(**fallback_payload)
                    logger.warning(
                        f"[QQ群通知] Markdown @ 发送失败，已降级为普通文本："
                        f"type={notice_type}, group={group_id}, error={exc}"
                    )
                    return
                except Exception as fallback_exc:
                    exc = fallback_exc
            logger.error(
                f"[QQ群通知] 发送失败：type={notice_type}, group={group_id}, error={exc}"
            )

    async def terminate(self) -> None:
        await self.bridge.uninstall()
        logger.info("[QQ群通知] 插件已卸载，事件桥已经收好。")
