import os
import shutil
import tempfile
import unittest
from unittest import mock
from ghost_fork import GhostVFS, CommitFailedError

class TestGhostVFS(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.main_file = os.path.join(self.test_dir, "main.py")
        with open(self.main_file, "w") as f:
            f.write("def calculate(): return 42\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_speculative_read_write(self):
        vfs = GhostVFS(self.test_dir)
        session = vfs.fork()

        # Read original
        original = session.read("main.py")
        self.assertIn("return 42", original)

        # Speculative edit
        session.write("main.py", "def calculate(): return 100\n")
        self.assertIn("return 100", session.read("main.py"))

        # Physical disk MUST still have 42 (Isolation)
        with open(self.main_file, "r") as f:
            self.assertIn("return 42", f.read())

    def test_rollback_on_broken_refactor(self):
        vfs = GhostVFS(self.test_dir)
        session = vfs.fork()

        # Agent introduces broken syntax or failing test
        session.write("main.py", "broken syntax error ((\n")

        # Validator checks syntax
        def check_syntax(s):
            code = s.read("main.py")
            try:
                compile(code, "main.py", "exec")
                return True
            except SyntaxError:
                return False

        with self.assertRaises(CommitFailedError):
            session.verify_and_commit(validator_fn=check_syntax)

        # Physical file MUST remain intact
        with open(self.main_file, "r") as f:
            self.assertIn("return 42", f.read())

    def test_staging_failure_leaves_disk_completely_untouched(self):
        # This is the exact scenario that used to leave a half-mutated tree
        # on disk: a multi-file commit where a later file's directory can't
        # be created because a file already occupies that path — a real,
        # plausible OS-level failure, not a contrived one. Before the fix,
        # the first file's new content was already written to disk by the
        # time the second file's failure raised, uncaught, out of
        # verify_and_commit.
        vfs = GhostVFS(self.test_dir)
        blocked_dir = os.path.join(self.test_dir, "blocked")
        os.makedirs(blocked_dir, exist_ok=True)
        with open(os.path.join(blocked_dir, "file_not_dir"), "w") as f:
            f.write("occupies the path a later write needs as a directory")

        session = vfs.fork()
        session.write("main.py", "def calculate(): return 999\n")
        session.write("blocked/file_not_dir/c.py", "unreachable\n")

        with self.assertRaises(CommitFailedError):
            session.verify_and_commit(validator_fn=lambda s: True)

        # main.py must be untouched on disk -- not "restored", never written.
        with open(self.main_file, "r") as f:
            self.assertIn("return 42", f.read())

    def test_apply_phase_failure_rolls_back_already_applied_files(self):
        # Staging can succeed for every file (all temp files written
        # cleanly) and the failure can still happen in the apply phase
        # itself -- e.g. a concurrent process holding a file, a permissions
        # change between staging and apply, a cross-device rename. Forces
        # that deterministically via a mocked os.replace that fails on the
        # second of two renames, and proves the first one gets rolled back
        # rather than left applied while the commit as a whole fails.
        vfs = GhostVFS(self.test_dir)
        session = vfs.fork()
        session.write("main.py", "def calculate(): return 999\n")
        session.write("new_file.py", "SHOULD_NOT_SURVIVE_A_FAILED_COMMIT\n")

        real_replace = os.replace
        call_count = {"n": 0}

        def flaky_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated failure applying the second file")
            return real_replace(src, dst)

        with mock.patch("ghost_fork.vfs.os.replace", side_effect=flaky_replace):
            with self.assertRaises(CommitFailedError):
                session.verify_and_commit(validator_fn=lambda s: True)

        # main.py (the first, already-applied rename) must be rolled back
        # to its pre-commit content, not left at its new value.
        with open(self.main_file, "r") as f:
            self.assertIn("return 42", f.read())
        # new_file.py's rename never got to run at all.
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "new_file.py")))

    def test_successful_atomic_commit(self):
        vfs = GhostVFS(self.test_dir)
        session = vfs.fork()

        session.write("main.py", "def calculate(): return 200\n")
        session.write("utils.py", "def helper(): return 'ok'\n")

        committed = session.verify_and_commit(validator_fn=lambda s: True)
        self.assertEqual(committed, 2)

        # Verify physical disk updated atomically
        with open(self.main_file, "r") as f:
            self.assertIn("return 200", f.read())

        utils_file = os.path.join(self.test_dir, "utils.py")
        self.assertTrue(os.path.exists(utils_file))

if __name__ == "__main__":
    unittest.main()
