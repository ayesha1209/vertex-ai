"""Orchestrate document generation: prompt → OpenAI → parse → assemble."""

from app.prompts.vertex_prompts import SYSTEM_PROMPT
from app.schemas.document import DocumentCreate, RowPreview

from app.services.document_generation.assembler import assemble_combined_document
from app.services.document_generation.openai_client import complete
from app.services.document_generation.product_type import detect_product_type
from app.services.document_generation.prompt_builder import build_user_prompt
from app.services.document_generation.response_parser import (
    MARKER_COA,
    split_four_sections,
)


def generate_documents_for_row(row: RowPreview) -> list[DocumentCreate]:
    """Generate one combined document: Quotation → TDS → COA → MSDS (exact format from reference)."""
    product_type = detect_product_type(row.product_name)
    user_prompt = build_user_prompt(row)

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

    doc = assemble_combined_document(
        quotation_text, tds_text, coa_text, msds_text,
        row.buyer_name, row.product_name, product_type,
    )
    return [doc]
