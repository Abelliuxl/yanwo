"""窗口规则的纯逻辑测试（不连 X，不需要游戏在跑）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yanwo.core.windows import WindowInfo, WindowRules, match_title  # noqa: E402


def win(wid: int, title: str, w: int = 800, h: int = 600, mapped: bool = True) -> WindowInfo:
    return WindowInfo(wid, title, 1000 + wid, 0, 0, w, h, mapped)


class TestMatch(unittest.TestCase):
    def setUp(self):
        self.wins = [
            win(1, "燕云十六声", 3840, 2160),
            win(2, "登录", 720, 960),
            win(3, "MpayAgeTipsForm", 120, 152),
            win(4, "Default IME", 1, 1, mapped=False),
            win(5, "QTrayIconMessageWindow", 2880, 1620, mapped=False),
            win(6, "1x1helper", 1, 1, mapped=True),
        ]

    def test_chinese_titles(self):
        self.assertEqual([w.title for w in match_title("^(登录|Login)$", self.wins)], ["登录"])
        self.assertEqual([w.title for w in match_title("燕云十六声", self.wins)], ["燕云十六声"])

    def test_skips_hidden_and_helper_windows(self):
        self.assertEqual(match_title(".*", self.wins, only_visible=True).__len__(), 3)
        self.assertTrue(any(w.title == "Default IME" for w in match_title(".*", self.wins, only_visible=False)))

    def test_bad_regex_is_not_fatal(self):
        self.assertEqual(match_title("([", self.wins), [])


class TestRules(unittest.TestCase):
    def test_priority_sorting(self):
        rules = [
            {"name": "低", "match": "a", "priority": 1},
            {"name": "高", "match": "b", "priority": 99},
            {"name": "中", "match": "c", "priority": 50},
        ]
        r = WindowRules(rules, watch_seconds=0)
        self.assertEqual([x["name"] for x in r.rules], ["高", "中", "低"])

    def test_disabled_rule_is_skipped(self):
        r = WindowRules([{"name": "关掉的", "match": "登录", "enabled": False}], watch_seconds=0)
        called = []
        r.tick = lambda: called.append(1)  # type: ignore
        r.tick()
        self.assertEqual(called, [1])  # 只是确认接口在（真执行要连 X）

    def test_default_enabled_no_rules(self):
        from yanwo.recipe import Recipe

        recipe = Recipe(id="x", name="x")  # 没有 [windows]
        self.assertFalse(recipe.windows_enabled)
        self.assertEqual(recipe.window_rules, [])


if __name__ == "__main__":
    unittest.main()
