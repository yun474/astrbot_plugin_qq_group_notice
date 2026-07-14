from __future__ import annotations

import unittest

from core.names import NameCache


class NameCacheTests(unittest.TestCase):
    def test_event_name_then_cache_then_empty(self):
        cache = NameCache()
        self.assertEqual(
            cache.member_name("g", "u", {"member": {"nickname": "小黑"}}),
            "小黑",
        )
        self.assertEqual(cache.member_name("g", "u"), "小黑")
        self.assertEqual(cache.member_name("g", "missing"), "")

    def test_group_alias_wins_over_event_field(self):
        cache = NameCache("g=主人快乐老家")
        self.assertEqual(cache.group_name("g", {"group_name": "事件群名"}), "主人快乐老家")

    def test_operator_name_uses_operator_specific_field(self):
        cache = NameCache()
        self.assertEqual(
            cache.operator_name("g", "op", {"operator_nickname": "管理员"}),
            "管理员",
        )


if __name__ == "__main__":
    unittest.main()
