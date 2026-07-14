from __future__ import annotations

import types
import unittest

from core.bridge import QQOfficialNoticeBridge
from core.events import QQGroupMemberEvent


class FakeClient:
    def __init__(self):
        self.original_calls = 0
        self.intents = 1 << 25

    async def on_group_add_robot(self, event):
        self.original_calls += 1


class FakeAdapter:
    def __init__(self, client):
        self.client = client

    def meta(self):
        return types.SimpleNamespace(name="qq_official")


class FakeManager:
    def __init__(self, adapters):
        self.adapters = adapters

    def get_insts(self):
        return self.adapters


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_binding_chains_original_and_restores_it(self):
        received = []

        async def handler(kind, event, adapter):
            received.append((kind, event, adapter))

        client = FakeClient()
        original = client.on_group_add_robot
        adapter = FakeAdapter(client)
        context = types.SimpleNamespace(platform_manager=FakeManager([adapter]))
        bridge = QQOfficialNoticeBridge(handler, lambda _: None)

        self.assertEqual(await bridge.bind_platforms(context), 1)
        self.assertTrue(client.intents & bridge.GROUP_MEMBER_INTENT)
        event = object()
        await client.on_group_add_robot(event)
        self.assertEqual(received[0][:2], ("bot_join", event))
        self.assertEqual(client.original_calls, 1)

        await bridge.uninstall()
        self.assertFalse(client.intents & bridge.GROUP_MEMBER_INTENT)
        await client.on_group_add_robot(event)
        self.assertEqual(client.original_calls, 2)
        self.assertEqual(client.on_group_add_robot.__func__, original.__func__)

    async def test_binding_preserves_existing_intents(self):
        async def handler(kind, event, adapter):
            return None

        client = FakeClient()
        client.intents |= 1 << 30
        adapter = FakeAdapter(client)
        bridge = QQOfficialNoticeBridge(handler, lambda _: None)

        await bridge.bind_platforms(
            types.SimpleNamespace(platform_manager=FakeManager([adapter]))
        )

        self.assertTrue(client.intents & (1 << 25))
        self.assertTrue(client.intents & (1 << 30))
        self.assertTrue(client.intents & bridge.GROUP_MEMBER_INTENT)
        await bridge.uninstall()

    async def test_binding_is_idempotent(self):
        async def handler(kind, event, adapter):
            return None

        client = FakeClient()
        context = types.SimpleNamespace(platform_manager=FakeManager([FakeAdapter(client)]))
        bridge = QQOfficialNoticeBridge(handler, lambda _: None)
        self.assertEqual(await bridge.bind_platforms(context), 1)
        self.assertEqual(await bridge.bind_platforms(context), 0)
        await bridge.uninstall()

    async def test_hot_reload_adds_and_removes_existing_connection_parsers(self):
        async def handler(kind, event, adapter):
            return None

        dispatched = []
        state = types.SimpleNamespace(
            api="api",
            _dispatch=lambda name, event: dispatched.append((name, event)),
        )
        connection = types.SimpleNamespace(parser={}, state=state)
        client = FakeClient()
        client._connection = connection
        context = types.SimpleNamespace(platform_manager=FakeManager([FakeAdapter(client)]))
        bridge = QQOfficialNoticeBridge(handler, lambda _: None)

        await bridge.bind_platforms(context)
        self.assertIn("group_member_add", connection.parser)
        connection.parser["group_member_add"](
            {"id": "evt", "d": {"group_openid": "g", "member_openid": "u"}}
        )
        self.assertEqual(dispatched[0][0], "group_member_add")

        await bridge.uninstall()
        self.assertNotIn("group_member_add", connection.parser)
        self.assertNotIn("group_member_remove", connection.parser)

    def test_member_parser_preserves_payload_fields(self):
        dispatched = []
        state = types.SimpleNamespace(
            api="api",
            _dispatch=lambda name, event: dispatched.append((name, event)),
        )
        parser = QQOfficialNoticeBridge._member_parser("GROUP_MEMBER_ADD")
        parser(
            state,
            {
                "id": "evt",
                "d": {
                    "group_openid": "group",
                    "member_openid": "member",
                    "op_member_openid": "operator",
                    "nickname": "新人",
                },
            },
        )
        name, event = dispatched[0]
        self.assertEqual(name, "group_member_add")
        self.assertIsInstance(event, QQGroupMemberEvent)
        self.assertEqual(event.event_id, "evt")
        self.assertEqual(event.group_openid, "group")
        self.assertEqual(event.raw_data["nickname"], "新人")


if __name__ == "__main__":
    unittest.main()
