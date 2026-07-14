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


class MainLogicTests(unittest.IsolatedAsyncioTestCase):
    def make_plugin(self, config):
        plugin = QQGroupNoticePlugin.__new__(QQGroupNoticePlugin)
        plugin.config = config
        plugin.policy = NoticePolicy.from_config(config)
        plugin.names = NameCache(config.get("group_aliases", ""))
        plugin.seen = TTLSeenCache()
        plugin.debug = False
        return plugin

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


if __name__ == "__main__":
    unittest.main()
