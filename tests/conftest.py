import enum
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


HLIL_OPERATION_NAMES = (
    "HLIL_IF",
    "HLIL_JUMP",
    "HLIL_LABEL",
    "HLIL_ASSIGN_MEM_SSA",
    "HLIL_DEREF",
    "HLIL_DEREF_SSA",
    "HLIL_DEREF_FIELD",
    "HLIL_DEREF_FIELD_SSA",
    "HLIL_ASSIGN_UNPACK_MEM_SSA",
    "HLIL_VAR_INIT",
    "HLIL_ADDRESS_OF",
    "HLIL_CONST_PTR",
    "HLIL_IMPORT",
    "HLIL_EXTERN_PTR",
    "HLIL_VAR_INIT_SSA",
    "HLIL_ASSIGN",
    "HLIL_STRUCT_FIELD",
    "HLIL_ARRAY_INDEX",
    "HLIL_ARRAY_INDEX_SSA",
    "HLIL_SPLIT",
    "HLIL_VAR",
    "HLIL_VAR_SSA",
    "HLIL_CONST",
    "HLIL_ADD",
    "HLIL_ADC",
    "HLIL_SUB",
    "HLIL_SBB",
    "HLIL_AND",
    "HLIL_OR",
    "HLIL_XOR",
    "HLIL_MUL",
    "HLIL_MULU_DP",
    "HLIL_MULS_DP",
    "HLIL_DIVU",
    "HLIL_DIVS",
    "HLIL_ASR",
    "HLIL_LSL",
    "HLIL_LSR",
    "HLIL_DIVU_DP",
    "HLIL_DIVS_DP",
    "HLIL_MODU",
    "HLIL_MODU_DP",
    "HLIL_MODS",
    "HLIL_MODS_DP",
    "HLIL_ROR",
    "HLIL_ROL",
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
    "HLIL_BOOL_TO_INT",
    "HLIL_NEG",
    "HLIL_NOT",
    "HLIL_LOW_PART",
    "HLIL_ZX",
    "HLIL_SX",
    "HLIL_RET",
    "HLIL_GOTO",
    "HLIL_CASE",
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
)


HighLevelILOperation = enum.Enum("HighLevelILOperation", HLIL_OPERATION_NAMES)


class BinaryView:
    pass


class ExpressionIndex:
    pass


class Variable:
    pass


class Function:
    pass


class HighLevelILInstruction:
    pass


class BackgroundTaskThread:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass


class PluginCommand:
    @staticmethod
    def register(*_args, **_kwargs):
        pass

    @staticmethod
    def register_for_function(*_args, **_kwargs):
        pass

    @staticmethod
    def register_for_high_level_il_instruction(*_args, **_kwargs):
        pass


class Settings:
    def register_group(self, *_args, **_kwargs):
        pass

    def register_setting(self, *_args, **_kwargs):
        pass

    def get_integer(self, *_args, **_kwargs):
        return 1

    def get_string(self, *_args, **_kwargs):
        return ""


LowLevelILOperation = enum.Enum("LowLevelILOperation", ("LLIL_UNDEF",))


def _install_binaryninja_stubs() -> None:
    binaryninja = types.ModuleType("binaryninja")
    binaryview = types.ModuleType("binaryninja.binaryview")
    function = types.ModuleType("binaryninja.function")
    highlevelil = types.ModuleType("binaryninja.highlevelil")
    log = types.ModuleType("binaryninja.log")
    lowlevelil = types.ModuleType("binaryninja.lowlevelil")
    plugin = types.ModuleType("binaryninja.plugin")
    settings = types.ModuleType("binaryninja.settings")
    variable = types.ModuleType("binaryninja.variable")

    binaryninja.PluginCommand = PluginCommand
    binaryview.BinaryView = BinaryView
    function.Function = Function
    highlevelil.ExpressionIndex = ExpressionIndex
    highlevelil.HighLevelILInstruction = HighLevelILInstruction
    highlevelil.HighLevelILOperation = HighLevelILOperation
    log.log_debug = lambda *_args, **_kwargs: None
    log.log_error = lambda *_args, **_kwargs: None
    lowlevelil.LowLevelILOperation = LowLevelILOperation
    plugin.BackgroundTaskThread = BackgroundTaskThread
    settings.Settings = Settings
    variable.Variable = Variable

    sys.modules["binaryninja"] = binaryninja
    sys.modules["binaryninja.binaryview"] = binaryview
    sys.modules["binaryninja.function"] = function
    sys.modules["binaryninja.highlevelil"] = highlevelil
    sys.modules["binaryninja.log"] = log
    sys.modules["binaryninja.lowlevelil"] = lowlevelil
    sys.modules["binaryninja.plugin"] = plugin
    sys.modules["binaryninja.settings"] = settings
    sys.modules["binaryninja.variable"] = variable


_install_binaryninja_stubs()


def _install_networkx_stub_if_missing() -> None:
    if importlib.util.find_spec("networkx") is not None:
        return

    networkx = types.ModuleType("networkx")

    class DiGraph:
        def add_node(self, *_args, **_kwargs):
            pass

        def add_edge(self, *_args, **_kwargs):
            pass

    networkx.DiGraph = DiGraph
    networkx.strongly_connected_components = lambda *_args, **_kwargs: []
    networkx.condensation = lambda *_args, **_kwargs: DiGraph()
    networkx.topological_sort = lambda *_args, **_kwargs: []
    networkx.single_source_shortest_path_length = lambda *_args, **_kwargs: {}
    sys.modules["networkx"] = networkx


_install_networkx_stub_if_missing()


@pytest.fixture(scope="session")
def ops():
    return HighLevelILOperation


@pytest.fixture(scope="session")
def fake_bv():
    return SimpleNamespace(arch=SimpleNamespace(address_size=8))


@pytest.fixture(scope="session")
def translation_module():
    pytest.importorskip("miasm.expression.expression")
    translation_path = (
        Path(__file__).resolve().parents[1]
        / "obfuscation_analysis"
        / "mba"
        / "translation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "obfuscation_analysis_mba_translation_under_test", translation_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def il_expr(ops):
    def make(operation, size=4, **operands):
        return SimpleNamespace(
            operation=operation,
            size=size,
            core_instr=operation.name,
            **operands,
        )

    return make


@pytest.fixture
def const(il_expr, ops):
    def make(value, size=4):
        return il_expr(ops.HLIL_CONST, size=size, constant=value)

    return make


@pytest.fixture
def var():
    def make(name, width=4, version=0):
        return SimpleNamespace(
            name=name,
            version=version,
            type=SimpleNamespace(width=width),
        )

    return make
