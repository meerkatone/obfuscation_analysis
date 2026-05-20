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


def _expr_size_bits(expr: ExpressionIndex, default: int = 0) -> int:
    """
    Return a Binary Ninja HLIL expression size in bits.
    """
    return expr.size * 8 if expr.size else default


def _coerce_size(expr: Expr, size: int, signed: bool = False) -> Expr:
    """
    Resize an expression to ``size`` bits for Miasm operators that require
    equal-sized operands.
    """
    if expr.size == size:
        return expr
    if expr.size < size:
        return expr.signExtend(size) if signed else expr.zeroExtend(size)
    return ExprSlice(expr, 0, size)


def _coerce_right(left: Expr, right: Expr, signed: bool = False) -> Expr:
    """
    Resize a binary operation RHS to the LHS width.
    """
    return _coerce_size(right, left.size, signed=signed)


def _bool_result(expr: ExpressionIndex, condition: Expr) -> Expr:
    """
    Convert a 1-bit Miasm predicate to Binary Ninja's boolean result width.
    """
    return condition.zeroExtend(_expr_size_bits(expr, default=8))


def _shift_count(left: Expr, right: Expr) -> Expr:
    """
    Miasm shift/rotate operators require equal-sized operands.
    """
    return _coerce_right(left, right)


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

        * High-level control flow (`HLIL_SWITCH`, loops, …)
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
            raise Exception(
                f"Unsupported translation for control-flow operation: {expr.core_instr}"
            )

        case HighLevelILOperation.HLIL_LABEL:
            raise Exception(
                f"Unsupported translation for control-flow operation: {expr.core_instr}"
            )

        case HighLevelILOperation.HLIL_ASSIGN_MEM_SSA:
            rhs = hlil_to_miasm(bv, expr.src)
            lhs = ExprMem(hlil_to_miasm(bv, expr.dest), rhs.size)
            return ExprAssign(lhs, rhs)

        case HighLevelILOperation.HLIL_DEREF:
            ex = hlil_to_miasm(bv, expr.src)
            return ExprMem(ex, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_DEREF_SSA:
            ex = hlil_to_miasm(bv, expr.src)
            return ExprMem(ex, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_DEREF_FIELD:
            ptr = hlil_to_miasm(bv, expr.src)
            offset = ExprInt(expr.offset, ptr.size)
            return ExprMem(ptr + offset, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_DEREF_FIELD_SSA:
            ptr = hlil_to_miasm(bv, expr.src)
            offset = ExprInt(expr.offset, ptr.size)
            return ExprMem(ptr + offset, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_ASSIGN_UNPACK_MEM_SSA:
            if len(expr.dest) != 1:
                raise Exception(
                    f"Unsupported translation for multi-destination assignment: {expr.core_instr}"
                )
            lhs = hlil_to_miasm(bv, expr.dest[0])
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

        case HighLevelILOperation.HLIL_CONST_PTR:
            ex = ExprInt(expr.constant, _expr_size_bits(expr))
            return ex

        case HighLevelILOperation.HLIL_IMPORT:
            return ExprInt(expr.constant, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_EXTERN_PTR:
            return ExprInt(expr.constant + expr.offset, _expr_size_bits(expr))

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

        case HighLevelILOperation.HLIL_ARRAY_INDEX:
            base_memory = hlil_to_miasm(bv, expr.src)
            indexed = _coerce_size(
                hlil_to_miasm(bv, expr.index), bv.arch.address_size * 8
            )
            return ExprMem(
                base_memory + (indexed * ExprInt(expr.size, bv.arch.address_size * 8)),
                _expr_size_bits(expr),
            )

        case HighLevelILOperation.HLIL_ARRAY_INDEX_SSA:
            base_memory = hlil_to_miasm(bv, expr.src)
            indexed = _coerce_size(
                hlil_to_miasm(bv, expr.index), bv.arch.address_size * 8
            )
            return ExprMem(
                base_memory + (indexed * ExprInt(expr.size, bv.arch.address_size * 8)),
                _expr_size_bits(expr),
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
            return left + _coerce_right(left, right)

        case HighLevelILOperation.HLIL_ADC:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            carry = _coerce_size(hlil_to_miasm(bv, expr.carry), left.size)
            return left + right + carry

        case HighLevelILOperation.HLIL_SUB:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left - _coerce_right(left, right)

        case HighLevelILOperation.HLIL_SBB:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            carry = _coerce_size(hlil_to_miasm(bv, expr.carry), left.size)
            return left - (right + carry)

        case HighLevelILOperation.HLIL_AND:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left & _coerce_right(left, right)

        case HighLevelILOperation.HLIL_OR:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left | _coerce_right(left, right)

        case HighLevelILOperation.HLIL_XOR:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left ^ _coerce_right(left, right)

        case HighLevelILOperation.HLIL_MUL:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return left * _coerce_right(left, right)

        case HighLevelILOperation.HLIL_MULU_DP:
            size = _expr_size_bits(expr)
            left = _coerce_size(hlil_to_miasm(bv, expr.left), size * 2)
            right = _coerce_size(hlil_to_miasm(bv, expr.right), size * 2)
            return left * right

        case HighLevelILOperation.HLIL_MULS_DP:
            size = _expr_size_bits(expr)
            left = _coerce_size(hlil_to_miasm(bv, expr.left), size * 2, signed=True)
            right = _coerce_size(hlil_to_miasm(bv, expr.right), size * 2, signed=True)
            return left * right

        case HighLevelILOperation.HLIL_DIVU:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            return ExprOp("udiv", left, right)

        case HighLevelILOperation.HLIL_DIVS:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right), signed=True)
            return ExprOp("sdiv", left, right)

        case HighLevelILOperation.HLIL_ASR:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return ExprOp("a>>", left, right)

        case HighLevelILOperation.HLIL_LSL:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return left << right

        case HighLevelILOperation.HLIL_LSR:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return left >> right

        case HighLevelILOperation.HLIL_DIVU_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            return ExprSlice(ExprOp("udiv", left, right), 0, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_DIVS_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right), signed=True)
            return ExprSlice(ExprOp("sdiv", left, right), 0, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_MODU:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            return ExprOp("umod", left, right)

        case HighLevelILOperation.HLIL_MODU_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right))
            return ExprSlice(ExprOp("umod", left, right), 0, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_MODS:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right), signed=True)
            return ExprOp("smod", left, right)

        case HighLevelILOperation.HLIL_MODS_DP:
            left = hlil_to_miasm(bv, expr.left)
            right = _coerce_right(left, hlil_to_miasm(bv, expr.right), signed=True)
            return ExprSlice(ExprOp("smod", left, right), 0, _expr_size_bits(expr))

        case HighLevelILOperation.HLIL_ROR:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return ExprOp(">>>", left, right)

        case HighLevelILOperation.HLIL_ROL:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return ExprOp("<<<", left, right)

        # binary comparison
        case HighLevelILOperation.HLIL_CMP_E:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(expr, ExprOp("==", left, _coerce_right(left, right)))

        case HighLevelILOperation.HLIL_CMP_NE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(expr, ~ExprOp("==", left, _coerce_right(left, right)))

        case HighLevelILOperation.HLIL_CMP_ULT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr, expr_is_unsigned_lower(left, _coerce_right(left, right))
            )

        case HighLevelILOperation.HLIL_CMP_ULE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr, expr_is_unsigned_lower_or_equal(left, _coerce_right(left, right))
            )

        case HighLevelILOperation.HLIL_CMP_UGE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr,
                expr_is_unsigned_greater_or_equal(left, _coerce_right(left, right)),
            )

        case HighLevelILOperation.HLIL_CMP_UGT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr, expr_is_unsigned_greater(left, _coerce_right(left, right))
            )

        case HighLevelILOperation.HLIL_CMP_SGT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr,
                expr_is_signed_greater(left, _coerce_right(left, right, signed=True)),
            )

        case HighLevelILOperation.HLIL_CMP_SGE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr,
                expr_is_signed_greater_or_equal(
                    left, _coerce_right(left, right, signed=True)
                ),
            )

        case HighLevelILOperation.HLIL_CMP_SLE:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr,
                expr_is_signed_lower_or_equal(
                    left, _coerce_right(left, right, signed=True)
                ),
            )

        case HighLevelILOperation.HLIL_CMP_SLT:
            left, right = hlil_to_miasm(bv, expr.left), hlil_to_miasm(bv, expr.right)
            return _bool_result(
                expr,
                expr_is_signed_lower(left, _coerce_right(left, right, signed=True)),
            )

        case HighLevelILOperation.HLIL_TEST_BIT:
            left = hlil_to_miasm(bv, expr.left)
            right = _shift_count(left, hlil_to_miasm(bv, expr.right))
            return _bool_result(expr, (left >> right)[:1])

        case HighLevelILOperation.HLIL_BOOL_TO_INT:
            src = hlil_to_miasm(bv, expr.src)
            return _coerce_size(src, _expr_size_bits(expr, default=8))

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
            raise Exception(
                f"Unsupported translation for empty return: {expr.core_instr}"
            )

        # unsupported control-flow operations
        case (
            HighLevelILOperation.HLIL_GOTO
            | HighLevelILOperation.HLIL_CASE
            | HighLevelILOperation.HLIL_JUMP
            | HighLevelILOperation.HLIL_LABEL
            | HighLevelILOperation.HLIL_FOR
            | HighLevelILOperation.HLIL_FOR_SSA
            | HighLevelILOperation.HLIL_DO_WHILE
            | HighLevelILOperation.HLIL_DO_WHILE_SSA
            | HighLevelILOperation.HLIL_WHILE
            | HighLevelILOperation.HLIL_WHILE_SSA
            | HighLevelILOperation.HLIL_SWITCH
            | HighLevelILOperation.HLIL_BREAK
            | HighLevelILOperation.HLIL_CONTINUE
            | HighLevelILOperation.HLIL_UNREACHABLE
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
            | HighLevelILOperation.HLIL_NORET
            | HighLevelILOperation.HLIL_CALL
            | HighLevelILOperation.HLIL_CALL_SSA
            | HighLevelILOperation.HLIL_TAILCALL
            | HighLevelILOperation.HLIL_INTRINSIC
            | HighLevelILOperation.HLIL_INTRINSIC_SSA
            | HighLevelILOperation.HLIL_SYSCALL
            | HighLevelILOperation.HLIL_SYSCALL_SSA
            | HighLevelILOperation.HLIL_VAR_DECLARE
            | HighLevelILOperation.HLIL_UNIMPL
            | HighLevelILOperation.HLIL_UNIMPL_MEM
            | HighLevelILOperation.HLIL_CONST_DATA
            | HighLevelILOperation.HLIL_FLOAT_CONST
            | HighLevelILOperation.HLIL_FADD
            | HighLevelILOperation.HLIL_FSUB
            | HighLevelILOperation.HLIL_FMUL
            | HighLevelILOperation.HLIL_FDIV
            | HighLevelILOperation.HLIL_FSQRT
            | HighLevelILOperation.HLIL_FNEG
            | HighLevelILOperation.HLIL_FABS
            | HighLevelILOperation.HLIL_FLOAT_TO_INT
            | HighLevelILOperation.HLIL_INT_TO_FLOAT
            | HighLevelILOperation.HLIL_FLOAT_CONV
            | HighLevelILOperation.HLIL_ROUND_TO_INT
            | HighLevelILOperation.HLIL_FLOOR
            | HighLevelILOperation.HLIL_CEIL
            | HighLevelILOperation.HLIL_FTRUNC
            | HighLevelILOperation.HLIL_FCMP_E
            | HighLevelILOperation.HLIL_FCMP_NE
            | HighLevelILOperation.HLIL_FCMP_LT
            | HighLevelILOperation.HLIL_FCMP_LE
            | HighLevelILOperation.HLIL_FCMP_GE
            | HighLevelILOperation.HLIL_FCMP_GT
            | HighLevelILOperation.HLIL_FCMP_O
            | HighLevelILOperation.HLIL_FCMP_UO
        ):
            raise Exception(
                f"Unsupported translation for special operation: {expr.core_instr}"
            )

        case _:
            raise Exception(f"Unsupported translation for operation: {expr.core_instr}")
