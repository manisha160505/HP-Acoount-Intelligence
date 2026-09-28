"""The regeneration engine: one path from "an input changed" to a committed output.

Every generated widget belongs to exactly one producer. A producer's output is
committed as one document, so a reader sees all of a run or none of it. Whether
a stored output is current is decided by comparing fingerprints, never by a
flag someone remembered to set.

Design: project-documentation/07_Internal_Generated/Engineering/
REGENERATION_DESIGN_2026-09-27.md
"""
