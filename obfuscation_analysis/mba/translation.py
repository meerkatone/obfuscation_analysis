from binaryninja.binaryview import BinaryView
from binaryninja.highlevelil import ExpressionIndex, HighLevelILOperation
from binaryninja.variable import Variable
from miasm.expression.expression import (
    Expr,
    ExprAssign,
    ExprCompose,
    ExprId,
    ExprInt,
    ExprMem,
    ExprOp,
    ExprSlice,
    expr_is_signed_greater,
    expr_is_signed_greater_or_equal,
    expr_is_signed_lower,
    expr_is_signed_lower_or_equal,
    expr_is_unsigned_greater,
    expr_is_unsigned_greater_or_equal,
    expr_is_unsigned_lower,
    expr_is_unsigned_lower_or_equal,
)


def variable_to_miasm(v: Variable) -> ExprId:
    """
    Convert a non-SSA Binary Ninja `Variable to a Miasm.

    The original variable name is kept verbatim and the bit-width is taken
    from `v.type.width` (bytes -> bits).
    """
    name = v.name
    size = v.type.width * 8
    return ExprId(name, size)


def ssa_variable_to_miasm(v: Variable) -> ExprId:
    """
    Convert a Binary Ninja SSA variable to a Miasm `ExprId`.

    The SSA index is appended as `name#version` so each version receives
    a unique Miasm identifier.

    Example
    -------
    `eax@3` -> `ExprId("eax#3", 32)`
    """
    name = f"{v.name}#{v.version}"
    size = v.type.width * 8
    return ExprId(name, size)


def mem_variable_to_miasm(v: Variable) -> ExprMem:
    """
    Return a Miasm `ExprMem` that models [*v]`.

    Internally this calls `ssa_variable_to_miasm` to obtain the
    address expression and wraps it in an `ExprMem` of matching
    bit-width.
    """
    size = v.type.width * 8
    return ExprMem(ssa_variable_to_miasm(v), size)


def hlil_to_miasm(
    bv: BinaryView,
    expr: ExpressionIndex,
) -> Expr:
    """
    Recursively translate a Binary Ninja HLIL expression to a Miasm
    Expr.

    The routine walks the HLIL AST and builds a semantically equivalent Miasm tree.  Only
    side-effect-free value expressions are supported; control-flow
    constructs (`if`, `switch`, loops, `goto`, PHI nodes, …) raise an
    Exception.

    Parameters
    ----------
    bv :
        BinaryView.
        Needed mainly for pointer size (`bv.arch.address_size`).
    expr :
        Any for of HLIL Expression,. `ExpressionIndex`
        (SSA or non-SSA).

    Returns
    -------
    Expr
        A Miasm expression whose bit-width matches ``expr.size``.
        The function never returns ``None``—translation failures are
        signalled via an ``Exception``.

    Raises
    ------
    Exception
        When *expr* (or any of its children) represents a construct that
        cannot be mapped to Miasm IR—for example:

        * High-level control flow (`HLIL_IF`, `HLIL_SWITCH`, …)
        * SSA PHI or memory-PHI nodes
        * Intrinsic or unimplemented HLIL operations

    Notes
    -----
    * Integer widths are expressed in **bits** (``expr.size * 8``), as
      required by Miasm.
    * SSA variables are rendered as ``name#version`` to keep each version
      distinct within the IR.
    * For double-precision divisions/modulos (e.g. ``DIVU_DP``) the result
      is truncated with :class:`~miasm.expression.expression.ExprSlice`
      because Miasm internally yields the full 128-bit quotient/remainder.
    """
    match expr.operation:
        case HighLevelILOperation.HLIL_IF:
            # translate only condition
            return hlil_to_miasm(bv, expr.condition)

        case HighLevelILOperation.HLIL_JUMP:
            # translate jump target
            return hlil_to_miasm(bv, expr.operands[0])

        case HighLevelILOperation.HLIL_LABEL:
            return ExprId(expr.target, expr.size)

        case HighLevelILOperation.HLIL_ASSIGN_MEM_SSA:
            lhs = hlil_to_miasm(bv, expr.dest)
            rhs = hlil_to_miasm(bv, expr.src)
            return ExprAssign(lhs, rhs)

        # assignment
        case HighLevelILOperation.HLIL_VAR_INIT:
            lhs = variable_to_miasm(expr.dest)
            rhs = hlil_to_miasm(bv, expr.src)
            if lhs is not None and rhs is not None:
                return ExprAssign(lhs, rhs)

        case HighLevelILOperation.HLIL_ADDRESS_OF:
            name = f"&{expr.operands[0]}"
            size = 8 * bv.arch.address_size
            return ExprId(name, size)

        case HighLevelILOperation.HLIL_DEREF_SSA:
            ex = hlil_to_miasm(bv, expr.operands[0])
            return ExprMem(ex, 8 * expr.size)

        case HighLevelILOperation.HLIL_CONST_PTR:
            ex = ExprInt(expr.operands[0], expr.size * 8)
            return ex

        case HighLevelILOperation.HLIL_IMPORT:
            ex = ExprInt(expr.operands[0], expr.size * 8)
            return ExprId(ex, expr.size)

        # SSA assignment
        case HighLevelILOperation.HLIL_VAR_INIT_SSA:
            lhs = ssa_variable_to_miasm(expr.dest)
            rhs = hlil_to_miasm(bv, expr.src)
            return ExprAssign(lhs, rhs)

        case HighLevelILOperation.HLIL_ASSIGN:
            lhs = hlil_to_miasm(bv, expr.dest)
            rhs = hlil_to_miasm(bv, expr.src)
            return ExprAssign(lhs, rhs)

        # part of a struct
        case HighLevelILOperation.HLIL_STRUCT_FIELD:
            src = hlil_to_miasm(bv, expr.src)
            return ExprSlice(src, expr.offset * 8, expr.offset * 8 + expr.size * 8)

        case HighLevelILOperation.HLIL_ARRAY_INDEX_SSA:
            base_memory = hlil_to_miasm(bv, expr.src)
            indexed = hlil_to_miasm(bv, expr.index)
            return ExprMem(
                base_memory + (indexed * ExprInt(expr.size, bv.arch.address_size * 8)),
                expr.size * 8,
            )

        case HighLevelILOperation.HLIL_SPLIT:
            low = hlil_to_miasm(bv, expr.low)
            high = hlil_to_miasm(bv, expr.high)
            return ExprCompose(low, high)

        # variables
        case HighLevelILOperation.HLIL_VAR:
            return variable_to_miasm(expr.operands[0])

        # SSA variables
        case HighLevelILOperation.HLIL_VAR_SSA:
            return ssa_variable_to_miasm(expr.var)

        # constant
        case HighLevelILOperation.HLIL_CONST:
            value = expr.constant
            size = expr.size * 8
            return ExprInt(value, size)

        # binary arithmetic/logical operations
        case HighLevelILOperation.HLIL_ADD:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left + right

        case HighLevelILOperation.HLIL_SUB:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left - right

        case HighLevelILOperation.HLIL_SBB:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left - right

        case HighLevelILOperation.HLIL_AND:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left & right

        case HighLevelILOperation.HLIL_OR:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left | right

        case HighLevelILOperation.HLIL_XOR:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left ^ right

        case HighLevelILOperation.HLIL_MUL:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left * right

        case HighLevelILOperation.HLIL_DIVS:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return ExprOp("s/", left, right)

        case HighLevelILOperation.HLIL_ASR:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left >> right

        case HighLevelILOperation.HLIL_LSL:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            return left << right

        case HighLevelILOperation.HLIL_LSR:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            return left >> right

        case HighLevelILOperation.HLIL_DIVU_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            # the slice here is needed because we're talking about double precision (128bit)
            return ExprSlice(ExprOp("%", left, right), 0, expr.size * 8)

        case HighLevelILOperation.HLIL_DIVS_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).signExtend(left.size)
            # the slice here is needed because we're talking about double precision (128bit)
            return ExprSlice(ExprOp("%", left, right), 0, expr.size * 8)

        case HighLevelILOperation.HLIL_MODU:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            return ExprOp("%", left, right)

        case HighLevelILOperation.HLIL_MODU_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            # the slice here is needed because we're talking about double precision (128bit)
            return ExprSlice(ExprOp("%", left, right), 0, expr.size * 8)

        case HighLevelILOperation.HLIL_MODS_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right).zeroExtend(left.size)
            # the slice here is needed because we're talking about double precision (128bit)
            return ExprSlice(ExprOp("%s", left, right), 0, expr.size * 8)

        case HighLevelILOperation.HLIL_ROR:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right)
            return ExprOp(">>>", left, right)

        case HighLevelILOperation.HLIL_ROL:
            left = hlil_to_miasm(bv, expr.left)
            right = hlil_to_miasm(bv, expr.right)
            return ExprOp("<<<", left, right)

        # binary comparison
        case HighLevelILOperation.HLIL_CMP_E:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return ExprOp("==", left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_NE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return (~ExprOp("==", left, right)).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_ULT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_unsigned_lower(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_ULE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_unsigned_lower_or_equal(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_UGE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_unsigned_greater_or_equal(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_UGT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_unsigned_greater(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_SGT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_signed_greater(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_SGE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_signed_greater_or_equal(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_SLE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_signed_lower_or_equal(left, right).zeroExtend(8)

        case HighLevelILOperation.HLIL_CMP_SLT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return expr_is_signed_lower(left, right).zeroExtend(8)

        # unary operations
        case HighLevelILOperation.HLIL_NEG:
            src = hlil_to_miasm(bv, expr.src)
            return -src

        case HighLevelILOperation.HLIL_NOT:
            src = hlil_to_miasm(bv, expr.src)
            return ~src

        case HighLevelILOperation.HLIL_LOW_PART:
            src = hlil_to_miasm(bv, expr.src)
            return ExprSlice(src, 0, expr.size * 8)

        case HighLevelILOperation.HLIL_ZX:
            src = hlil_to_miasm(bv, expr.src)
            return src.zeroExtend(expr.size * 8)

        case HighLevelILOperation.HLIL_SX:
            src = hlil_to_miasm(bv, expr.src)
            return src.signExtend(expr.size * 8)

        case HighLevelILOperation.HLIL_RET:
            # ensure return has arguments
            if len(expr.src) != 0:
                return hlil_to_miasm(bv, expr.src[0])

        # unsupported control-flow operations
        case (
            HighLevelILOperation.HLIL_GOTO
            | HighLevelILOperation.HLIL_CASE
            | HighLevelILOperation.HLIL_DO_WHILE_SSA
            | HighLevelILOperation.HLIL_WHILE_SSA
            | HighLevelILOperation.HLIL_SWITCH
            | HighLevelILOperation.HLIL_BREAK
        ):
            raise Exception(
                f"Unsupported translation for control-flow operation: {expr.core_instr}"
            )

        # unssupported special operations that cannot be semantically represented in MiasmIR
        case (
            HighLevelILOperation.HLIL_VAR_PHI
            | HighLevelILOperation.HLIL_ASSIGN_UNPACK
            | HighLevelILOperation.HLIL_MEM_PHI
            | HighLevelILOperation.HLIL_UNDEF
            | HighLevelILOperation.HLIL_NOP
            | HighLevelILOperation.HLIL_CONTINUE
            | HighLevelILOperation.HLIL_NORET
            | HighLevelILOperation.HLIL_CALL_SSA
            | HighLevelILOperation.HLIL_VAR_DECLARE
        ):
            raise Exception(
                f"Unsupported translation for special operation: {expr.core_instr}"
            )

        case _:
            raise Exception(f"Unsupported translation for operation: {expr.core_instr}")
