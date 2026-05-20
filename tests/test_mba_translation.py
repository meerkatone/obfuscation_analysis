from types import SimpleNamespace

import pytest

miasm_expr = pytest.importorskip("miasm.expression.expression")

ExprAssign = miasm_expr.ExprAssign
ExprCompose = miasm_expr.ExprCompose
ExprId = miasm_expr.ExprId
ExprInt = miasm_expr.ExprInt
ExprMem = miasm_expr.ExprMem
ExprOp = miasm_expr.ExprOp
ExprSlice = miasm_expr.ExprSlice


def tr(translation_module, fake_bv, expr):
    return translation_module.hlil_to_miasm(fake_bv, expr)


def assert_op(expr, op, size=None):
    assert isinstance(expr, ExprOp)
    assert expr.op == op
    if size is not None:
        assert expr.size == size


def test_variable_helpers(translation_module, var):
    plain = translation_module.variable_to_miasm(var("eax", width=4))
    assert plain == ExprId("eax", 32)

    ssa = translation_module.ssa_variable_to_miasm(var("eax", width=4, version=3))
    assert ssa == ExprId("eax#3", 32)

    mem = translation_module.mem_variable_to_miasm(var("ptr", width=8, version=7))
    assert mem == ExprMem(ExprId("ptr#7", 64), 64)


def test_constant_pointer_import_and_extern_ptr(
    translation_module, fake_bv, il_expr, ops
):
    const_ptr = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_CONST_PTR, size=8, constant=0x401000),
    )
    assert const_ptr == ExprInt(0x401000, 64)

    imported = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_IMPORT, size=8, constant=0x402000),
    )
    assert imported == ExprInt(0x402000, 64)

    extern = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_EXTERN_PTR, size=8, constant=0x400000, offset=0x123),
    )
    assert extern == ExprInt(0x400123, 64)


def test_address_of_uses_pointer_width(translation_module, fake_bv, il_expr, ops, var):
    src_var = var("stack_var", width=4)
    address = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_ADDRESS_OF, size=8, operands=[src_var]),
    )
    assert address == ExprId(f"&{src_var}", 64)


def test_variable_reads_and_assignments(
    translation_module, fake_bv, il_expr, ops, const, var
):
    x = var("x", width=4)
    y = var("y", width=8, version=2)

    assert tr(
        translation_module, fake_bv, il_expr(ops.HLIL_VAR, operands=[x])
    ) == ExprId("x", 32)
    assert tr(translation_module, fake_bv, il_expr(ops.HLIL_VAR_SSA, var=y)) == ExprId(
        "y#2", 64
    )

    var_init = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_VAR_INIT, dest=x, src=const(0x12, 4)),
    )
    assert var_init == ExprAssign(ExprId("x", 32), ExprInt(0x12, 32))

    ssa_init = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_VAR_INIT_SSA, dest=y, src=const(0x1234, 8)),
    )
    assert ssa_init == ExprAssign(ExprId("y#2", 64), ExprInt(0x1234, 64))

    assign = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ASSIGN,
            dest=il_expr(ops.HLIL_VAR, operands=[x]),
            src=const(0x99, 4),
        ),
    )
    assert assign == ExprAssign(ExprId("x", 32), ExprInt(0x99, 32))


def test_memory_reads_and_writes(translation_module, fake_bv, il_expr, ops, const):
    address = const(0x1000, 8)

    for operation in (ops.HLIL_DEREF, ops.HLIL_DEREF_SSA):
        loaded = tr(
            translation_module,
            fake_bv,
            il_expr(operation, size=4, src=address),
        )
        assert loaded == ExprMem(ExprInt(0x1000, 64), 32)

    for operation in (ops.HLIL_DEREF_FIELD, ops.HLIL_DEREF_FIELD_SSA):
        loaded = tr(
            translation_module,
            fake_bv,
            il_expr(operation, size=2, src=address, offset=0x10),
        )
        assert loaded == ExprMem(ExprInt(0x1000, 64) + ExprInt(0x10, 64), 16)

    store = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ASSIGN_MEM_SSA,
            size=0,
            dest=address,
            src=const(0xDEADBEEF, 4),
        ),
    )
    assert store == ExprAssign(
        ExprMem(ExprInt(0x1000, 64), 32), ExprInt(0xDEADBEEF, 32)
    )


def test_single_destination_unpack_mem_assignment(
    translation_module, fake_bv, il_expr, ops, const, var
):
    dst = il_expr(ops.HLIL_VAR, operands=[var("dst", width=4)])
    assign = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ASSIGN_UNPACK_MEM_SSA,
            size=0,
            dest=[dst],
            src=const(0x55, 4),
        ),
    )
    assert assign == ExprAssign(ExprId("dst", 32), ExprInt(0x55, 32))

    with pytest.raises(Exception, match="multi-destination assignment"):
        tr(
            translation_module,
            fake_bv,
            il_expr(
                ops.HLIL_ASSIGN_UNPACK_MEM_SSA,
                size=0,
                dest=[dst, dst],
                src=const(0x55, 4),
            ),
        )


def test_struct_field_array_index_and_split(
    translation_module, fake_bv, il_expr, ops, const
):
    field = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_STRUCT_FIELD, size=2, src=const(0x1122334455667788, 8), offset=2
        ),
    )
    assert field == ExprSlice(ExprInt(0x1122334455667788, 64), 16, 32)

    indexed = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ARRAY_INDEX,
            size=4,
            src=const(0x2000, 8),
            index=const(3, 1),
        ),
    )
    assert indexed == ExprMem(
        ExprInt(0x2000, 64) + (ExprInt(3, 8).zeroExtend(64) * ExprInt(4, 64)),
        32,
    )

    indexed_ssa = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ARRAY_INDEX_SSA,
            size=8,
            src=const(0x3000, 8),
            index=const(2, 4),
        ),
    )
    assert indexed_ssa == ExprMem(
        ExprInt(0x3000, 64) + (ExprInt(2, 32).zeroExtend(64) * ExprInt(8, 64)),
        64,
    )

    split = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_SPLIT, size=8, low=const(0xAA, 1), high=const(0xBB, 1)),
    )
    assert split == ExprCompose(ExprInt(0xAA, 8), ExprInt(0xBB, 8))


@pytest.mark.parametrize(
    ("operation", "expected_op"),
    [
        ("HLIL_ADD", "+"),
        ("HLIL_AND", "&"),
        ("HLIL_OR", "|"),
        ("HLIL_XOR", "^"),
        ("HLIL_MUL", "*"),
    ],
)
def test_binary_operations_resize_rhs_to_lhs(
    translation_module, fake_bv, il_expr, ops, const, operation, expected_op
):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(
            getattr(ops, operation), left=const(0x11223344, 4), right=const(0x55, 1)
        ),
    )
    assert_op(result, expected_op, 32)
    assert result.args[1].size == 32


def test_subtraction_resizes_rhs(translation_module, fake_bv, il_expr, ops, const):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_SUB, left=const(0x1000, 4), right=const(0x10, 1)),
    )
    assert result.size == 32
    assert result.args[1].size == 32


def test_carry_arithmetic_preserves_carry_operand(
    translation_module, fake_bv, il_expr, ops, const
):
    adc = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_ADC,
            left=const(0x100, 4),
            right=const(0x10, 1),
            carry=const(1, 1),
        ),
    )
    assert adc.size == 32
    assert str(adc).count("0x1") >= 1

    sbb = tr(
        translation_module,
        fake_bv,
        il_expr(
            ops.HLIL_SBB,
            left=const(0x100, 4),
            right=const(0x10, 1),
            carry=const(1, 1),
        ),
    )
    assert sbb.size == 32
    assert str(sbb).count("0x1") >= 1


@pytest.mark.parametrize(
    ("operation", "expected_op", "signed_rhs"),
    [
        ("HLIL_DIVU", "udiv", False),
        ("HLIL_DIVS", "sdiv", True),
        ("HLIL_MODU", "umod", False),
        ("HLIL_MODS", "smod", True),
    ],
)
def test_division_and_modulo_use_miasm_signedness(
    translation_module,
    fake_bv,
    il_expr,
    ops,
    const,
    operation,
    expected_op,
    signed_rhs,
):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(getattr(ops, operation), left=const(0x80000000, 4), right=const(3, 1)),
    )
    assert_op(result, expected_op, 32)
    assert result.args[1].size == 32
    if signed_rhs:
        assert result.args[1].op == "signExt_32"
    else:
        assert result.args[1].op == "zeroExt_32"


@pytest.mark.parametrize(
    ("operation", "expected_op"),
    [
        ("HLIL_DIVU_DP", "udiv"),
        ("HLIL_DIVS_DP", "sdiv"),
        ("HLIL_MODU_DP", "umod"),
        ("HLIL_MODS_DP", "smod"),
    ],
)
def test_double_precision_division_and_modulo_are_sliced_results(
    translation_module, fake_bv, il_expr, ops, const, operation, expected_op
):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(
            getattr(ops, operation),
            size=4,
            left=const(0x100000001, 8),
            right=const(0x1234, 4),
        ),
    )
    assert isinstance(result, ExprSlice)
    assert result.start == 0
    assert result.stop == 32
    assert_op(result.arg, expected_op, 64)
    assert result.arg.args[1].size == 64


@pytest.mark.parametrize(
    ("operation", "expected_op"),
    [
        ("HLIL_ASR", "a>>"),
        ("HLIL_LSL", "<<"),
        ("HLIL_LSR", ">>"),
        ("HLIL_ROR", ">>>"),
        ("HLIL_ROL", "<<<"),
    ],
)
def test_shift_and_rotate_ops_resize_counts(
    translation_module, fake_bv, il_expr, ops, const, operation, expected_op
):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(getattr(ops, operation), left=const(0x80000000, 4), right=const(7, 1)),
    )
    assert_op(result, expected_op, 32)
    assert result.args[1].size == 32


def test_double_precision_multiply_extends_operands(
    translation_module, fake_bv, il_expr, ops, const
):
    unsigned_result = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_MULU_DP, size=4, left=const(0xFE, 1), right=const(0x10, 1)),
    )
    assert_op(unsigned_result, "*", 64)
    assert all(arg.size == 64 for arg in unsigned_result.args)
    assert all(arg.op == "zeroExt_64" for arg in unsigned_result.args)

    signed_result = tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_MULS_DP, size=4, left=const(0xFE, 1), right=const(0x10, 1)),
    )
    assert_op(signed_result, "*", 64)
    assert all(arg.size == 64 for arg in signed_result.args)
    assert all(arg.op == "signExt_64" for arg in signed_result.args)


@pytest.mark.parametrize(
    "operation",
    [
        "HLIL_CMP_E",
        "HLIL_CMP_NE",
        "HLIL_CMP_ULT",
        "HLIL_CMP_ULE",
        "HLIL_CMP_UGE",
        "HLIL_CMP_UGT",
        "HLIL_CMP_SGT",
        "HLIL_CMP_SGE",
        "HLIL_CMP_SLE",
        "HLIL_CMP_SLT",
        "HLIL_TEST_BIT",
    ],
)
def test_comparisons_and_test_bit_return_hlil_bool_width(
    translation_module, fake_bv, il_expr, ops, const, operation
):
    result = tr(
        translation_module,
        fake_bv,
        il_expr(
            getattr(ops, operation), size=4, left=const(0x80, 4), right=const(7, 1)
        ),
    )
    assert result.size == 32


def test_bool_to_int_and_unary_conversions(
    translation_module, fake_bv, il_expr, ops, const
):
    source = const(0x80, 1)

    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_BOOL_TO_INT, size=4, src=source),
    ) == ExprInt(0x80, 8).zeroExtend(32)

    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_LOW_PART, size=1, src=const(0x1234, 2)),
    ) == ExprSlice(ExprInt(0x1234, 16), 0, 8)

    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_ZX, size=4, src=source),
    ) == ExprInt(0x80, 8).zeroExtend(32)

    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_SX, size=4, src=source),
    ) == ExprInt(0x80, 8).signExtend(32)

    assert tr(
        translation_module, fake_bv, il_expr(ops.HLIL_NEG, src=source)
    ) == -ExprInt(0x80, 8)
    assert tr(
        translation_module, fake_bv, il_expr(ops.HLIL_NOT, src=source)
    ) == ~ExprInt(0x80, 8)


def test_if_and_return_translate_value_subexpressions(
    translation_module, fake_bv, il_expr, ops, const
):
    condition = const(1, 1)
    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_IF, size=0, condition=condition),
    ) == ExprInt(1, 8)

    assert tr(
        translation_module,
        fake_bv,
        il_expr(ops.HLIL_RET, size=0, src=[const(0x1234, 4)]),
    ) == ExprInt(0x1234, 32)

    with pytest.raises(Exception, match="empty return"):
        tr(translation_module, fake_bv, il_expr(ops.HLIL_RET, size=0, src=[]))


@pytest.mark.parametrize(
    "operation",
    [
        "HLIL_GOTO",
        "HLIL_CASE",
        "HLIL_JUMP",
        "HLIL_LABEL",
        "HLIL_FOR",
        "HLIL_FOR_SSA",
        "HLIL_DO_WHILE",
        "HLIL_DO_WHILE_SSA",
        "HLIL_WHILE",
        "HLIL_WHILE_SSA",
        "HLIL_SWITCH",
        "HLIL_BREAK",
        "HLIL_CONTINUE",
        "HLIL_UNREACHABLE",
    ],
)
def test_unsupported_control_flow_raises(
    translation_module, fake_bv, il_expr, ops, operation
):
    with pytest.raises(Exception, match="Unsupported translation for control-flow"):
        tr(translation_module, fake_bv, il_expr(getattr(ops, operation), size=0))


@pytest.mark.parametrize(
    "operation",
    [
        "HLIL_VAR_PHI",
        "HLIL_ASSIGN_UNPACK",
        "HLIL_MEM_PHI",
        "HLIL_UNDEF",
        "HLIL_NOP",
        "HLIL_NORET",
        "HLIL_CALL",
        "HLIL_CALL_SSA",
        "HLIL_TAILCALL",
        "HLIL_INTRINSIC",
        "HLIL_INTRINSIC_SSA",
        "HLIL_SYSCALL",
        "HLIL_SYSCALL_SSA",
        "HLIL_VAR_DECLARE",
        "HLIL_UNIMPL",
        "HLIL_UNIMPL_MEM",
        "HLIL_CONST_DATA",
        "HLIL_FLOAT_CONST",
        "HLIL_FADD",
        "HLIL_FSUB",
        "HLIL_FMUL",
        "HLIL_FDIV",
        "HLIL_FSQRT",
        "HLIL_FNEG",
        "HLIL_FABS",
        "HLIL_FLOAT_TO_INT",
        "HLIL_INT_TO_FLOAT",
        "HLIL_FLOAT_CONV",
        "HLIL_ROUND_TO_INT",
        "HLIL_FLOOR",
        "HLIL_CEIL",
        "HLIL_FTRUNC",
        "HLIL_FCMP_E",
        "HLIL_FCMP_NE",
        "HLIL_FCMP_LT",
        "HLIL_FCMP_LE",
        "HLIL_FCMP_GE",
        "HLIL_FCMP_GT",
        "HLIL_FCMP_O",
        "HLIL_FCMP_UO",
    ],
)
def test_unsupported_special_operations_raise(
    translation_module, fake_bv, il_expr, ops, operation
):
    with pytest.raises(
        Exception, match="Unsupported translation for special operation"
    ):
        tr(translation_module, fake_bv, il_expr(getattr(ops, operation), size=0))


def test_unknown_operation_raises(translation_module, fake_bv, il_expr):
    unknown = SimpleNamespace(name="HLIL_UNKNOWN")
    with pytest.raises(Exception, match="Unsupported translation for operation"):
        tr(translation_module, fake_bv, il_expr(unknown, size=0))
