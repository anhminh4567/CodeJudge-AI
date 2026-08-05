"""Light RAG: extract -> chunk -> embed -> flat-file store -> retrieve.

Deliberately minimal (no vector DB) per the design's D6 — cosine similarity over
a modest number of vectors is all a personal-scale doc set needs.
"""
