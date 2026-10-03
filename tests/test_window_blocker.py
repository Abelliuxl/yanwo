import unittest
from unittest.mock import MagicMock, patch
from yanwo.recipe import Recipe, Step
from yanwo.core.session import Session


class TestWindowBlocker(unittest.TestCase):
    def test_worker_is_scoped_to_recipe_and_stops_its_own_process_group(self):
        recipe = Recipe(id="test", name="test", windows={"suppress_classes": ["MPAY_AGE_TIPS"]},
                        steps=[Step("wine", {"wine": "/wine", "prefix": "/isolated/pfx"})])
        process = MagicMock(pid=1234)
        session = Session(recipe, None)
        with patch("yanwo.core.session.subprocess.Popen", return_value=process) as popen:
            session._start_window_blockers()
            session._start_window_blockers()
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0][-2:], ["--suppress-window", "MPAY_AGE_TIPS"])
        self.assertEqual(popen.call_args.kwargs["env"]["WINEPREFIX"], "/isolated/pfx")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        with patch("yanwo.core.session.os.killpg") as kill:
            session._stop_window_rules()
        self.assertEqual(kill.call_args.args[0], process.pid)
        process.wait.assert_called_once_with(timeout=1)
        self.assertEqual(session._window_blockers, [])

    def test_no_worker_without_explicit_classes(self):
        session = Session(Recipe(id="test", name="test"), None)
        with patch("yanwo.core.session.subprocess.Popen") as popen:
            session._start_window_blockers()
        popen.assert_not_called()
