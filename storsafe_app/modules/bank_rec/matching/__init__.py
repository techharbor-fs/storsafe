"""
Bank Reconciliation Matching Engine Package.

Provides the 7-pass auto-matching algorithm.
"""

from .engine import run_auto_matching, MatchingResult

__all__ = ['run_auto_matching', 'MatchingResult']
