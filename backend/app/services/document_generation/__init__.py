"""Document generation: separated logic (client, prompts, parser, assembler, generator)."""

from app.services.document_generation.generator import generate_documents_for_row

__all__ = ["generate_documents_for_row"]
