"""
Static COA/TDS/MSDS templates for prompts (no DOCX loading at runtime).
Templates are in reference_templates_generated.py, built by scripts/build_reference_templates.py
when docs/*.docx change.
"""

try:
    from app.prompts.reference_templates_generated import (
        COA_TEMPLATE,
        MSDS_TEMPLATE,
        TDS_TEMPLATE,
    )
except ImportError:
    COA_TEMPLATE = ""
    TDS_TEMPLATE = ""
    MSDS_TEMPLATE = ""


def get_coa_template() -> str:
    return COA_TEMPLATE


def get_tds_template() -> str:
    return TDS_TEMPLATE


def get_msds_template() -> str:
    return MSDS_TEMPLATE
