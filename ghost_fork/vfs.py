import os
from typing import Dict, Optional, List, Callable, Tuple
from dataclasses import dataclass

class CommitFailedError(Exception):
    """Raised when speculative compilation, unit tests, or invariant checks fail."""
    pass

@dataclass
class ShadowFile:
    original_path: str
    content: str
    is_modified: bool = False
    is_deleted: bool = False

class SpeculativeSession:
    """
    An isolated, in-memory Copy-on-Write (CoW) shadow workspace.
    Allows coding agents to execute speculative multi-file refactors,
    compile, and test before touching physical disk.
    """
    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        self.shadow_files: Dict[str, ShadowFile] = {}
        self.is_active = True

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.root_dir, path))

    def read(self, path: str) -> str:
        full_path = self._resolve_path(path)
        if full_path in self.shadow_files:
            shadow = self.shadow_files[full_path]
            if shadow.is_deleted:
                raise FileNotFoundError(f"File '{path}' marked as deleted in shadow workspace")
            return shadow.content

        # Read from physical disk on first access (Lazy CoW loading)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Physical file not found: '{full_path}'")
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.shadow_files[full_path] = ShadowFile(original_path=full_path, content=content)
        return content

    def write(self, path: str, content: str):
        full_path = self._resolve_path(path)
        self.shadow_files[full_path] = ShadowFile(
            original_path=full_path,
            content=content,
            is_modified=True,
            is_deleted=False
        )

    def delete(self, path: str):
        full_path = self._resolve_path(path)
        if full_path in self.shadow_files:
            self.shadow_files[full_path].is_deleted = True
            self.shadow_files[full_path].is_modified = True
        else:
            self.shadow_files[full_path] = ShadowFile(
                original_path=full_path,
                content="",
                is_modified=True,
                is_deleted=True
            )

    def rollback(self):
        """Discards all speculative in-memory edits instantly with 0ms disk overhead."""
        self.shadow_files.clear()
        self.is_active = False

    def verify_and_commit(self, validator_fn: Optional[Callable[["SpeculativeSession"], bool]] = None) -> int:
        """
        Runs speculative validation (compilation/tests). If true, commits to
        physical disk in two phases: staging (which never touches a real
        target path) and apply (fast, per-file atomic operations, with
        best-effort rollback if a later file in the same commit fails).
        If validation fails, rolls back completely without leaving broken
        files.

        An earlier version wrote files directly, one at a time, with no
        staging step. A real OS error partway through a multi-file commit
        (a blocked path, a permissions error, a full disk) left files
        already written in that loop on disk while the exception propagated
        uncaught — reproduced directly: a 2-file commit where the second
        file's directory creation failed left the first file's new content
        on disk with no error recovery. That's the exact "half-mutated
        tree" failure mode this tool exists to prevent, just moved into its
        own commit step. Fixed below.
        """
        if not self.is_active:
            raise RuntimeError("Cannot commit an inactive speculative session")

        # 1. Run Verification Invariant
        if validator_fn is not None:
            try:
                passed = validator_fn(self)
                if not passed:
                    self.rollback()
                    raise CommitFailedError("Speculative validator returned False: compilation or tests failed")
            except Exception as e:
                self.rollback()
                raise CommitFailedError(f"Speculative validation failed: {str(e)}")

        modified = [(p, s) for p, s in self.shadow_files.items() if s.is_modified and not s.is_deleted]
        deleted = [(p, s) for p, s in self.shadow_files.items() if s.is_modified and s.is_deleted]

        # 2a. Stage: write new content to temp files next to their real
        # targets, and read the pre-commit content of every file this
        # commit will touch (for rollback in 2b). Nothing here writes,
        # removes, or truncates a real target path — if anything in this
        # block raises, the physical disk is provably untouched, because
        # nothing on it has been mutated yet.
        staged_writes: List[Tuple[str, str]] = []  # (tmp_path, final_path)
        pre_commit_content: Dict[str, Optional[str]] = {}  # final_path -> original content, or None if it didn't exist
        try:
            for full_path, _ in modified + deleted:
                if full_path not in pre_commit_content:
                    if os.path.exists(full_path):
                        with open(full_path, "r", encoding="utf-8") as f:
                            pre_commit_content[full_path] = f.read()
                    else:
                        pre_commit_content[full_path] = None

            for full_path, shadow in modified:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                tmp_path = f"{full_path}.ghostfork.tmp.{os.getpid()}.{id(shadow)}"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(shadow.content)
                staged_writes.append((tmp_path, full_path))
        except Exception as e:
            for tmp_path, _ in staged_writes:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            self.rollback()
            raise CommitFailedError(f"Staging failed before any file on disk was modified: {e}")

        # 2b. Apply: fast, per-file atomic operations (os.replace is an
        # atomic rename on the same filesystem). If one of these still
        # fails, restore every file this commit has already touched in this
        # loop, using the pre-commit content captured above, and raise --
        # best-effort, in-process rollback, not a crash-safe write-ahead
        # log. A hard process kill between two of these operations is the
        # one scenario this can't protect against; see the README.
        committed_files = 0
        applied_paths: List[str] = []
        try:
            for tmp_path, full_path in staged_writes:
                os.replace(tmp_path, full_path)
                applied_paths.append(full_path)
                committed_files += 1
            for full_path, _ in deleted:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    applied_paths.append(full_path)
                    committed_files += 1
        except Exception as apply_error:
            rollback_errors = []
            for full_path in applied_paths:
                original = pre_commit_content.get(full_path)
                try:
                    if original is None:
                        if os.path.exists(full_path):
                            os.remove(full_path)
                    else:
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(original)
                except Exception as rollback_error:
                    rollback_errors.append(f"{full_path}: {rollback_error}")
            self.is_active = False
            if rollback_errors:
                raise CommitFailedError(
                    f"Apply failed ({apply_error}) and rollback could not fully restore: {rollback_errors}"
                )
            raise CommitFailedError(f"Apply failed and was rolled back cleanly: {apply_error}")

        self.is_active = False
        return committed_files

class GhostVFS:
    """Master factory managing speculative agent workspaces."""
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)

    def fork(self) -> SpeculativeSession:
        return SpeculativeSession(self.root_dir)
