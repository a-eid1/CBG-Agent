# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Top level agent"""

import base64
import json
import logging
import os
from datetime import date
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import load_artifacts

from google.genai import types

from .prompts import return_instructions_root

# --- OpenTelemetry / Weave setup ---------------------------------------------

ENABLE_WANDB_TRACING = os.getenv("ENABLE_WANDB_TRACING", "false").lower() == "true"
if ENABLE_WANDB_TRACING:

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk import trace as trace_sdk
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    # Configure Weave endpoint and authentication
    _WANDB_BASE_URL = "https://trace.wandb.ai"
    _WANDB_PROJECT_ID = os.getenv("WANDB_PROJECT_ID")
    _OTEL_EXPORTER_OTLP_ENDPOINT = f"{_WANDB_BASE_URL}/otel/v1/traces"

    # Set up authentication
    _WANDB_API_KEY = os.getenv("WANDB_API_KEY")
    _WANDB_AUTH = base64.b64encode(f"api:{_WANDB_API_KEY}".encode()).decode()

    _OTEL_EXPORTER_OTLP_HEADERS = {
        "Authorization": f"Basic {_WANDB_AUTH}",
        "project_id": _WANDB_PROJECT_ID,
    }

    # Create the OTLP span exporter with endpoint and headers
    exporter = OTLPSpanExporter(
        endpoint=_OTEL_EXPORTER_OTLP_ENDPOINT,
        headers=_OTEL_EXPORTER_OTLP_HEADERS,
    )

    # Create a tracer provider and add the exporter
    _tracer_provider = trace_sdk.TracerProvider()
    _tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Set the global tracer provider BEFORE importing/using ADK
    trace.set_tracer_provider(_tracer_provider)

    # Set up logging
    # Note this level can be overridden by adk web on the command line;
    # e.g. running `adk web --log_level DEBUG` or `adk web -v`
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)

# --- Logging setup ----------------------------------------------------------

import google.cloud.logging

IS_RUNNING_IN_GCP = os.getenv("K_SERVICE") is not None

if IS_RUNNING_IN_GCP:
    # In Agent Engine / Cloud Run
    client = google.cloud.logging.Client()
    client.setup_logging()
    logging.basicConfig(level=logging.INFO)
    logging.info("Running in GCP. Configured Google Cloud Logging.")
else:
    # Local dev (adk web, etc.)
    logging.basicConfig(level=logging.INFO)
    logging.info("Running locally. Using basic console logging.")

logger = logging.getLogger(__name__)
logger.info("Libraries imported and logging configured.")

# --- Root Agent Definition ----------------------------------------------------

def get_root_agent() -> LlmAgent:
    tools = [load_artifacts]
    agent = LlmAgent(
        model=os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash"),
        name="meeting_insights_root_agent",
        instruction=return_instructions_root(),
        global_instruction=(
            f"""
            You are an Information Agent System.
            Todays date: {date.today()}
            """
        ),
        tools=tools,  # type: ignore
        generate_content_config=types.GenerateContentConfig(temperature=0.01),
    )

    return agent


# Fetch the root agent
root_agent = get_root_agent()
