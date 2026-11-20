"""Execute the native replay overlay guard against an isolated official source fixture."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APPLIER = ROOT / "overlays/apply-cloud9-source-compat.py"
PATCH = ROOT / "overlays/responses-replay-usage.patch"
SOURCE = "open-sse/handlers/chatCore/responsesObjectToSse.ts"
HELPER = "open-sse/utils/responsesStreamHelpers.ts"
GUARD_TEST = "tests/unit/issue-19320-responses-usage-detail-counters.test.ts"
CONTRACT = "tests/unit/responses-object-replay-usage.test.ts"
INPUTS = ("package.json", SOURCE, HELPER, GUARD_TEST)

def load_guard(applier=APPLIER):
    # Execute the actual function, without running the monolithic applier's other overlays.
    tree = ast.parse(applier.read_text(), filename=str(applier))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "apply_responses_replay_usage"]
    if len(functions) != 1:
        raise AssertionError("the native replay guard must be present exactly once")
    namespace = {"__file__": str(applier)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(applier), "exec"), namespace)
    return namespace["apply_responses_replay_usage"]

class TestResponsesReplayOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get("CLOUD9_RESPONSES_REPLAY_BASELINE")
        if not value:
            raise unittest.SkipTest("requires the official source fixture; CI runs this after clone")
        cls.baseline = Path(value)
        cls.apply = staticmethod(load_guard())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "upstream"
        for name in INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.baseline / name, target)

    def snapshot(self):
        result = {}
        for name in (*INPUTS, CONTRACT):
            path = self.root / name
            if path.is_symlink():
                result[name] = ("symlink", os.readlink(path))
            elif path.exists():
                meta = path.stat()
                result[name] = (path.read_bytes(), meta.st_mode, meta.st_mtime_ns)
            else:
                result[name] = None
        return result

    def refused_without_write(self, root=None, guard=None):
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "CLOUD9_RESPONSES_REPLAY_"):
            (guard or self.apply)(root or self.root)
        self.assertEqual(self.snapshot(), before)

    def test_apply_and_repeat_are_exact_and_idempotent(self):
        self.assertEqual(self.apply(self.root), "applied")
        self.assertEqual(hashlib.sha256((self.root / SOURCE).read_bytes()).hexdigest(),
                         "5fcd4cae33e7a8e704210663103919346f0535dd20a93f299c60dd7191dd9609")
        self.assertEqual(hashlib.sha256((self.root / CONTRACT).read_bytes()).hexdigest(),
                         "6c5b089380ac417ed0f4588429a2aec6dc443022f4e32191e54c8e3040fc1649")
        after = self.snapshot()
        self.assertEqual(self.apply(self.root), "already_applied")
        self.assertEqual(self.snapshot(), after)

    def test_source_helper_and_existing_test_drift_fail_before_write(self):
        for name in (SOURCE, HELPER, GUARD_TEST):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.refused_without_write()
                path.write_bytes(original)

    def test_unqualified_version_is_refused(self):
        path = self.root / "package.json"
        package = json.loads(path.read_text())
        package["version"] = "3.8.55"
        path.write_text(json.dumps(package))
        self.refused_without_write()

    def test_mixed_source_and_contract_states_are_refused(self):
        self.apply(self.root)
        after = (self.root / SOURCE).read_bytes()
        (self.root / SOURCE).write_bytes((self.baseline / SOURCE).read_bytes())
        self.refused_without_write()
        (self.root / SOURCE).write_bytes(after)
        (self.root / CONTRACT).unlink()
        self.refused_without_write()

    def test_symlink_source_helper_and_root_are_refused(self):
        for name in (SOURCE, HELPER):
            with self.subTest(name=name):
                path = self.root / name
                backing = path.with_name(path.name + ".backing")
                path.rename(backing)
                path.symlink_to(backing.name)
                self.refused_without_write()
                path.unlink()
                backing.rename(path)
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.refused_without_write(root=alias)

    def test_entrypoint_rejects_lexical_root_symlink_before_any_write(self):
        alias = self.root.parent / "entrypoint-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        before = self.snapshot()
        result = subprocess.run([sys.executable, str(APPLIER), str(alias)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLOUD9_RESPONSES_REPLAY_SYMLINK_OR_INVALID_PARENT", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_patch_drift_is_refused_before_write(self):
        overlays = self.root.parent / "altered-overlays"
        overlays.mkdir()
        applier = overlays / APPLIER.name
        shutil.copy2(APPLIER, applier)
        (overlays / PATCH.name).write_bytes(PATCH.read_bytes() + b"\n")
        self.refused_without_write(guard=load_guard(applier))

if __name__ == "__main__":
    unittest.main()
