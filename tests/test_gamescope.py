import unittest
from unittest.mock import patch

from yanwo.core.gamescope import GamescopeFocus


class TestGamescopeFocus(unittest.TestCase):
    def test_release_restores_previous_focus(self):
        focus = GamescopeFocus()
        focus.display = ":0"
        with patch.object(focus, "_get", side_effect=[0, 123]), patch.object(focus, "_set") as setter:
            focus.update(123)
            focus.release()
            self.assertEqual([c.args for c in setter.call_args_list], [(123,), (0,)])

    def test_release_preserves_external_change(self):
        focus = GamescopeFocus()
        focus.display, focus.target = ":0", 123
        with patch.object(focus, "_get", return_value=456), patch.object(focus, "_set") as setter:
            focus.release()
            setter.assert_not_called()

    def test_does_not_override_external_focus(self):
        focus = GamescopeFocus()
        focus.display = ":0"
        with patch.object(focus, "_get", return_value=456), patch.object(focus, "_set") as setter:
            focus.update(123)
            setter.assert_not_called()

    def test_desktop_skips_control(self):
        focus = GamescopeFocus()
        with patch.object(focus, "discover", return_value=False), patch.object(focus, "_set") as setter:
            focus.update(123)
            setter.assert_not_called()

    def test_dialog_type_is_restored(self):
        focus = GamescopeFocus()
        focus.display = ":0"
        with patch.object(focus, "_get", side_effect=[0, 123]), patch.object(focus, "_set"), \
             patch.object(focus, "_run", side_effect=[
                 "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL", "",
                 "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_DIALOG", "",
             ]) as run:
            focus.update(123, [124])
            focus.release()
            self.assertEqual(run.call_args.args[1][-1], "_NET_WM_WINDOW_TYPE_NORMAL")
            self.assertEqual(focus.types, {})

    def test_game_and_compositor_focus_are_restored_separately(self):
        focus = GamescopeFocus()
        focus.display = ":0"
        with patch.dict("os.environ", {"DISPLAY": ":1"}), \
             patch.object(focus, "_get", side_effect=[0, 0, 123, 123]), \
             patch.object(focus, "_set") as setter, patch.object(focus, "_run") as run:
            focus.update(123)
            focus.release()
            self.assertEqual([c.args for c in setter.call_args_list], [(123,), (0,)])
            self.assertEqual([c.args[0] for c in run.call_args_list], [":1", ":1"])
            self.assertEqual(run.call_args.args[1][-1], "0")
