"""React immediately when Steam clears the pinned gamescope base window."""
from __future__ import annotations
import ctypes
import select
import threading


class BaseLayerWatch(threading.Thread):
    PROPERTY = b"GAMESCOPECTRL_BASELAYER_WINDOW"

    def __init__(self, owner, displays):
        super().__init__(daemon=True, name="gamescope-base-watch")
        self.owner = owner
        self.displays = displays
        self.stopped = threading.Event()
        self.window_connection = None

    def repair(self, conn, atom):
        target = self.owner.target
        if not target:
            return
        raw = conn._raw_prop(conn.root, atom)
        # Only repair a cleared value; a different nonzero owner keeps control.
        if not raw or int.from_bytes(raw[:4], "little") != 0:
            return
        # The compositor root on :0 pins a window belonging to :1. Validate
        # it on its owning server, rather than searching :0 for a foreign XID.
        window_conn = self.window_connection or conn
        if not window_conn._mapped(target):
            return
        value = ctypes.c_ulong(target)
        conn.lib.XChangeProperty(conn.dpy, conn.root, atom, 6, 32, 0,
                                 ctypes.byref(value), 1)
        conn.lib.XFlush(conn.dpy)

    def run(self):
        # Separate X connections keep event consumption out of the window/input
        # threads. XSelectInput subscribes only this client to root properties.
        from .windows import _X
        connections = []
        try:
            for display in self.displays:
                conn = _X(display)
                lib = conn.lib
                lib.XSelectInput.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_long]
                lib.XConnectionNumber.argtypes = [ctypes.c_void_p]
                lib.XConnectionNumber.restype = ctypes.c_int
                lib.XPending.argtypes = [ctypes.c_void_p]
                lib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                lib.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                    ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
                lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
                atom = lib.XInternAtom(conn.dpy, self.PROPERTY, 0)
                lib.XSelectInput(conn.dpy, conn.root, 1 << 22)  # PropertyChangeMask
                lib.XFlush(conn.dpy)
                connections.append((conn, atom, lib.XConnectionNumber(conn.dpy)))
                if display == (self.owner.local_display or self.owner.display):
                    self.window_connection = conn
            while not self.stopped.is_set():
                ready, _, _ = select.select([fd for _, _, fd in connections], [], [], .05)
                for conn, atom, fd in connections:
                    if fd not in ready and not conn.lib.XPending(conn.dpy):
                        continue
                    event = (ctypes.c_long * 24)()
                    while conn.lib.XPending(conn.dpy):
                        conn.lib.XNextEvent(conn.dpy, ctypes.byref(event))
                    self.repair(conn, atom)
        finally:
            for conn, _, _ in connections:
                conn.lib.XCloseDisplay(conn.dpy)

    def stop(self):
        self.stopped.set()
        self.join(timeout=1)
