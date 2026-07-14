from __future__ import annotations

import types
import unittest
import sys
from pathlib import Path

_OUTPUTS_ROOT = Path(__file__).resolve().parents[2]
if str(_OUTPUTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTPUTS_ROOT))

from astrbot_plugin_qq_group_notice.core.names import NameCache  # noqa: E402
from astrbot_plugin_qq_group_notice.core.policy import (  # noqa: E402
    NoticePolicy,
    TTLSeenCache,
)
from astrbot_plugin_qq_group_notice.main import QQGroupNoticePlugin  # noqa: E402


class FakeAPI:
    def __init__(self):
        self.calls = []

    async def post_group_message(self, **payload):
        self.calls.append(payload)
        return {"id": "sent"}


class FailingMarkdownAPI(FakeAPI):
    async def post_group_message(self, **payload):
        self.calls.append(payload)
        if payload.get("msg_type") == 2:
            raise RuntimeError("markdown denied")
        return {"id": "sent"}


class MainLogicTests(unittest.IsolatedAsyncioTestCase):
    def make_plugin(self, config):
        plugin = QQGroupNoticePlugin.__new__(QQGroupNoticePlugin)
        plugin.config = config
        plugin.policy = NoticePolicy.from_config(config)
        plugin.names = NameCache(config.get("group_aliases", ""))
        plugin.seen = TTLSeenCache()
        plugin.debug = False
        return plugin

    async def test_plugin_loaded_hook_binds_existing_platforms(self):
        calls = []

        class FakeBridge:
            async def bind_platforms(self, context):
                calls.append(context)

        plugin = QQGroupNoticePlugin.__new__(QQGroupNoticePlugin)
        plugin.context = object()
        plugin.bridge = FakeBridge()

        await plugin.on_plugin_loaded(types.SimpleNamespace(name="anything"))

        self.assertEqual(calls, [plugin.context])

    def test_default_member_join_template_uses_member_at(self):
        plugin = self.make_plugin({})

        self.assertEqual(
            plugin._template("member_join"),
            "欢迎 {member_at} 加入 {group_display}！",
        )

    async def test_member_join_renders_names_and_sends_with_event_id(self):
        plugin = self.make_plugin(
            {
                "enabled": True,
                "enable_member_join": True,
                "member_join_message": "欢迎 {member_nickname} 来到 {group_name}",
                "group_aliases": "group=测试群",
            }
        )
        api = FakeAPI()
        event = types.SimpleNamespace(
            _api=api,
            event_id="evt",
            timestamp="1710000000",
            group_openid="group",
            member_openid="member",
            op_member_openid="operator",
            raw_data={"member_nickname": "新人"},
        )
        adapter = types.SimpleNamespace(
            client=types.SimpleNamespace(robot=types.SimpleNamespace(username="云云"))
        )
        await plugin._handle_notice("member_join", event, adapter)
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0]["content"], "欢迎 新人 来到 测试群")
        self.assertEqual(api.calls[0]["event_id"], "evt")

    async def test_member_at_uses_official_markdown_tag(self):
        plugin = self.make_plugin(
            {
                "enabled": True,
                "enable_member_join": True,
                "member_join_message": "欢迎 {member_at} 加入群聊",
            }
        )
        api = FakeAPI()
        event = types.SimpleNamespace(
            _api=api,
            event_id="evt-at",
            timestamp="",
            group_openid="group",
            member_openid="member",
            op_member_openid="",
            raw_data={},
        )

        await plugin._handle_notice(
            "member_join",
            event,
            types.SimpleNamespace(client=types.SimpleNamespace(robot=None)),
        )

        self.assertEqual(api.calls[0]["msg_type"], 2)
        self.assertEqual(
            api.calls[0]["markdown"]["content"],
            '欢迎 <qqbot-at-user id="member" /> 加入群聊',
        )
        self.assertNotIn("content", api.calls[0])

    async def test_member_at_falls_back_without_raw_tag(self):
        plugin = self.make_plugin(
            {
                "enabled": True,
                "enable_member_join": True,
                "member_join_message": "欢迎 {member_at} 加入群聊",
            }
        )
        api = FailingMarkdownAPI()
        event = types.SimpleNamespace(
            _api=api,
            event_id="evt-at-fallback",
            timestamp="",
            group_openid="group",
            member_openid="member",
            op_member_openid="",
            raw_data={},
        )

        await plugin._handle_notice(
            "member_join",
            event,
            types.SimpleNamespace(client=types.SimpleNamespace(robot=None)),
        )

        self.assertEqual(len(api.calls), 2)
        self.assertEqual(api.calls[1]["msg_type"], 0)
        self.assertEqual(api.calls[1]["content"], "欢迎 member 加入群聊")
        self.assertNotIn("qqbot-at-user", api.calls[1]["content"])

    async def test_blacklist_blocks_send(self):
        plugin = self.make_plugin(
            {
                "enabled": True,
                "enable_member_leave": True,
                "member_leave_message": "bye",
                "group_filter_mode": "blacklist",
                "blacklist_groups": "blocked",
            }
        )
        api = FakeAPI()
        event = types.SimpleNamespace(
            _api=api,
            event_id="evt2",
            timestamp="",
            group_openid="blocked",
            member_openid="member",
            op_member_openid="",
            raw_data={},
        )
        await plugin._handle_notice(
            "member_leave",
            event,
            types.SimpleNamespace(client=types.SimpleNamespace(robot=None)),
        )
        self.assertEqual(api.calls, [])

    async def test_member_leave_is_sent_as_proactive_message(self):
        plugin = self.make_plugin(
            {
                "enabled": True,
                "enable_member_leave": True,
                "member_leave_message": "{member_openid} 退群了",
            }
        )
        api = FakeAPI()
        event = types.SimpleNamespace(
            _api=api,
            event_id="evt-leave",
            timestamp="1710000000",
            group_openid="group",
            member_openid="member",
            op_member_openid="operator",
            raw_data={},
        )
        adapter = types.SimpleNamespace(client=types.SimpleNamespace(robot=None))

        await plugin._handle_notice("member_leave", event, adapter)

        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0]["content"], "member 退群了")
        self.assertNotIn("event_id", api.calls[0])


if __name__ == "__main__":
    unittest.main()
