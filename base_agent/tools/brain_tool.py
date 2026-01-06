"""Step 2 (Brain) as an ADK Function Tool wrapper.

The pipeline is designed as:

1) Parser (tool): PDF -> structured JD JSON
2) Brain (LLM): JD JSON -> Competency JSON contract
3) Renderer (tool): contract -> PPTX

In ADK, the Root Agent can either generate the Step-2 JSON directly in its own
reasoning, or call this wrapper to delegate to :func:`base_agent.brain.generate_competency_json`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import base64

from . import brain as _brain
from ..config import BRAIN_MODEL, RULEBOOK_PDF_PATH


async def generate_competency_model(
    job: Dict[str, Any],
    chosen_competency: Optional[str] = None,
    model_name: str = "gemini-2.5-pro",
    rulebook_artifact_filename: Optional[str] = None,
    tool_context=None,
) -> Dict[str, Any]:
    """
    [Step 2] Generates the Competency Matrix JSON based on Government Standards.

    This tool acts as the "Brain". It takes the raw Job Description (from Step 1),
    applies the logic from the 2025 Competency Rulebook (Bloom's Taxonomy), and
    produces the structured content required for the PowerPoint slide.

    Args:
        job: The structured job data dict returned by `parse_jd_pdf`.
        chosen_competency: If the AI was unsure previously, this is the user's manual selection.
        model_name: The Gemini model version.
        rulebook_artifact_filename: Optional PDF to use as a reference source (e.g., the Rulebook).
        tool_context: ADK context (injected automatically).

    Returns:
        A dictionary containing the full competency matrix (Main competency, sub-topics,
        and 4 proficiency levels) ready for rendering.
    """

    # Optional rulebook context via artifact
    rulebook_bytes: Optional[bytes] = None
    if rulebook_artifact_filename and tool_context is not None:
        try:
            part = await tool_context.load_artifact(filename=rulebook_artifact_filename)
            
            if isinstance(part, dict) and "inlineData" in part:
                b64 = part["inlineData"].get("data")
                if b64: rulebook_bytes = base64.b64decode(b64)
            elif part and getattr(part, "inline_data", None):
                rulebook_bytes = part.inline_data.data
            elif part and hasattr(part, "data"):
                rulebook_bytes = part.data
            
        except Exception:
            rulebook_bytes = None
    
    if BRAIN_MODEL:
        model_name = BRAIN_MODEL

    out = _brain.generate_competency_json(
        job_payload=job,
        model_name=model_name,
        rulebook_pdf_path=RULEBOOK_PDF_PATH or None,
        rulebook_pdf_bytes=rulebook_bytes,
        retry=1,
        chosen_competency=chosen_competency,
    )

    if isinstance(out, list):
        return {
            "mode": "ok",
            "data": [x.model_dump() if hasattr(x, "model_dump") else x for x in out],
        }

    return {
        "mode": "clarification",
        "data": out.model_dump() if hasattr(out, "model_dump") else out,
    }
