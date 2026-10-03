import unittest
from types import SimpleNamespace
from unittest.mock import patch

from yanwo.input.daemon import InputDaemon
from yanwo.input.steam_keyboard import SteamKeyboard


class TestSteamKeyboard(unittest.TestCase):
    def test_open_uses_native_steam_protocol(self):
        keyboard = SteamKeyboard()
        with patch("yanwo.input.steam_keyboard.shutil.which", return_value="/usr/bin/steam"), \
             patch("yanwo.input.steam_keyboard.subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            keyboard.open()
            self.assertEqual(run.call_args.args[0], ["/usr/bin/steam", keyboard.OPEN_URL])
            self.assertTrue(keyboard.requested)

    def test_only_closes_keyboard_requested_by_yanwo(self):
        keyboard = SteamKeyboard()
        with patch.object(keyboard, "_command") as command:
            keyboard.close()
            command.assert_not_called()
            keyboard.requested = True
            keyboard.close()
            command.assert_called_once_with(keyboard.CLOSE_URL)

    def test_overlay_blocks_input_and_closing_resumes_it(self):
        keyboard = SteamKeyboard()
        keyboard._input_atom = 1
        keyboard._conn = SimpleNamespace(list=lambda: [SimpleNamespace(mapped=True, wid=5)],
                                         _raw_prop=lambda *_: b"\x01\x00\x00\x00")
        self.assertTrue(keyboard.input_taken())
        keyboard._conn._raw_prop = lambda *_: b"\x00\x00\x00\x00"
        self.assertFalse(keyboard.input_taken())

    def test_request_grace_expires_without_visible_keyboard(self):
        keyboard = SteamKeyboard()
        keyboard._retry_at = 100
        with patch.object(keyboard, "_command"), patch("yanwo.input.steam_keyboard.time.monotonic", return_value=10):
            keyboard.open()
            self.assertFalse(keyboard.input_taken())
        with patch("yanwo.input.steam_keyboard.time.monotonic", return_value=14):
            self.assertFalse(keyboard.input_taken())
            self.assertFalse(keyboard.requested)

    def test_a_clicks_before_notifying_without_blocking_cursor(self):
        calls = []
        daemon = InputDaemon(on_intent=lambda kind, value: calls.append((kind, value)))
        daemon.set_mode("cursor")
        daemon.cursor.click = lambda *args: calls.append("click")
        daemon._dispatch([("confirm", 1)])
        self.assertEqual(calls, ["click", ("pointer_click", 1)])
        self.assertFalse(daemon.keyboard_active)

    def test_open_passes_field_geometry_for_native_keyboard_avoidance(self):
        keyboard = SteamKeyboard()
        with patch.object(keyboard, "_command") as command:
            keyboard.open(dict(x=75, y=348, w=501, h=36, mode=3))
            command.assert_called_once_with(
                "steam://open/keyboard?XPosition=75&YPosition=348&Width=501&Height=36&Mode=3")

    def test_keyboard_does_not_change_manual_pause(self):
        daemon = InputDaemon()
        daemon.paused = True
        daemon.keyboard_active = True
        daemon.keyboard_active = False
        self.assertTrue(daemon.paused)
