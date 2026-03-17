"""Backward-compat re-export — real implementation in app/infrastructure/vector/note_text_builder."""

from app.infrastructure.vector.note_text_builder import NoteText, build_note_text

__all__ = ["NoteText", "build_note_text"]
