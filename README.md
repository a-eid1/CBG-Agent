# Meeting Insights Agent

This project is a **specialized version** of the original Data Science multi-agent sample.  
It has been simplified to focus on a **single BigQuery dataset**: a table of meeting minutes
named `minutes`. The agent lets users ask **natural-language questions** about meetings and,
when useful, generate **charts and visual summaries** of the results.

Compared to the original sample, this version:

- Uses **BigQuery only** (no AlloyDB).
- Does **not** include a BQML/RAG sub-agent.
- Focuses on a single table that stores **meeting minutes**.

---

## Overview

The Meeting Insights Agent is a conversational system that:

- Translates natural-language questions (Arabic or English) into **BigQuery SQL**.
- Executes queries against a `minutes` table in BigQuery.
- Optionally runs **Python analytics** (pandas + matplotlib) on the query result.
- Returns both **text summaries** and **visualizations** (plots/graphs).

It is implemented using the **Google AI Agent Developer Kit (ADK)** and can be:

- Run locally via the ADK CLI / Web UI.
- Deployed to **Vertex AI Agent Engine**.
- Deployed to **Google Cloud Run**.

---

## What the `minutes` table represents

The `minutes` BigQuery table is a **log of meetings**.

- **One row = one meeting minutes document** (one meeting, even if there are many agenda items).
- Columns capture:
  - Basic metadata (date, time, place, attendees).
  - The main discussion and decisions.
  - Follow-up plans, responsibilities, and target dates.

Think of it as a **“meeting summary warehouse”** that can answer questions like:

- What meetings happened, when, and about what?
- Who tends to attend which kinds of meetings?
- What was decided and what follow-up is needed?
- How a project or initiative evolves over several meetings.

### Table Schema

| Column Name        | Type   | Description                                                                 |
|--------------------|--------|-----------------------------------------------------------------------------|
| `id`               | INT64  | Meeting ID (YY + WeekNumber(2 digits) + MeetingNumberWithinWeek).           |
| `week_number`      | INT64  | Meeting ISO week number.                                                    |
| `meeting_date`     | DATE   | Meeting date in `YYYY-MM-DD`.                                               |
| `details`          | STRING | Compact text with time, location, rapporteur / minute-taker.                |
| `attendees`        | STRING | Free-text list of attendees (names, titles, units).                         |
| `meeting_topic`    | STRING | Short description of the meeting topic.                                     |
| `meeting_purpose`  | STRING | Purpose of the meeting (e.g., planning, follow-up, workshop).               |
| `summary`          | STRING | Summary of discussions and key themes.                                      |
| `target_date`      | STRING | Follow-up dates or timeframes (stored as text).                             |
| `future_plan`      | STRING | Planned next steps and future work.                                         |
| `decisions`        | STRING | Main decisions and action points.                                           |
| `responsible`      | STRING | Main responsible party or unit for follow-up.                               |
| `notes`            | STRING | Extra comments (currently often empty, reserved for annotations).           |

Users do **not** have to know these column names.  
They interact using natural language about:

- Meetings, dates, topics, projects, initiatives.
- Attendees and departments.
- Decisions, next steps, and responsibilities.

---

## Agent Details

**Interaction Type:** Conversational  
**Complexity:** Intermediate  
**Agent Type:** Multi-Agent (simplified)  

**Components:**

- Root agent (Meeting Insights root agent).
- BigQuery sub-agent (NL → SQL → BigQuery).
- Analytics sub-agent (“Python / notebook-style” analysis + charts).
- ADK Web UI (optional).
- Vertex AI Code Interpreter (for running Python).

**Vertical:** Any organization that needs to explore **meeting minutes** in a structured way.

---

## Architecture (Simplified)

This simplified architecture has three key agents:

1. **Meeting Insights Root Agent**
   - Receives all user messages.
   - Understands user intent and the meeting-minutes domain.
   - Routes to:
     - `call_bigquery_agent` – when data retrieval is needed.
     - `call_analytics_agent` – when further analysis or charts are requested.

2. **BigQuery Agent**
   - Uses **ADK’s Built-in BigQuery Tools** to:
     - Translate natural language into SQL (NL2SQL).
     - Execute queries against the `minutes` table.
   - Returns:
     - SQL text.
     - Raw query results.
     - A basic natural-language summary.

3. **Analytics (Python) Agent**
   - Uses a **Vertex AI Code Interpreter** extension.
   - Receives the query results as pandas DataFrames.
   - Implements “NL → Python”:
     - Aggregations and transformations.
     - Trends over time.
     - Bar charts, line charts, other plots using matplotlib.
   - Returns:
     - A detailed explanation.
     - References to generated charts.

All AlloyDB-related and BQML/RAG components from the original sample have been removed or are unused in this configuration.

---

## Key Features

- **Natural-Language Queries**  
  Users can ask questions like:
  - “How many meetings were held between September and November 2025?”
  - “Which meetings were about the digital twin project?”
  - “Who appears most frequently in these meetings?”

- **BigQuery NL2SQL**  
  The BigQuery sub-agent uses:
  - A Gemini-based NL2SQL approach (`BASELINE`) or
  - The CHASE-SQL method (`CHASE`),
  depending on the `NL2SQL_METHOD` environment variable.

- **Python Analytics + Visuals**  
  The analytics sub-agent:
  - Runs Python in a managed environment.
  - Uses pandas and matplotlib for analysis and plots.
  - Produces charts (e.g., meeting counts per month, per topic, per responsible unit).

- **ADK Web UI & CLI**  
  You can interact with the agent via:
  - `uv run adk run data_science` (CLI).
  - `uv run adk web` (Web UI).

- **Agent Engine & Cloud Run Deployment**  
  - Deploy the agent to **Vertex AI Agent Engine** for managed conversational workflows.
  - Optionally deploy to **Cloud Run** with an ADK Web UI for internal dashboards.

---

## Prerequisites

You will need:

- **Google Cloud Account** with:
  - BigQuery enabled.
  - Vertex AI enabled.
- **Python 3.12+**.
- **uv** as the Python package/virtual environment manager.  
  Install from: https://docs.astral.sh/uv/getting-started/installation/
- **git** for cloning the repository.
- A BigQuery dataset containing the `minutes` table (or a similar table with the schema described above).

---

## Project Setup with `uv`

1. **Clone the Repository**

    git clone https://github.com/a-eid1/Meeting-Records-Insights-Agent.git  

2. **Install Dependencies**

    uv sync

3. **Activate the Environment (if using uv’s default .venv)**

    source .venv/bin/activate

4. **Create and Configure `.env`**

   Copy `.env.example` to `.env` and set required fields.  
   At minimum:

    GOOGLE_GENAI_USE_VERTEXAI=1

    GOOGLE_CLOUD_PROJECT="your-gcp-project-id"  
    GOOGLE_CLOUD_LOCATION="your-vertex-region"  # e.g. "us-central1"

    BQ_DATA_PROJECT_ID="your-data-project-id"  
    BQ_COMPUTE_PROJECT_ID="your-compute-project-id"    # can be same as data project  
    BQ_DATASET_ID="your_bigquery_dataset"              # dataset containing the minutes table

    ROOT_AGENT_MODEL="gemini-2.5-pro"  
    BIGQUERY_AGENT_MODEL="gemini-2.5-pro"  
    ANALYTICS_AGENT_MODEL="gemini-2.5-pro"  
    BASELINE_NL2SQL_MODEL="gemini-2.5-pro"  
    CHASE_NL2SQL_MODEL="gemini-2.5-pro"  
    NL2SQL_METHOD="BASELINE"   # or "CHASE"

    CODE_INTERPRETER_EXTENSION_NAME=""  # leave blank to create one automatically

    DATASET_CONFIG_FILE="./my_minutes_dataset_config.json"

---

## Dataset Configuration

The agent uses a small JSON file to describe the datasets it can access.  
In this simplified setup, you typically configure **one BigQuery dataset** that contains the `minutes` table.

### Example: `my_minutes_dataset_config.json`

Create this file at the root of the `data-science` agent directory:

    {
      "datasets": [
        {
          "type": "bigquery",
          "name": "minutes_dataset",
          "description": "BigQuery dataset containing the `minutes` table with meeting minutes: one row per meeting, including date, attendees, topic, decisions, and follow-up plans."
        }
      ]
    }

Set:

    DATASET_CONFIG_FILE="./my_minutes_dataset_config.json"

in your `.env` file.

> Note: In this simplified fork, **cross-dataset joins** and **AlloyDB datasets** are not used.  
> Only the BigQuery dataset(s) described here are considered.

---

## BigQuery Setup (Minutes Table)

1. Ensure BigQuery is enabled in your project and you have appropriate IAM roles.
2. Create (or reuse) a dataset, e.g.:

    bq mk --location="$GOOGLE_CLOUD_LOCATION" "$BQ_DATA_PROJECT_ID:$BQ_DATASET_ID"

3. Create and populate the `minutes` table with the schema described in the “What the `minutes` table represents” section.

4. Verify that:
   - `BQ_DATA_PROJECT_ID`, `BQ_COMPUTE_PROJECT_ID`, and `BQ_DATASET_ID` in `.env` are correct.
   - Your credentials allow querying this dataset.

---

## Running the Agent Locally

From the `python/agents/data-science` directory:

1. **CLI Mode**

    uv run adk run data_science

   You can then chat with the Meeting Insights Agent in the terminal.

2. **ADK Web UI**

    uv run adk web

   Open the printed URL in a browser and select `data_science` from the dropdown.

---

## Example Interaction (Minutes Table)

**User:**  
> What data do you have access to?

**Meeting Insights Agent:**  
> I have access to a BigQuery dataset containing a `minutes` table. Each row is one meeting, with columns like `meeting_date`, `attendees`, `meeting_topic`, `summary`, `decisions`, `future_plan`, and `responsible`.

**User:**  
> How many meetings do we have recorded so far, and between which dates?

**Meeting Insights Agent:**  
> Result: There are 134 meetings recorded. They span from 2024-02-10 to 2025-12-01.  
> Explanation: I queried the `minutes` table to count all rows and compute the minimum and maximum `meeting_date`.

**User:**  
> Please create a bar chart showing the number of meetings per month.

**Meeting Insights Agent:**  
> Result: I generated a bar chart of total meetings per calendar month. The busiest month was October 2025.  
> Explanation: I first used the BigQuery agent to retrieve the count of meetings grouped by month based on `meeting_date`. Then I used the analytics agent to plot the results as a bar chart using matplotlib.

**User:**  
> Which meetings were about the Green Corridor 2030 initiative?

**Meeting Insights Agent:**  
> Result: I found 7 meetings related to the Green Corridor 2030 initiative. These span from 2025-03-15 to 2025-10-27.  
> Explanation: I queried the `minutes` table for rows where the topic or summary mentioned “Green Corridor 2030” and listed the corresponding dates and short descriptions.

---

## Deployment on Vertex AI Agent Engine

### Initial Setup

1. Follow the official Agent Engine setup guide:  
   https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/set-up

2. Ensure the Vertex AI Reasoning Engine service account has:

    export RE_SA="service-${GOOGLE_CLOUD_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"  
    gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} \
        --member="serviceAccount:${RE_SA}" \
        --condition=None \
        --role="roles/bigquery.user"  
    gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} \
        --member="serviceAccount:${RE_SA}" \
        --condition=None \
        --role="roles/bigquery.dataViewer"  
    gcloud projects add-iam-policy-binding ${GOOGLE_CLOUD_PROJECT} \
        --member="serviceAccount:${RE_SA}" \
        --condition=None \
        --role="roles/aiplatform.user"

### Build Wheel and Deploy

From the `meeting-records-insights-agent` directory:

    uv build --wheel --out-dir deployment

This creates a wheel, for example `data_science-0.1-py3-none-any.whl` in `deployment/`.

Then:

    cd deployment  
    python3 deploy.py --create

On success, this prints a resource name like:

    projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/1234567890123456789

Use `test_deployment.py` to chat with the deployed Meeting Insights Agent:

    export RESOURCE_ID="1234567890123456789"  
    export USER_ID="demo-user"  
    python3 test_deployment.py --resource_id=$RESOURCE_ID --user_id=$USER_ID

---

## Optimizing and Extension Tips

- **Prompt Engineering**  
  Refine the prompts for:
  - Meeting Insights root agent
  - BigQuery agent
  - Analytics agent

  to match your organization’s meeting style, languages, and recurring projects.

- **Additional Tools**  
  You can add new tools or sub-agents, for example:
  - Export selected meetings to a document.
  - Integrate with task tracking systems.

- **Model Selection**  
  Try different Gemini models for:
  - Root routing.
  - NL2SQL.
  - Analytics reasoning.

---

## Troubleshooting

- If you see **SQL errors**:
  - Confirm `BQ_DATASET_ID`, `BQ_DATA_PROJECT_ID`, and `BQ_COMPUTE_PROJECT_ID`.
  - Ensure the `minutes` table schema matches the expected columns.

- If the agent tries to use AlloyDB or BQML (from older code):
  - Make sure you have removed or disabled AlloyDB and BQML sub-agents.
  - Check `data_science/agent.py` and `data_science/tools.py` to confirm that
    only `call_bigquery_agent` and `call_analytics_agent` are wired in.

- If the analytics agent fails to run code:
  - Check the `CODE_INTERPRETER_EXTENSION_NAME` logs.
  - If it was left empty, a new extension should be created automatically.