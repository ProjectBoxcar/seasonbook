"""Season Book — Wright/Malécot genetics on the real AOA certificate herd.

Standalone package. Does not modify AlpacaManager or Hereditas.
Science is the same as Hereditas: F of a cria is the Malécot coancestry of
its parents, expanded by topological pedigree depth.
"""

from .wright import (
    DEFAULT_PEDIGREE_DEPTH,
    PedigreeNode,
    coancestry,
    expected_offspring_f,
    interpret_f,
    mean_kinship,
    wright_f,
    wright_paths,
)

__all__ = [
    "DEFAULT_PEDIGREE_DEPTH",
    "PedigreeNode",
    "coancestry",
    "expected_offspring_f",
    "interpret_f",
    "mean_kinship",
    "wright_f",
    "wright_paths",
]

__version__ = "2.0.0"
