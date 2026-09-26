"""Aeron environmental monitoring: normalization, freshness, persistence and ingestion.

The verified source contract is documented in ``AERON_REAL_API_CONTRACT.md``.
Public reads never contact Aeron; only the separate worker does.
"""
