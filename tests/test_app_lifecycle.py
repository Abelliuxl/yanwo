import unittest
from unittest.mock import MagicMock, patch
from yanwo.__main__ import main


class TestHubExit(unittest.TestCase):
    def test_event_loop_return_still_shuts_down_session(self):
        app = MagicMock()
        with patch('yanwo.__main__.load_recipes', return_value=[object()]), \
             patch('yanwo.__main__.HubApp', return_value=app):
            self.assertEqual(main(['--fullscreen']), 0)
        app.shutdown.assert_called_once()

    def test_ui_error_still_shuts_down_session(self):
        app = MagicMock()
        app.run.side_effect = RuntimeError('UI stopped')
        with patch('yanwo.__main__.load_recipes', return_value=[object()]), \
             patch('yanwo.__main__.HubApp', return_value=app), \
             patch('yanwo.__main__.logging.getLogger'), patch('builtins.print'):
            self.assertEqual(main(['--fullscreen']), 1)
        app.shutdown.assert_called_once()
