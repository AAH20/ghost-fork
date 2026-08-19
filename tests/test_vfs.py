import os
import shutil
import tempfile
import unittest
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
