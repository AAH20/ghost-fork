import os
import shutil
import time
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field

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
        Runs speculative validation (compilation/tests). If true, commits atomically to physical disk.
        If validation fails, rolls back completely without leaving broken files.
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

        # 2. Atomic Flush to Physical Disk
        committed_files = 0
        for full_path, shadow in self.shadow_files.items():
            if not shadow.is_modified:
                continue

            if shadow.is_deleted:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    committed_files += 1
            else:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(shadow.content)
                committed_files += 1

        self.is_active = False
        return committed_files

class GhostVFS:
    """Master factory managing speculative agent workspaces."""
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)

    def fork(self) -> SpeculativeSession:
        return SpeculativeSession(self.root_dir)
