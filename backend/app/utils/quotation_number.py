"""Quotation number: [COMPANY CODE]/[SEQUENCE]/[YY]/[MONTH] e.g. AK/01/25/155."""

import re
from datetime import datetime
from typing import Optional

# Simple in-memory sequence per process (resets on restart). For production, use DB.
_sequence = 0


def _company_code(company_name: Optional[str], default: str = "VT") -> str:
    """First 2-3 letters of Company Name, uppercase letters only."""
    if not company_name or not str(company_name).strip():
        return default
    s = re.sub(r"[^A-Za-z]", "", str(company_name).strip())[:3].upper()
    return s[:2] if len(s) >= 2 else (s or default)


def generate_quotation_no(company_name: Optional[str] = None) -> str:
    """Generate next quotation number: COMPANY_CODE/SEQ/YY/MM."""
    global _sequence
    _sequence += 1
    code = _company_code(company_name)
    now = datetime.utcnow()
    yy = str(now.year)[-2:]
    mm = f"{now.month:02d}"
    seq = f"{_sequence:03d}"
    return f"{code}/{seq}/{yy}/{mm}"
