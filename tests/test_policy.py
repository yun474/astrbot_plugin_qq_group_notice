from __future__ import annotations

import unittest

from core.policy import NoticePolicy, SafeTemplate, TTLSeenCache, parse_aliases, parse_id_set


class PolicyTests(unittest.TestCase):
    def test_id_lists_accept_commas_spaces_and_lines(self):
        self.assertEqual(parse_id_set("a,b\nc d;e"), {"a", "b", "c", "d", "e"})

    def test_blacklist_and_whitelist(self):
        blacklist = NoticePolicy.from_config(
            {"enabled": True, "group_filter_mode": "blacklist", "blacklist_groups": "bad"}
        )
        self.assertFalse(blacklist.allows("bad"))
        self.assertTrue(blacklist.allows("good"))

        whitelist = NoticePolicy.from_config(
            {"enabled": True, "group_filter_mode": "whitelist", "whitelist_groups": "good"}
        )
        self.assertTrue(whitelist.allows("good"))
        self.assertFalse(whitelist.allows("bad"))

    def test_empty_whitelist_rejects_every_group(self):
        policy = NoticePolicy.from_config(
            {"enabled": True, "group_filter_mode": "whitelist", "whitelist_groups": ""}
        )
        self.assertFalse(policy.allows("group"))

    def test_alias_parser_and_safe_template(self):
        aliases = parse_aliases("g1=一群\n# comment\ng2:二群\nbroken")
        self.assertEqual(aliases, {"g1": "一群", "g2": "二群"})
        rendered = SafeTemplate.render("欢迎 {name}，{unknown}", {"name": "云云"})
        self.assertEqual(rendered, "欢迎 云云，{unknown}")

    def test_seen_cache_expires_and_bounds(self):
        cache = TTLSeenCache(ttl_seconds=10, max_entries=16)
        self.assertFalse(cache.is_duplicate("a", now=0))
        self.assertTrue(cache.is_duplicate("a", now=1))
        self.assertFalse(cache.is_duplicate("a", now=11))


if __name__ == "__main__":
    unittest.main()
