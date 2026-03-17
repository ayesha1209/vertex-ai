"""Orchestrate document generation: prompt → OpenAI → parse → assemble.

Multi-product strategy
----------------------
When a row has N comma-separated products (N > 1), asking the AI to produce
N×3 technical documents (TDS + COA + MSDS per product) in one call causes
the response to be silently truncated — only the first 1–2 products get docs.

Fix: generate the quotation (all products) in one call, then generate
TDS/COA/MSDS for each individual product in its own separate call.
This keeps each call within the model's output-token budget.
"""

import uuid

from app.prompts.vertex_prompts import (
    SINGLE_PRODUCT_TECH_DOCS_TEMPLATE,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_TECH_DOCS_ONLY,
)
from app.schemas.document import DocumentCreate, DocumentType, RowPreview
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

# Products are considered "multi-product" when the product_name field
# contains a comma — the same threshold already used by the assembler.
_MULTI_PRODUCT_THRESHOLD = 2


def _split_products(product_name: str) -> list[str]:
    """Return individual product names from a comma-separated string."""
    return [p.strip() for p in product_name.split(",") if p.strip()]


def _parse_doc_types(row: RowPreview) -> set[DocumentType]:
    """
    Parse the optional doc_types hint from Excel.

    Examples (case-insensitive, comma-separated):
      - "" or None        -> all four: quotation, tds, coa, msds
      - "q,tds"           -> quotation + tds only
      - "tds, coa, msds"  -> tds + coa + msds
    """
    raw = (row.doc_types or "").strip()
    if not raw:
        return {DocumentType.quotation, DocumentType.tds, DocumentType.coa, DocumentType.msds}

    tokens = [t.strip().lower() for t in raw.replace(";", ",").split(",") if t.strip()]
    selected: set[DocumentType] = set()
    for t in tokens:
        if t in {"q", "quotation", "quote"}:
            selected.add(DocumentType.quotation)
        elif t in {"tds"}:
            selected.add(DocumentType.tds)
        elif t in {"coa"}:
            selected.add(DocumentType.coa)
        elif t in {"msds"}:
            selected.add(DocumentType.msds)

    if not selected:
        # If nothing recognised, fall back to all documents so we never
        # silently skip everything due to a typo in the Excel cell.
        return {DocumentType.quotation, DocumentType.tds, DocumentType.coa, DocumentType.msds}
    return selected


def _generate_tech_docs_for_product(
    single_product: str,
    row: RowPreview,
) -> tuple[str, str, str]:
    """
    Call OpenAI to generate TDS, COA, MSDS for a single product.
    Returns (tds_text, coa_text, msds_text).
    """
    prompt = SINGLE_PRODUCT_TECH_DOCS_TEMPLATE.format(
        product_name=single_product,
        company_name=(row.company_name or "").strip(),
        buyer_name=row.buyer_name or "",
        country=(row.country or row.unloading_country or "").strip(),
        manufacturer_name=(row.manufacturer_name or row.company_name or "").strip(),
        hsn_code=(row.hsn_code or "").strip(),
        cas_no=(row.cas_no or "").strip(),
        quantity=(row.quantity or "").strip(),
        unit=(row.unit or "").strip(),
        local_export=(row.local_export or "").strip(),
    )
    full_text = complete(SYSTEM_PROMPT_TECH_DOCS_ONLY, prompt, temperature=0.3)

    # Parse the three sections out of the response.
    # The response starts directly with "# TECHNICAL DATA SHEET (TDS) - …"
    # so we wrap it with a dummy quotation marker so split_four_sections works.
    wrapped = "# QUOTATION\n\n" + full_text
    try:
        _, tds_text, coa_text, msds_text = split_four_sections(wrapped)
    except Exception:
        tds_text = coa_text = msds_text = ""

    return tds_text, coa_text, msds_text


def generate_documents_for_row(row: RowPreview) -> list[DocumentCreate]:
    """
    Generate Quotation + TDS + COA + MSDS for a row.

    Single product  → 1 OpenAI call (original behaviour).
    Multiple products → 1 call for the full quotation, then 1 call per product
                        for its TDS/COA/MSDS, all sharing the same batch_id.
    """
    product_type = detect_product_type(row.product_name)
    allowed_doc_types = _parse_doc_types(row)
    products = _split_products(row.product_name)
    is_multi = len(products) >= _MULTI_PRODUCT_THRESHOLD

    # ------------------------------------------------------------------ #
    # Step 1: generate the quotation (always a single call)               #
    # ------------------------------------------------------------------ #
    user_prompt = build_user_prompt(row)

    terms_text = get_terms(product_type)
    if terms_text and terms_text.strip():
        user_prompt = (
            user_prompt
            + "\n\nIn the quotation's TERMS & CONDITIONS section (Section 5), use exactly the following text (keep the same structure and numbering):\n"
            + terms_text.strip()
        )

    if is_multi:
        # Ask the AI only for the quotation; skip TDS/COA/MSDS in this call.
        quotation_only_prompt = (
            user_prompt
            + "\n\nIMPORTANT: Output ONLY the # QUOTATION section (with all products in the items table and the TERMS & CONDITIONS). "
            "Do NOT output any TDS, COA, or MSDS sections in this response."
        )
        full_text = complete(SYSTEM_PROMPT, quotation_only_prompt, temperature=0.3)
        # full_text is quotation only — extract it
        try:
            quotation_text, _, _, _ = split_four_sections("# QUOTATION\n" + full_text)
            if not quotation_text.strip():
                quotation_text = full_text
        except Exception:
            quotation_text = full_text
        tds_combined = ""
        coa_combined = ""
        msds_combined = ""
    else:
        # Original single-call path
        full_text = complete(SYSTEM_PROMPT, user_prompt, temperature=0.3)
        try:
            quotation_text, tds_combined, coa_combined, msds_combined = split_four_sections(full_text)
        except Exception:
            idx = full_text.find(MARKER_COA)
            if idx >= 0:
                quotation_text = full_text[:idx].strip()
                if quotation_text.startswith("#"):
                    quotation_text = quotation_text.split("\n", 1)[-1].strip()
                rest = full_text[idx:].strip()
                coa_combined = rest.split("\n", 1)[-1].strip() if rest.startswith("#") else rest
                tds_combined = "Technical Data Sheet – use REFERENCE structure."
                msds_combined = "Material Safety Data Sheet – use REFERENCE structure."
            else:
                quotation_text = full_text
                tds_combined = coa_combined = msds_combined = ""

    batch_id = str(uuid.uuid4())
    quotation_no = (row.quotation_no or "").strip() or generate_quotation_no(row.company_name)

    buyer_name = row.buyer_name
    shared_kwargs = dict(
        product_type=product_type,
        batch_id=batch_id,
        employee_name=row.employee_name,
        letterhead=row.letterhead,
        quotation_no=quotation_no,
        company_name=row.company_name,
        local_export=row.local_export,
        hsn_code=row.hsn_code,
        quantity=row.quantity,
        unit=row.unit,
        country=row.country or row.unloading_country,
        port=row.port or row.port_of_loading or row.port_of_unloading,
        incoterm=row.incoterm or row.price_fob_cif,
        payment_terms=row.payment_terms,
        remarks=row.remarks,
    )

    if not is_multi:
        # Single product: original path, one assembly call
        docs = assemble_separate_documents(
            quotation_text,
            tds_combined,
            coa_combined,
            msds_combined,
            buyer_name,
            row.product_name,
            **shared_kwargs,
        )
        # Filter according to requested doc types from Excel
        return [d for d in docs if d.doc_type in allowed_doc_types]

    # ------------------------------------------------------------------ #
    # Step 2 (multi-product): one OpenAI call per individual product      #
    # for TDS/COA/MSDS, then assemble everything together.                #
    # ------------------------------------------------------------------ #

    all_docs: list[DocumentCreate] = []

    # Start with the quotation document only (if requested)
    if DocumentType.quotation in allowed_doc_types:
        quotation_docs = assemble_separate_documents(
            quotation_text,
            "",   # tds_text — will be added per product below
            "",   # coa_text
            "",   # msds_text
            buyer_name,
            row.product_name,
            **shared_kwargs,
        )
        # assemble_separate_documents adds placeholder "No TDS/COA/MSDS content"
        # docs when text is empty — keep only the quotation itself here.
        all_docs.extend(d for d in quotation_docs if d.doc_type == DocumentType.quotation)

    for single_product in products:
        try:
            p_tds, p_coa, p_msds = _generate_tech_docs_for_product(single_product, row)
        except Exception:
            p_tds = p_coa = p_msds = ""

        # Build tech docs for this product only (empty quotation_text so no
        # duplicate quotation is created; we already have it above).
        per_product_docs = assemble_separate_documents(
            "",      # quotation_text — already added above
            p_tds,
            p_coa,
            p_msds,
            buyer_name,
            single_product,
            **shared_kwargs,
        )
        # Keep only requested tech-doc types (skip quotation placeholder)
        all_docs.extend(
            d
            for d in per_product_docs
            if d.doc_type in allowed_doc_types and d.doc_type != DocumentType.quotation
        )

    return all_docs
