import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from yanwo.core.focus_watch import BaseLayerWatch


class TestBaseLayerWatch(unittest.TestCase):
    def test_compositor_pin_validates_window_on_owning_server(self):
        owner = SimpleNamespace(target=123)
        watch = BaseLayerWatch(owner, [])
        compositor = MagicMock(dpy=10, root=1)
        compositor._raw_prop.return_value = b'\0' * 4
        game = MagicMock()
        game._mapped.return_value = True
        watch.window_connection = game
        watch.repair(compositor, 5)
        game._mapped.assert_called_once_with(123)
        compositor._mapped.assert_not_called()
        args = compositor.lib.XChangeProperty.call_args.args
        self.assertEqual(ctypes.cast(args[6], ctypes.POINTER(ctypes.c_ulong)).contents.value, 123)

    def test_preserves_external_nonzero_pin(self):
        watch = BaseLayerWatch(SimpleNamespace(target=123), [])
        conn = MagicMock()
        conn._raw_prop.return_value = (456).to_bytes(4, 'little')
        watch.repair(conn, 5)
        conn.lib.XChangeProperty.assert_not_called()

    def test_does_not_restore_destroyed_window(self):
        watch = BaseLayerWatch(SimpleNamespace(target=123), [])
        conn = MagicMock()
        conn._raw_prop.return_value = b'\0' * 4
        conn._mapped.return_value = False
        watch.repair(conn, 5)
        conn.lib.XChangeProperty.assert_not_called()
