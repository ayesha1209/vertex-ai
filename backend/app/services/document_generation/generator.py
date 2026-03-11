"""Orchestrate document generation: prompt → OpenAI → parse → assemble."""

import uuid

from app.prompts.vertex_prompts import SYSTEM_PROMPT
from app.schemas.document import DocumentCreate, RowPreview

from app.services.document_generation.assembler import assemble_separate_documents
from app.services.document_generation.openai_client import complete
from app.services.document_generation.product_type import detect_product_type
from app.services.document_generation.prompt_builder import build_user_prompt
from app.utils.quotation_number import generate_quotation_no
from app.services.document_generation.response_parser import (
    MARKER_COA,
    split_four_sections,
)
from app.services.terms_service import get_terms


def generate_documents_for_row(row: RowPreview) -> list[DocumentCreate]:
    """Generate four separate documents: Quotation, TDS, COA, MSDS. Quotation terms come from editable Terms (injected into prompt)."""
    product_type = detect_product_type(row.product_name)
    user_prompt = build_user_prompt(row)

    # Inject editable terms so the AI outputs them in the quotation (Section 5) — single source, no duplicate
    terms_text = get_terms(product_type)
    if terms_text and terms_text.strip():
        user_prompt = (
            user_prompt
            + "\n\nIn the quotation's TERMS & CONDITIONS section (Section 5), use exactly the following text (keep the same structure and numbering):\n"
            + terms_text.strip()
        )

    full_text = complete(SYSTEM_PROMPT, user_prompt, temperature=0.3)

    try:
        quotation_text, tds_text, coa_text, msds_text = split_four_sections(full_text)
    except Exception:
        idx = full_text.find(MARKER_COA)
        if idx >= 0:
            quotation_text = full_text[:idx].strip()
            if quotation_text.startswith("#"):
                quotation_text = quotation_text.split("\n", 1)[-1].strip()
            rest = full_text[idx:].strip()
            coa_text = rest.split("\n", 1)[-1].strip() if rest.startswith("#") else rest
            tds_text = "Technical Data Sheet – use REFERENCE structure."
            msds_text = "Material Safety Data Sheet – use REFERENCE structure."
        else:
            quotation_text = full_text
            tds_text = coa_text = msds_text = ""

    batch_id = str(uuid.uuid4())
    quotation_no = (row.quotation_no or "").strip() or generate_quotation_no(row.company_name)

    return assemble_separate_documents(
        quotation_text,
        tds_text,
        coa_text,
        msds_text,
        row.buyer_name,
        row.product_name,
        product_type,
        batch_id=batch_id,
        employee_name=row.employee_name,
        letterhead=row.letterhead,
        quotation_no=quotation_no,
        company_name=row.company_name,
        local_export=row.local_export,
    )
