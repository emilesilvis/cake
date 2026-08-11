"""Shared Cake domain and portfolio interface."""

from .domain import (
    CakeError,
    canonical_ref,
    format_cake_contract,
    format_slice_contract,
    parse_cake_contract,
    parse_slice_contract,
    parse_slice_source,
    preview_transition,
    token_for,
    validate_snapshot,
)
from .portfolio import CakePortfolio
from .slicing import CakeSlicer

__all__ = [
    "CakeError",
    "CakePortfolio",
    "CakeSlicer",
    "canonical_ref",
    "format_cake_contract",
    "format_slice_contract",
    "parse_cake_contract",
    "parse_slice_contract",
    "parse_slice_source",
    "preview_transition",
    "token_for",
    "validate_snapshot",
]
