import os
import vertexai
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Cloud Project configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# VertexAI init
vertexai.init(project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)

# Model configuration
ROOT_AGENT_MODEL = os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-pro")
PARSER_MODEL = os.getenv("PARSER_MODEL", "gemini-2.5-pro")
BRAIN_MODEL = os.getenv("BRAIN_MODEL", "gemini-2.5-pro")

# Base directories
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "base_agent" / "templates"
TEMPLATE_PPTX = TEMPLATES_DIR / "template.pptx"

RULEBOOK_PDF_PATH = os.getenv("RULEBOOK_PDF_PATH", "")

# GCS config for output
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
GCS_PREFIX = os.getenv("GCS_PREFIX", "")
GCS_RETURN_SIGNED_URL = os.getenv("GCS_RETURN_SIGNED_URL", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}
try:
    GCS_SIGNED_URL_TTL_SECONDS = int(os.getenv("GCS_SIGNED_URL_TTL_SECONDS", "3600"))
except ValueError:
    GCS_SIGNED_URL_TTL_SECONDS = 3600
