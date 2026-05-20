from __future__ import annotations

from typing import Optional

from binaryninja import SSAVariable
from binaryninja.binaryview import BinaryView
from binaryninja.highlevelil import (
    HighLevelILFunction,
    HighLevelILInstruction,
    HighLevelILVarPhi,
)
from miasm.expression.expression import Expr

from .translation import hlil_to_miasm, ssa_variable_to_miasm


def backward_slice_basic_block_level(
    bv: BinaryView,
    instr: HighLevelILInstruction,
    hlil: HighLevelILFunction,
) -> Optional[Expr]:
    """
    Statically backward-slice instr inside its HLIL basic block, recursively
    inlining SSA definitions, and return the resolved expression in Miasm IR.

    Algorithm (single basic block)
    ------------------------------
    1. Translate the root `instr.ssa_form` to Miasm (`expr_m2`).
    2. Build a work-list with every SSA variable the root expression reads.
    3. While the work-list is not empty:
       a. Pop one SSA variable.
       b. Fetch its definition. Skip if it lies outside the same basic block
          or is a `HLIL_VAR_PHI`.
       c. Translate the definition’s *source* to Miasm; if translation
          raises an *Exception*, skip that variable.
       d. Immediately substitute the SSA variable in `expr_m2` with the
          translated sub-expression.
       e. Push every *new* SSA variable the definition reads onto the
          work-list.

    Limitations
    -----------
    * Only register SSA variables are inlined; memory SSA is ignored.
    * Definitions in predecessor blocks are not followed.
    * Unsupported HLIL -> Miasm constructs are silently skipped.

    Returns
    -------
    Expr
        Fully inlined Miasm expression.
    """
    # fetch HLIL basic block
    cur_basic_block = hlil.get_basic_block_at(instr.instr_index)
    # get SSA form
    expr = instr.ssa_form
    # set HLIL root to SSA basic block
    start_bb = cur_basic_block.start
    end_bb = cur_basic_block.end

    # init expression in miasm IR
    expr_m2 = hlil_to_miasm(bv, expr)

    # init worklist with variable uses (variables in a SSA form)
    worklist = [
        v
        for v in set(expr.ssa_form.vars_read)
        if isinstance(v, SSAVariable) and hlil.get_ssa_var_definition(v) is not None
    ]

    # replacement dictionary for miasm expression
    replacements = {}

    # process worklist
    while len(worklist) > 0:
        # pop variable from stack
        variable = worklist.pop(-1)

        # get variable definition
        definition = hlil.get_ssa_var_definition(variable)

        # skip if no definition
        if definition is None:
            continue

        # skip definitions outside the current basic block
        if definition.instr_index < start_bb or definition.instr_index > end_bb:
            continue

        # skip SSA phi functions
        if isinstance(definition, HighLevelILVarPhi):
            continue

        # replace SSA variable with its definition in miasm IR
        replacements[ssa_variable_to_miasm(variable)] = hlil_to_miasm(
            bv, definition.src
        )
        expr_m2 = expr_m2.replace_expr(replacements)

        # add variable uses to worklist
        for v in set(definition.vars_read):
            if hlil.get_ssa_var_definition(v) is not None:
                worklist.append(v)

    return expr_m2
