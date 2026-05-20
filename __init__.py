"""
Binary Ninja plugin entrypoint for *Obfuscation Analysis*.

Registers UI commands, user-visible settings, and wires them to the
background-thread helpers.
"""

import json
from pathlib import Path

from binaryninja import PluginCommand
from binaryninja.settings import Settings

from .obfuscation_analysis import (
    identify_corrupted_functions_bg,
    inline_functions_recursively_bg,
    inline_functions_recursively_max_depth_bg,
    remove_corrupted_functions_bg,
    simplify_hlil_instruction_bg,
)

# ----------------------------------------------------------------------
#  Command registrations
# ----------------------------------------------------------------------

PluginCommand.register_for_high_level_il_instruction(
    "Obfuscation Analysis\\MBA Simplification\\Slice && Simplify",
    (
        "Back-slice the selected HLIL expression, translate it to Miasm IR, "
        "run msynth for Mixed-Boolean Arithmetic (MBA) simplification, and "
        "annotate the result as a decompiler comment."
    ),
    simplify_hlil_instruction_bg,
)

PluginCommand.register(
    "Obfuscation Analysis\\Corrupted Functions\\Identify Corrupted Functions",
    (
        "Scan the binary for functions that contain undefined or overlapping "
        "instructions (typical artefacts of failed disassembly)."
    ),
    identify_corrupted_functions_bg,
)

PluginCommand.register(
    "Obfuscation Analysis\\Corrupted Functions\\Remove Corrupted Functions",
    (
        "Remove all functions with corrupted disassembly from the BinaryView "
        "and trigger re-analysis to clean up the function list."
    ),
    remove_corrupted_functions_bg,
)

PluginCommand.register_for_function(
    "Obfuscation Analysis\\Function Inlining\\Inline Recursively (Unlimited)",
    (
        "Inline all functions called by the current function recursively in the decompiler to enable a cross-function analysis."
    ),
    inline_functions_recursively_bg,
)


PluginCommand.register_for_function(
    "Obfuscation Analysis\\Function Inlining\\Inline Up to N Levels",
    (
        "Inline callees only up to a configurable depth, to widen cross-function analysis without flattening the entire call tree."
    ),
    inline_functions_recursively_max_depth_bg,
)

# ----------------------------------------------------------------------
#  User-visible settings
# ----------------------------------------------------------------------

plugin_dir = Path(__file__).resolve().parent
# Always use forward slashes so the JSON that follows is valid on Windows too.
mba_oracle_path = (plugin_dir / "msynth_oracle.pickle").as_posix()

Settings().register_group("obfuscation_analysis", "Obfuscation Analysis")
setting_spec = {
    "description": (
        "Absolute path to the oracle database shipped with msynth. "
        "Required for MBA simplification."
    ),
    "title": "msynth Oracle DB Path",
    "default": mba_oracle_path,
    "type": "string",
    "requiresRestart": True,
    "optional": False,
    "uiSelectionAction": "file",
}

Settings().register_setting(
    "obfuscation_analysis.mba_oracle_path",
    json.dumps(setting_spec),
)


inline_depth_spec = {
    "description": (
        "Maximum call depth for recursive function inlining."
        "Inlines only up to N call levels from the start function."
    ),
    "title": "Max Function Inlining Depth",
    "default": 1,
    "type": "number",
    "optional": False,
    "requiresRestart": False,
    "minValue": 1,
    "maxValue": 128,
}
Settings().register_setting(
    "obfuscation_analysis.function_inlining_max_depth",
    json.dumps(inline_depth_spec),
)
