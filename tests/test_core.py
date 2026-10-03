"""最小测试集：`./tools/tests.sh` 或 `python3 -m unittest discover -s tests`

只测不需要图形、不需要真起游戏的部分。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yanwo.core import detect, runner  # noqa: E402
from yanwo.recipe import load_recipes  # noqa: E402


class TestRecipe(unittest.TestCase):
    def test_loads(self):
        rs = load_recipes()
        self.assertTrue(rs, "至少要有一个配方")
        self.assertEqual(rs[0].id, "yysls-guofu")
        self.assertTrue(rs[0].detect_launcher and rs[0].detect_game, "detect 必须填")

    def test_vars_expanded(self):
        r = load_recipes()[0]
        p = r.steps[0].get("prefix")
        self.assertTrue(str(p).startswith(os.path.expanduser("~")), p)
        self.assertNotIn("${", str(p))


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.r = load_recipes()[0]
        self.s = self.r.steps[0]

    def test_env_separators(self):
        env = runner.build_env(self.s, self.r)
        self.assertIn(";", env["WINEDLLOVERRIDES"], "DLL 覆盖必须用 ; 分隔")
        self.assertIn("d3d12core=n,b", env["WINEDLLOVERRIDES"])
        self.assertIn(":", env["WINEDLLPATH"], "DLL 搜索路径必须用 : 分隔")
        self.assertIn("vkd3d-proton", env["WINEDLLPATH"])
        self.assertEqual(env["QT_OPENGL"], "software")
        self.assertEqual(env["QT_QUICK_BACKEND"], "software")
        self.assertTrue(env["WINEPREFIX"].endswith("/pfx"))

    def test_command(self):
        argv, cwd = runner.command_for(self.s, self.r)
        self.assertTrue(argv[0].endswith("/wine"))
        self.assertEqual(argv[1], "launcher.exe")
        self.assertTrue(cwd and os.path.isdir(cwd))

    def test_unknown_kind(self):
        from yanwo.recipe import Step

        with self.assertRaises(NotImplementedError):
            runner.command_for(Step(kind="wat"), self.r)


class TestDetect(unittest.TestCase):
    def test_no_match(self):
        self.assertEqual(detect.find(["__definitely_not_running__"]), {})

    def test_self_not_in_prefix(self):
        self.assertNotIn(os.getpid(), detect.procs_of_prefix("2885173776"))


if __name__ == "__main__":
    unittest.main()
