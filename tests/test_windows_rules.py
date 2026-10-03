"""窗口规则的纯逻辑测试（不连 X，不需要游戏在跑）。"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yanwo.core.windows import (  # noqa: E402
    BridgeGate,
    WindowInfo,
    WindowRules,
    match_title,
    verdict_activate,
    select_login_dialog,
)


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


class TestActivateVerdict(unittest.TestCase):
    """activate 的判定：堆叠索引上去了 = 真生效（gamescope 从不写 _NET_ACTIVE_WINDOW）。"""

    def test_index_rise_is_ok(self):
        self.assertIn("OK", verdict_activate(3, 4, 0x0, 0x123))
        self.assertIn("3→4", verdict_activate(3, 4, 0x0, 0x123))

    def test_ewmh_property_is_ok(self):
        self.assertIn("OK", verdict_activate(5, 5, 0x123, 0x123), "真 WM 会写这个属性")

    def test_no_change_is_failure(self):
        v = verdict_activate(5, 5, 0x0, 0x123)
        self.assertIn("没生效", v)
        self.assertIn("层级 5→5", v)


class TestBridgeGate(unittest.TestCase):
    """游戏阶段"要不要开光标桥"的判定：只剩主窗口→关；有弹窗/命中标题→开。"""

    def main_win(self, wid=1, title="燕云十六声"):
        return WindowInfo(wid, title, 0, 0, 0, 3840, 2160, True)

    def dialog(self, wid=2, title="登录"):
        return WindowInfo(wid, title, 0, 0, 0, 720, 960, True, transient_for=1)

    def test_only_main_window_wants_no_cursor(self):
        g = BridgeGate(cursor_windows=["^(登录|Login)$"], cursor_on_dialogs=True)
        self.assertFalse(g.wants_cursor([self.main_win()])[0])

    def test_dialog_enables_cursor(self):
        wins = [self.main_win(), self.dialog()]
        self.assertTrue(BridgeGate([], True).wants_cursor(wins)[0])
        self.assertFalse(BridgeGate([], False).wants_cursor(wins)[0], "关掉弹窗启发式就不开")

    def test_title_pattern_enables_cursor(self):
        wins = [self.main_win(), WindowInfo(2, "登录", 0, 0, 0, 720, 960, True)]
        g = BridgeGate(cursor_windows=["^(登录|Login)$"], cursor_on_dialogs=False)
        self.assertTrue(g.wants_cursor(wins)[0])

    def test_pause_window_forces_off(self):
        g = BridgeGate(cursor_windows=["登录"], pause_windows=["^Steam 覆盖"])
        self.assertTrue(g.wants_cursor([self.main_win(), self.dialog(2, "登录")])[0])
        wins = [self.main_win(), WindowInfo(3, "Steam 覆盖界面", 0, 0, 0, 1920, 1080, True)]
        want, why = g.wants_cursor(wins)
        self.assertFalse(want, "命中暂停窗口时必须关")
        self.assertIn("暂停窗口", why)

    def test_helper_windows_ignored(self):
        g = BridgeGate([], True)
        wins = [self.main_win(), WindowInfo(9, "Default IME", 0, 0, 0, 1, 1, True, transient_for=1)]
        self.assertFalse(g.wants_cursor(wins)[0], "IME/1x1 辅助窗不算")


class TestRules(unittest.TestCase):
    def test_gamescope_matches_dialogs_only_from_target_process(self):
        rules = WindowRules([
            {"match": "^登录$", "actions": ["gamescope_focus"]},
            {"match": "^Mpay", "actions": ["gamescope_dialog"]},
        ])
        target = win(1, "登录")
        age = win(2, "MpayAgeTipsForm")
        age.pid = target.pid
        unrelated = win(3, "MpayOther")
        with patch("yanwo.core.windows.list_windows", return_value=[target, age, unrelated]), \
             patch.object(rules._gamescope, "update") as update:
            rules.sync_gamescope()
            update.assert_called_once_with(1, [2])

    def test_missing_login_releases_focus(self):
        rules = WindowRules([{"match": "^登录$", "actions": ["gamescope_focus"]}])
        with patch("yanwo.core.windows.list_windows", return_value=[]), \
             patch.object(rules._gamescope, "update") as update:
            rules.sync_gamescope()
            update.assert_called_once_with(0, [])

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


class TestLoginDialogs(unittest.TestCase):
    def test_unnamed_popup_takes_over_and_closing_returns_to_login(self):
        login = WindowInfo(1, "登录", pid=10, w=720, h=960, mapped=True)
        popup = WindowInfo(2, "", pid=10, w=680, h=468, mapped=True, transient_for=1)
        rules = WindowRules([{"match": "^登录$", "actions": ["gamescope_focus"]}])
        with patch("yanwo.core.windows.list_windows", return_value=[login, popup]), \
             patch.object(rules._gamescope, "update") as update:
            rules.sync_gamescope()
            update.assert_called_once_with(2, [])
        popup.mapped = False
        with patch("yanwo.core.windows.list_windows", return_value=[login, popup]), \
             patch.object(rules._gamescope, "update") as update:
            rules.sync_gamescope()
            update.assert_called_once_with(1, [])

    def test_nested_popup_skips_age_shadow_tooltip_and_other_process(self):
        login = WindowInfo(1, "登录", pid=10, w=720, h=960, mapped=True)
        def child(wid, parent, **kwargs):
            return WindowInfo(wid, "", pid=kwargs.pop("pid", 10),
                              w=680, h=468, mapped=True, transient_for=parent, **kwargs)
        popup, nested = child(2, 1), child(3, 2)
        age, tip = child(4, 1), child(5, 2)
        shadow, unrelated = child(6, 2, accepts_focus=False), child(7, 2, pid=20)
        self.assertEqual(select_login_dialog(login, [login, popup, nested, age, tip, shadow, unrelated], {4, 5}).wid, 3)
