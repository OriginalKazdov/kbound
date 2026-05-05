"""Compositional rule recovery layer (typed atoms + active query over chains).

Public surface:

    ATOMS                       — registry of typed atomic transforms
    Atom                        — abstract base for new atoms
    synthesize / predict        — depth-2 compositional synthesis (passive)
    ActiveCompositionSession    — stateful active session over compositions
    Composition                 — depth-1 / depth-2 composition object
"""

from kbound.compositional.active_compose import (
    ActiveCompositionSession,
    Composition,
    enumerate_consistent_compositions,
    expected_info_gain_compose,
)
from kbound.compositional.atoms import (
    ATOMS,
    AffineMod,
    Atom,
    BitShiftRight,
    ConstAdd,
    Identity,
    ModReduce,
    Power,
    XorConst,
)
from kbound.compositional.search import predict, synthesize

__all__ = [
    "ATOMS",
    "Atom",
    "AffineMod",
    "ModReduce",
    "Power",
    "ConstAdd",
    "Identity",
    "XorConst",
    "BitShiftRight",
    "synthesize",
    "predict",
    "ActiveCompositionSession",
    "Composition",
    "enumerate_consistent_compositions",
    "expected_info_gain_compose",
]
