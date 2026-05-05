"""Classifier layer — geometry detection and family identification.

Public surface:

    classify_geometry      — spatial / algebraic / borderline + features
    identify_family        — algebraic subfamily detection (lcg, polycoef, …)
"""

from kbound.classifier.family_id import identify_family
from kbound.classifier.oracle_classifier import classify_geometry

__all__ = ["classify_geometry", "identify_family"]
