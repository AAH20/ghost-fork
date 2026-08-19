# Ghost-Fork

An in-memory, copy-on-write shadow workspace for speculative multi-file
edits, with a validate-then-commit workflow for autonomous coding agents.

[![CI](https://github.com/AAH20/ghost-fork/actions/workflows/ci.yml/badge.svg)](https://github.com/AAH20/ghost-fork/actions)
[![License](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](LICENSE-MIT)

An earlier version of this repo claimed an atomic multi-file commit that
wasn't actually atomic — proven by reproducing the exact failure it claimed
to prevent, not by inspection. Fixed for real:

- **The "atomic commit" wrote files directly, one at a time, with no
  staging.** A real OS-level failure partway through a multi-file commit
  (a blocked path, a full disk, a permissions error) left files already
  written in that loop on disk, with the exception propagating uncaught —
  the exact half-mutated-tree failure mode this tool exists to prevent,
  just moved into its own commit step. Reproduced directly: a two-file
  commit where the second file's directory couldn't be created left the
  first file's new content on disk with no recovery.
- **Fixed with a real two-phase commit**, not a rename: phase one stages
  every write to a temp file next to its real target and reads the
  pre-commit content of every file the commit will touch — nothing on the
  physical disk is touched in this phase, so a staging failure now leaves
  disk provably untouched (this is what
  `test_staging_failure_leaves_disk_completely_untouched` proves). Phase
  two applies via `os.replace` (atomic rename on the same filesystem); if
  a later file's apply step fails, everything already applied in that
  phase is rolled back to its pre-commit content — proven by
  `test_apply_phase_failure_rolls_back_already_applied_files`, which
  deterministically fails the second of two renames via fault injection
  and confirms the first one gets restored rather than left applied while
  the commit as a whole fails.
- **`pip install ghost-fork` never worked** — never published to PyPI. The
  Quickstart installs from source instead.
- **`pydantic` and `typing_extensions` were listed as dependencies and
  never imported anywhere** — removed; zero third-party runtime
  dependencies. Also cleaned up unused imports (`shutil`, `time`, `Any`,
  `field`) that were never referenced either.
- **The OpenHands #14370 citation is real but unrelated** — checked its
  actual title ("ACP settings: preserve LLM/condenser/MCP config across
  OpenHands ↔ ACP toggles"); it's about settings persistence, not broken
  git trees from partial multi-file edits. Removed. The Aider citations
  (#291 "Add /rollback command", #1018 "Undo prompt command") are real and
  genuinely on-topic; kept.
- **The unsourced "$25,000+ per incident" figure and the "Commercial
  Integration with A2Z SOC" section had no basis in this repo** — no
  calculator producing that number, no code talking to a2zsoc.com. Both
  removed.
- **"Zero-overhead" is gone** — reading a file's full content into a Python
  string, per file, is real memory overhead, not zero. It's small and
  reasonable for a coding-agent workspace's typical file sizes, which is a
  fair claim; "zero" wasn't.

## What's actually here

```
ghost-fork/
├── ghost_fork/
│   ├── __init__.py   # Package exports
│   └── vfs.py        # SpeculativeSession (CoW shadow workspace, two-phase commit) + GhostVFS (factory)
└── tests/
    └── test_vfs.py    # Isolation, rollback-on-validation-failure, staging-failure safety, apply-failure rollback, successful commit
```

## Try it

```bash
git clone https://github.com/AAH20/ghost-fork.git && cd ghost-fork
pip install -e .
python -m unittest tests.test_vfs -v
```

```python
from ghost_fork import GhostVFS, CommitFailedError

vfs = GhostVFS(root_dir=".")
session = vfs.fork()

session.write("src/core.py", "def new_feature(): return True\n")
session.write("src/utils.py", "import core\n")

def validate_refactor(s):
    try:
        compile(s.read("src/core.py"), "core.py", "exec")
        compile(s.read("src/utils.py"), "utils.py", "exec")
        return True
    except SyntaxError:
        return False

# validate_refactor above only checks syntax, not tests — pass your own
# validator_fn that actually runs your test suite for real pre-commit
# verification; the API takes any callable, this is just the minimal example.
committed_count = session.verify_and_commit(validator_fn=validate_refactor)
print(f"Committed {committed_count} files to disk.")
```

## Honest scope

- The commit protocol is genuinely two-phase and provably safe against
  failures during staging (nothing on disk is touched) and against
  failures during apply (already-applied files in that same commit are
  rolled back). What it is not is crash-safe against the process itself
  being killed *between* two apply-phase operations — recovering from that
  would need a persistent write-ahead log surviving process restart, which
  this in-memory-only tool doesn't have. That window is now a handful of
  fast `os.replace`/`os.remove` calls per commit, not the full, slower
  content-write loop it used to be, but it isn't mathematically zero.
- Not published to PyPI. Install from source (see above).
- The CoW model copies whole-file content into memory strings on first
  read; fine for typical source files, not designed for huge files.

## License

MIT OR Apache-2.0
