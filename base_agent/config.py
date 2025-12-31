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
MODEL_NAME = "gemini-2.5-pro"

# Base directories
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "base_agent" / "templates"
OUTPUT_DIR = BASE_DIR / "output"

# Template file path
TEMPLATE_EXCEL = TEMPLATES_DIR / "MM Excel Template.xlsx"

# GCS config for master Excel
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GCS_MASTER_EXCEL_BLOB = os.getenv("GCS_MASTER_EXCEL_BLOB")
