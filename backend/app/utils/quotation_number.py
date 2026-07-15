"""Quotation number: VERT/[SEQUENCE]/[YEAR] e.g. VERT/001/2026."""

from datetime import datetime
from typing import Optional

# Simple in-memory sequence per process (resets on restart). For production, use DB.
_sequence = 0


def generate_quotation_no(company_name: Optional[str] = None) -> str:
    """Generate next quotation number: VERT/SEQ/YEAR."""
    global _sequence
    _sequence += 1
    now = datetime.utcnow()
    year = now.year
    seq = f"{_sequence:03d}"
    return f"VERT/{seq}/{year}"


def build_quotation_no(seq: int) -> str:
    """Build a quotation number from a user-supplied sequence integer."""
    now = datetime.utcnow()
    return f"VERT/{seq:03d}/{now.year}"
