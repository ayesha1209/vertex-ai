"""
Backward compatibility: re-export from document_generation.
Logic lives in app/services/document_generation/ (client, prompt_builder, response_parser, assembler, generator).
"""

from app.services.document_generation import generate_documents_for_row

__all__ = ["generate_documents_for_row"]
