"""
Ghost-Fork: In-Memory Copy-on-Write (CoW) Virtual Filesystem & Speculative Execution Enclave
for Autonomous AI Coding Agents (Aider / OpenHands / Claude Code).
"""

from .vfs import GhostVFS, ShadowFile, SpeculativeSession, CommitFailedError

__version__ = "0.1.0"
__all__ = [
    "GhostVFS",
    "ShadowFile",
    "SpeculativeSession",
    "CommitFailedError",
]
