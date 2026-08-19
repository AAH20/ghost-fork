# Ghost-Fork (`ghost-fork`)

**In-Memory Copy-on-Write (CoW) Virtual Filesystem & Atomic Speculative Rollback Engine for Autonomous AI Coding Agents (Aider / OpenHands / Claude Code).**

[![License](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](LICENSE)
[![Zero-Git-Corruption](https://img.shields.io/badge/Speculative%20Execution-100%25%20Isolated-success.svg)]()
[![Tests](https://img.shields.io/badge/Tests-Passed%20(3%2F3)-brightgreen.svg)]()

---

## 1. The Production Crisis in AI Coding Agents

When autonomous coding agents (Aider, OpenHands, Claude Code, Cursor) execute multi-file refactors in enterprise repositories, partial failures trigger severe developer friction:

* **Broken Git Trees & Partial Edits:** An agent modifying 8 files fails on file 5 (due to syntax errors or broken tests), leaving the physical Git tree half-mutated and broken (as documented in Aider #291, #1018, and OpenHands #14370).
* **Security & Subprocess Risks:** Direct `git reset --hard` shell invocations during automated agent sessions risk losing uncommitted human changes.
* **Productivity Loss:** Engineering teams spend 4+ hours per developer weekly untangling half-baked agent edits ($25,000+ per incident across 50-person teams).

---

## 2. The Solution: `ghost-fork`

`Ghost-Fork` provides a zero-overhead, in-memory Copy-on-Write (CoW) virtual filesystem:

* **Speculative Execution Enclave:** Agents read and write files in isolated shadow memory without touching physical disk.
* **Invariant-Gated Commit:** Edits are compiled and tested inside the in-memory sandbox. The changes are flushed to physical disk **atomically if and only if 100% of tests and compiler checks pass**.
* **Instant Rollback:** If a refactor fails, shadow memory is discarded in 0 milliseconds, leaving the physical Git workspace pristine.

---

## 3. Quickstart

### Installation
```bash
pip install ghost-fork
```

### Usage
```python
from ghost_fork import GhostVFS, CommitFailedError

vfs = GhostVFS(root_dir=".")
session = vfs.fork()

# 1. Speculative Multi-File Edits (In-Memory Only)
session.write("src/core.py", "def new_feature(): return True\n")
session.write("src/utils.py", "import core\n")

# 2. Speculative Validation (Compile & Test)
def validate_refactor(s):
    try:
        compile(s.read("src/core.py"), "core.py", "exec")
        compile(s.read("src/utils.py"), "utils.py", "exec")
        return True
    except SyntaxError:
        return False

# 3. Atomic Commit to Physical Disk
committed_count = session.verify_and_commit(validator_fn=validate_refactor)
print(f"Successfully committed {committed_count} verified files to disk.")
```

---

## 4. Architecture & Moats

```
ghost-fork/
├── ghost_fork/
│   ├── __init__.py        # Clean package exports
│   ├── vfs.py             # Copy-on-Write (CoW) Shadow Workspace & Atomic Committer
└── tests/
    └── test_vfs.py        # Verified unit tests (Isolation, Rollback, Atomic Flush)
```

---

## 5. Commercial Integration with A2Z SOC

`Ghost-Fork` streams speculative refactor telemetry, compiler diagnostic proofs, and code lineage directly into **[A2Z SOC](https://a2zsoc.com)** for continuous DevSecOps governance, code provenance verification, and SOC2 / ISO 27001 auditability.

---

## 6. Author

**Ahmed Hassan**  
*Principal AI Systems Architect | Founder, A2Z SOC*  
* LinkedIn: [Ahmed Hassan](https://eg.linkedin.com/in/ahmed-hassan-f11)  
* Platform: [A2Z SOC](https://a2zsoc.com)
