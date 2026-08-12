"""
test_assoc.py
=============
Unit tests for the Windows file-association helpers in hvsr_gui_assoc.

A fake ``winreg`` is injected through ``sys.modules`` so the tests never
touch the real registry on the machine running them.
Run:  python test_assoc.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))


class _Key:
    """A fake registry key handle (context manager like winreg's)."""

    def __init__(self, reg, path):
        self._reg = reg
        self._path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _navigate(reg, path):
    node = reg.tree
    for part in path.split("\\"):
        node = node.get(part)
        if node is None:
            raise OSError("key not found: " + path)
    return node


class FakeWinreg:
    """In-memory winreg stand-in: keys are dicts, values are strings."""

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.tree = {}

    def CreateKey(self, root, path):
        node = self.tree
        for part in path.split("\\"):
            node = node.setdefault(part, {})
        return _Key(self, path)

    def OpenKey(self, root, path):
        _navigate(self, path)
        return _Key(self, path)

    def SetValueEx(self, key, name, res, typ, value):
        node = self.tree
        for part in key._path.split("\\"):
            node = node.setdefault(part, {})
        node[name] = value

    def QueryValueEx(self, key, name):
        return _navigate(self, key._path)[name], FakeWinreg.REG_SZ

    def DeleteKey(self, root, path):
        parts = path.split("\\")
        node = self.tree
        for part in parts[:-1]:
            node = node[part]
        try:
            del node[parts[-1]]
        except KeyError:
            raise OSError("key not found: " + path)

    def EnumKey(self, key, index):
        node = _navigate(self, key._path)
        subkeys = [k for k, v in node.items() if isinstance(v, dict)]
        if index >= len(subkeys):
            raise OSError("no more keys")
        return subkeys[index]


class TestFileAssoc(unittest.TestCase):
    def setUp(self):
        import hvsr_gui_assoc
        self.mod = hvsr_gui_assoc
        self.fake = FakeWinreg()
        self._orig = sys.modules.get("winreg")
        sys.modules["winreg"] = self.fake

    def tearDown(self):
        if self._orig is None:
            sys.modules.pop("winreg", None)
        else:
            sys.modules["winreg"] = self._orig

    def test_disabled_by_default(self):
        self.assertFalse(self.mod.assoc_enabled())

    def test_roundtrip_registers_and_cleans_up(self):
        self.mod.set_assoc(True)
        self.assertTrue(self.mod.assoc_enabled())
        classes = self.fake.tree["Software"]["Classes"]
        # every extension maps to the ProgID
        for ext in (".eqd", ".sg2", ".mseed", ".miniseed"):
            self.assertEqual(classes[ext][""], "HVSR_Analyzer")
        # the ProgID carries the open command
        cmd = classes["HVSR_Analyzer"]["shell"]["open"]["command"][""]
        self.assertIn("%1", cmd)

        self.mod.set_assoc(False)
        self.assertFalse(self.mod.assoc_enabled())
        classes = self.fake.tree["Software"]["Classes"]
        for ext in (".eqd", ".sg2", ".mseed", ".miniseed"):
            self.assertNotIn(ext, classes)
        self.assertNotIn("HVSR_Analyzer", classes)

    def test_source_command_launches_main_py(self):
        # running from source the shell command must point pythonw at
        # src/main.py, otherwise double-clicking would open a bare python
        cmd = self.mod._command()
        self.assertIn("main.py", cmd)
        self.assertIn("%1", cmd)
        self.assertIn("pythonw", cmd)

    def test_cleanup_is_idempotent(self):
        # unregistering when nothing was ever registered must not raise
        self.mod.set_assoc(False)
        self.assertFalse(self.mod.assoc_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
