"""手柄桥的单元测试（不需要真的手柄）。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yanwo.input.jsdevice import RawEvent, TYPE_AXIS, TYPE_BUTTON  # noqa: E402
from yanwo.input.mapper import Mapper  # noqa: E402
from yanwo.input.profile import Profile  # noqa: E402


def btn(n: int, pressed: bool = True) -> RawEvent:
    return RawEvent(0, 1 if pressed else 0, TYPE_BUTTON, n)


def axis(n: int, v: int) -> RawEvent:
    return RawEvent(0, v, TYPE_AXIS, n)


class TestProfile(unittest.TestCase):
    def test_defaults_match_xbox(self):
        p = Profile()
        self.assertEqual((p.axis_move_x, p.axis_move_y), (0, 1), "左摇杆=主光标轴")
        self.assertEqual((p.axis_move_x2, p.axis_move_y2), (3, 4), "右摇杆=副光标轴")
        self.assertEqual((p.btn_confirm, p.btn_back), (0, 1))
        self.assertEqual((p.axis_hat_x, p.axis_hat_y), (6, 7))

    def test_roundtrip(self):
        p = Profile()
        p.speed_px_s = 999
        p.btn_confirm = 5
        toml = p.to_toml()
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "x.toml")
            f.write_text(toml, encoding="utf-8")
            q = Profile.load(f)
        self.assertEqual(q.speed_px_s, 999)
        self.assertEqual(q.btn_confirm, 5)


class TestMapper(unittest.TestCase):
    def setUp(self):
        self.p = Profile()
        self.m = Mapper(self.p)

    def test_button_edges(self):
        self.assertEqual(self.m.feed(btn(0, True)), [("confirm", 1)])
        self.assertEqual(self.m.feed(btn(0, True)), [], "重复按下要忽略")
        self.assertEqual(self.m.feed(btn(0, False)), [], "松开不产生意图")
        self.assertEqual(self.m.feed(btn(0, True)), [("confirm", 1)], "松开后可以再按")
        self.assertEqual(self.m.feed(btn(1, True)), [("back", 1)])

    def test_unknown_button(self):
        self.assertEqual(self.m.feed(btn(9, True)), [("button", 9)])

    def test_deadzone(self):
        # 默认 profile 的"移光标"轴是右摇杆（pointer_stick = "right"）
        self.m.feed(axis(self.p.axis_move_x2, 100))
        self.assertEqual(self.m.cursor_velocity(), (0.0, 0.0))
        self.m.feed(axis(self.p.axis_move_x2, 32767))
        vx, vy = self.m.cursor_velocity()
        self.assertGreater(vx, 0.9)
        self.assertEqual(vy, 0.0)

    def test_nav_hat(self):
        self.assertEqual(self.m.nav_step(), 0)
        self.m.feed(axis(self.p.axis_hat_y, -32767))
        self.assertEqual(self.m.nav_step(), -1, "第一次应立刻响应")
        self.assertEqual(self.m.nav_step(), 0, "同一方向不应立刻重复")
        self.m.feed(axis(self.p.axis_hat_y, 0))
        self.assertEqual(self.m.nav_step(), 0)
        self.m.feed(axis(self.p.axis_hat_y, 32767))
        self.assertEqual(self.m.nav_step(), 1)

    def test_left_stick_does_not_move_cursor_by_default(self):
        """默认只用右摇杆：左摇杆留给 Steam 覆盖界面/切窗口（2026-10-04 决定）。"""
        self.m.feed(axis(self.p.axis_move_x, 32767))
        self.assertEqual(self.m.cursor_velocity(), (0.0, 0.0), "左摇杆不该动光标")
        self.m.feed(axis(self.p.axis_move_x2, 32767))
        self.assertGreater(self.m.cursor_velocity()[0], 0.9, "右摇杆要能移光标")

    def test_both_sticks_when_configured(self):
        self.m.p.pointer_stick = "both"
        self.m.feed(axis(self.p.axis_move_x, 32767))
        self.assertGreater(self.m.cursor_velocity()[0], 0.9, "设为 both 时左摇杆也能移")
        self.m.feed(axis(self.p.axis_move_x, 0))
        self.m.feed(axis(self.p.axis_move_x2, 32767))
        self.assertGreater(self.m.cursor_velocity()[0], 0.9, "右摇杆也能移")

    def test_left_stick_nav_can_be_disabled(self):
        self.m.feed(axis(self.p.axis_move_y, 32767))
        self.assertEqual(self.m.nav_step(allow_left_stick=True), 1, "Hub 里左摇杆可导航")
        self.m.feed(axis(self.p.axis_move_y, 0))
        self.m.feed(axis(self.p.axis_move_y, 32767))
        self.assertEqual(
            self.m.nav_step(allow_left_stick=False), 0,
            "启动器阶段左摇杆是移动光标，不该触发方向键",
        )

    def test_nav_repeat_disabled(self):
        self.p.nav_repeat_ms = 0
        self.m.feed(axis(self.p.axis_hat_y, 32767))
        self.assertEqual(self.m.nav_step(), 1)
        self.assertEqual(self.m.nav_step(), 1, "repeat=0 时应每次都出")

    def test_parse_init_and_normal(self):
        import struct

        from yanwo.input.jsdevice import EVENT_FMT, parse_events

        buf = struct.pack(EVENT_FMT, 1, 1, TYPE_BUTTON | 0x80, 0) + struct.pack(
            EVENT_FMT, 2, 1, TYPE_BUTTON, 3
        )
        evs, rest = parse_events(buf)
        self.assertEqual(len(evs), 2)
        self.assertTrue(evs[0].is_init, "高位的初始化事件要被标出来")
        self.assertFalse(evs[1].is_init)
        self.assertEqual(evs[1].number, 3)
        self.assertEqual(rest, b"")
        evs2, rest2 = parse_events(buf[:6])
        self.assertEqual((evs2, len(rest2)), ([], 6), "半包要留着")


class TestPointerStick(unittest.TestCase):
    """移光标用哪根摇杆（用户要求：只用右摇杆，把左摇杆让给 Steam 覆盖界面）。"""

    def mapper(self, stick):
        prof = Profile()
        prof.pointer_stick = stick
        m = Mapper(prof)
        return m

    def push(self, m, lx=0, ly=0, rx=0, ry=0):
        for num, val in ((0, lx), (1, ly), (3, rx), (4, ry)):
            m.feed(axis(num, val))
        return m.cursor_velocity()

    def test_right_only(self):
        m = self.mapper("right")
        self.assertEqual(self.push(m, lx=30000), (0.0, 0.0), "左摇杆不该动光标")
        self.assertGreater(self.push(m, rx=30000)[0], 0.5, "右摇杆要能动")

    def test_left_only(self):
        m = self.mapper("left")
        self.assertEqual(self.push(m, rx=30000), (0.0, 0.0), "右摇杆不该动光标")
        self.assertGreater(self.push(m, lx=30000)[0], 0.5)

    def test_both(self):
        m = self.mapper("both")
        self.assertGreater(self.push(m, lx=30000)[0], 0.5)
        self.assertGreater(self.push(m, rx=30000)[0], 0.5)

    def test_default_profile_is_right(self):
        self.assertEqual(Profile().pointer_stick, "right", "默认只用右摇杆")


class TestComboAndPause(unittest.TestCase):
    def test_combo_down(self):
        m = Mapper(Profile())
        self.assertFalse(m.combo_down(["select", "third"]))
        m.feed(btn(6, True))          # select
        self.assertFalse(m.combo_down(["select", "third"]))
        m.feed(btn(2, True))          # third (X)
        self.assertTrue(m.combo_down(["select", "third"]))
        m.feed(btn(2, False))
        self.assertFalse(m.combo_down(["select", "third"]))

    def test_toggle_pause_blocks_injection(self):
        from yanwo.input.daemon import InputDaemon

        calls = []
        d = InputDaemon(on_intent=lambda k, v: calls.append(k))
        d.cursor.click = lambda b=1: calls.append("click")  # type: ignore
        d.set_mode("launcher")
        d._dispatch([("confirm", 1)])
        self.assertEqual(calls, ["click"], "正常状态下要注入")
        self.assertTrue(d.toggle_pause("test"))
        d._dispatch([("confirm", 1)])
        self.assertEqual(calls, ["click"], "暂停后不能再注入")
        self.assertFalse(d.toggle_pause("test"))
        d._dispatch([("confirm", 1)])
        self.assertEqual(calls, ["click", "click"], "恢复后继续注入")


class TestDaemon(unittest.TestCase):
    def test_launcher_actions(self):
        from yanwo.input.daemon import InputDaemon

        calls: list = []
        d = InputDaemon(on_intent=lambda k, v: calls.append((k, v)))
        d.cursor.click = lambda b=1: calls.append(("click", b))  # type: ignore
        d.cursor.key = lambda k: calls.append(("key", k))  # type: ignore
        d.set_mode("launcher")
        d._dispatch([("confirm", 1), ("back", 1), ("start", 1), ("nav", -1)])
        self.assertIn(("click", 1), calls)
        self.assertIn(("click", 3), calls)
        self.assertIn(("key", "Return"), calls)
        self.assertIn(("key", "Up"), calls)

    def test_off_mode_is_silent(self):
        from yanwo.input.daemon import InputDaemon

        calls = []
        d = InputDaemon(on_intent=lambda k, v: calls.append(k))
        d.set_mode("off")
        d._dispatch([("confirm", 1), ("nav", 1)])
        self.assertEqual(calls, [])

    def test_hub_mode_forwards(self):
        from yanwo.input.daemon import InputDaemon

        calls = []
        d = InputDaemon(on_intent=lambda k, v: calls.append((k, v)))
        d.set_mode("hub")
        d._dispatch([("nav", -1), ("confirm", 1)])
        self.assertEqual(calls, [("nav", -1), ("confirm", 1)])


if __name__ == "__main__":
    unittest.main()
