"""
Singleton wrapper around msynth’s `Simplifier`.

*  Lazy-initialised the first time `get_simplifier` is called.
*  Thread-safe via a tiny `threading.Lock`.
*  Emits concise user errors (with full trace in *Debug* log) when the
   oracle path is missing or the initialisation fails.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Optional

from binaryninja.settings import Settings
from msynth import Simplifier

from ..utils import user_error

# ----------------------------------------------------------------------
# Internal singleton state
# ----------------------------------------------------------------------

_MBA_SIMPLIFIER: Optional[Simplifier] = None
_LOCK = Lock()  # guards first-time creation


# ----------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------


def get_simplifier() -> Optional[Simplifier]:
    """
    Return the global `Simplifier` instance, creating it on first use.

    On failure (oracle not configured / not found / msynth error) a concise
    message is logged and `None` is returned, so callers can fall back gracefully.

    Returns
    -------
    Simplifier | None
    """
    global _MBA_SIMPLIFIER

    # fast path
    if _MBA_SIMPLIFIER is not None:
        return _MBA_SIMPLIFIER

    # thread-safe lazy init
    with _LOCK:
        if _MBA_SIMPLIFIER is not None:
            return _MBA_SIMPLIFIER

        oracle_path = (
            Settings().get_string("obfuscation_analysis.mba_oracle_path").strip()
        )

        # ---- configuration sanity checks --------------------------------
        if not oracle_path:
            user_error(
                "msynth oracle path not configured – set it under "
                "Settings → Obfuscation Analysis."
            )
            return None

        if not Path(oracle_path).exists():
            user_error(f"Oracle database for msynth not found: {oracle_path}")
            return None

        # ---- create Simplifier ------------------------------------------
        try:
            _MBA_SIMPLIFIER = Simplifier(oracle_path=oracle_path)
        except Exception as err:  # pragma: no cover
            user_error(
                "Failed to initialise msynth simplifier – see Debug Log.",
                exc=err,
            )
            _MBA_SIMPLIFIER = None

    return _MBA_SIMPLIFIER


def set_simplifier(simplifier: Simplifier) -> None:
    """
    Manually inject a pre-created `Simplifier`.
    """
    global _MBA_SIMPLIFIER
    with _LOCK:
        _MBA_SIMPLIFIER = simplifier
