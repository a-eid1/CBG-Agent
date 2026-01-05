"""Tools package.

Step 1: PDF parsing
Step 3: PPTX rendering
"""

from .pdf_parser import parse_jd_pdf
from .brain_tool import generate_competency_model
from .competency_generator import (
    generate_competency_slides,
    validate_template_placeholders,
    default_output_name,
    render_competency_pptx,
)

__all__ = [
    "parse_jd_pdf",
    "generate_competency_model",
    "generate_competency_slides",
    "render_competency_pptx",
    "validate_template_placeholders",
    "default_output_name",
]
