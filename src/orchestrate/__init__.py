"""End-to-end orchestration across transdub stages.

Composes the independent, pure stages (download → translate → …) into a
runnable flow. This is the seam a workflow framework (Prefect/Temporal/…)
would later replace; stages stay decoupled and unaware of each other.
"""
