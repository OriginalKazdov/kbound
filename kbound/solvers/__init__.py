"""Solver layer — typed RCE solvers + dispatcher.

Most users should call `kbound.recover_rule(...)` rather than reach into this
module directly. The dispatcher is exposed for advanced callers that want to
bypass classification and call a specific solver.

Public surface:

    dispatch              — geometry/family-aware solver router
    verify                — re-check a recovered rule against the support set
"""

from kbound.solvers import verify
from kbound.solvers.dispatcher import dispatch

__all__ = ["dispatch", "verify"]
