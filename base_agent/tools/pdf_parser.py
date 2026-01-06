
"""
PDF Parser Tool (Step 1)

- Detects multiple job cards inside an Arabic Job Description PDF.
- Each job card starts with the title "بطاقة الوصف الوظيفي" (after Unicode normalization).
- When a specific job is selected, extracts *all* JD fields into structured JSON
  using Gemini 2.5 Pro (text-first; optional vision-OCR fallback).

Designed to be used as an ADK Function Tool:
- Add `tool_context: ToolContext` as the last argument; ADK injects it.
- Works whether the PDF is passed as an artifact filename or attached to the current user message.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import inspect
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from ..config import PARSER_MODEL

# -----------------------------
# Data models (lightweight)
# -----------------------------

JD_HEADER = "بطاقة الوصف الوظيفي"

# Fields from the JD template (Arabic labels), mapped to stable JSON keys.
FIELD_MAP = {
    "مسمى الوظيفة": "job_title",
    "كود الوظيفة": "job_code",
    "الدرجة المالية": "financial_grade",
    "المجموعة العامة": "general_group",
    "المجموعة النوعية": "specific_group",
    "تختص هذه الوظيفة": "job_purpose",
    "تقع هذه الوظيفة": "job_location",
    "واجبات ومسؤوليات الوظيفة": "duties",
    "المؤهل": "qualification",
    "الخبرة العملية": "experience",
}

JOB_CODE_RE = re.compile(r"\b([A-Za-z0-9]{4})\b")


@dataclasses.dataclass
class JobSegment:
    index: int
    page_start: int  # 0-based
    page_end: int    # 0-based inclusive
    title: str


# -----------------------------
# Helpers (robustness)
# -----------------------------

def _nfkc(text: str) -> str:
    """Normalize Arabic presentation forms and spacing."""
    return unicodedata.normalize("NFKC", text or "")


def _clean_json_text(text: str) -> str:
    """
    Attempts to isolate a JSON object/array from an LLM response.
    Handles code fences and leading/trailing commentary.
    """
    if not text:
        return text
    t = text.strip()

    # Remove fenced blocks if present
    t = re.sub(r"^\s*```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)

    # Find first '{' or '[' and last matching '}' or ']'
    start_candidates = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not start_candidates:
        return t
    start = min(start_candidates)
    t2 = t[start:]

    # Heuristic: trim to last '}' or ']'
    last_obj = t2.rfind("}")
    last_arr = t2.rfind("]")
    end = max(last_obj, last_arr)
    if end != -1:
        t2 = t2[: end + 1]
    return t2.strip()


def _safe_json_loads(text: str) -> Any:
    """
    JSON loads with helpful error message.
    """
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from model output. Error={e}. Cleaned head={cleaned[:200]!r}")


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


def _extract_page_texts(pdf_bytes: bytes) -> List[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts: List[str] = []
    for i in range(doc.page_count):
        t = doc.load_page(i).get_text("text")
        texts.append(_nfkc(t))
    return texts


def _detect_job_segments(page_texts: List[str]) -> List[JobSegment]:
    """
    Uses occurrences of JD_HEADER in extracted page texts as segment boundaries.
    A job starts at each page containing the header; it runs until the page before the next header.
    """
    starts = [i for i, t in enumerate(page_texts) if JD_HEADER in t]
    if not starts:
        return []

    segments: List[Tuple[int, int]] = []
    for idx, s in enumerate(starts):
        e = (starts[idx + 1] - 1) if idx + 1 < len(starts) else (len(page_texts) - 1)
        segments.append((s, e))

    job_segments: List[JobSegment] = []
    for j, (s, e) in enumerate(segments):
        lines = [ln.strip() for ln in page_texts[s].splitlines() if ln.strip()]
        title = "غير محدد"
        try:
            k = lines.index(JD_HEADER)
            if k + 1 < len(lines):
                title = lines[k + 1].strip()
        except ValueError:
            # header not line-separated; fall back to regex
            m = re.search(rf"{re.escape(JD_HEADER)}\s*\n\s*(.+)", page_texts[s])
            if m:
                title = m.group(1).strip()

        job_segments.append(JobSegment(index=j, page_start=s, page_end=e, title=title))
    return job_segments


def _make_subpdf(pdf_bytes: bytes, page_start: int, page_end: int) -> bytes:
    """Create a new PDF byte-string that includes only [page_start..page_end]."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    out.insert_pdf(src, from_page=page_start, to_page=page_end)
    return out.tobytes()


def _render_pages_to_png(pdf_bytes: bytes, page_start: int, page_end: int, zoom: float = 2.0) -> List[bytes]:
    """Render pages to PNG bytes for OCR-vision fallback."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    imgs: List[bytes] = []
    mat = fitz.Matrix(zoom, zoom)
    for i in range(page_start, page_end + 1):
        pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
        imgs.append(pix.tobytes("png"))
    return imgs


def _looks_scanned(page_texts: List[str], page_start: int, page_end: int) -> bool:
    """
    Heuristic: if very few Arabic letters extracted across the segment, likely scanned.
    """
    seg = "\n".join(page_texts[page_start:page_end + 1]).strip()
    # Arabic unicode block
    arabic_chars = re.findall(r"[\u0600-\u06FF]", seg)
    return len(arabic_chars) < 200  # tunable


# -----------------------------
# Gemini extraction
# -----------------------------

_EXTRACT_PROMPT_AR = """\
أنت نظام لاستخراج بيانات "بطاقة الوصف الوظيفي" الحكومية (عربي).
المطلوب: استخراج الحقول التالية بدقة قدر الإمكان من نص/وثيقة البطاقة:

- مسمى الوظيفة
- كود الوظيفة (رمز مكوّن من 4 خانات حرف/رقم)
- الدرجة المالية
- المجموعة العامة
- المجموعة النوعية
- تختص هذه الوظيفة (النص الكامل)
- تقع هذه الوظيفة (النص الكامل)
- واجبات ومسؤوليات الوظيفة (قائمة بنقاط)
- اشتراطات شغل الوظيفة: المؤهل، الخبرة العملية

قواعد الإخراج:
1) أعد JSON فقط بدون Markdown وبدون أي شرح.
2) استخدم المفاتيح التالية بالإنجليزية (snake_case) EXACTLY:
   job_title, job_code, financial_grade, general_group, specific_group,
   job_purpose, job_location, duties, qualification, experience,
   additional_fields
3) duties: مصفوفة من السلاسل (كل واجب كسطر منفصل).
4) إذا تعذر العثور على قيمة، ضع null.
5) لا تخمّن حقائق غير موجودة في المستند.

الآن استخرج البيانات من المستند/النص المرفق.
"""


async def _call_gemini_extract(
    *,
    pdf_part: Optional[bytes],
    text_hint: Optional[str],
    images_png: Optional[List[bytes]],
    model_name: str,
    project: str,
    location: str,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """
    Calls Gemini via the Google Gen AI SDK (Vertex AI endpoint).
    Uses PDF bytes if available; otherwise can use rendered PNG pages.
    """
    # Import lazily so the module can be imported without the SDK during local non-LLM tests.
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(api_version="v1"),
    )

    contents: List[Any] = []
    if pdf_part is not None:
        contents.append(types.Part.from_bytes(data=pdf_part, mime_type="application/pdf"))
    if images_png:
        for img in images_png:
            contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))
    if text_hint:
        # Keep it after the media parts, before prompt.
        contents.append(f"نص مستخرج (للمساعدة فقط):\n{text_hint}")

    contents.append(_EXTRACT_PROMPT_AR)

    resp = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=temperature,
            # Ask model to be deterministic for extraction.
            top_p=0.1,
        ),
    )
    # google-genai response: resp.text
    raw = getattr(resp, "text", None)
    if not raw and hasattr(resp, "candidates") and resp.candidates:
        # defensive
        try:
            raw = resp.candidates[0].content.parts[0].text
        except Exception:
            raw = None
    if not raw:
        raise RuntimeError("Gemini returned empty response.")
    data = _safe_json_loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object for a single job extraction.")
    return data


def _validate_job_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce the contract and normalize common issues.
    """
    out: Dict[str, Any] = {}
    # Ensure required keys exist
    required = [
        "job_title", "job_code", "financial_grade", "general_group", "specific_group",
        "job_purpose", "job_location", "duties", "qualification", "experience", "additional_fields"
    ]
    for k in required:
        out[k] = payload.get(k, None)

    # Normalize duties -> list[str] or None
    duties = out["duties"]
    if duties is None:
        pass
    elif isinstance(duties, str):
        # split on newlines / bullets
        parts = [re.sub(r"^\s*[•\-\*\u2022]\s*", "", ln).strip() for ln in duties.splitlines()]
        parts = [p for p in parts if p]
        out["duties"] = parts
    elif isinstance(duties, list):
        out["duties"] = [str(x).strip() for x in duties if str(x).strip()]
    else:
        out["duties"] = None

    # Normalize job_code to 4 alnum if present
    jc = out["job_code"]
    if isinstance(jc, str):
        m = JOB_CODE_RE.search(jc.strip())
        out["job_code"] = m.group(1) if m else jc.strip()[:8]  # keep some value instead of dropping
    else:
        out["job_code"] = None

    # additional_fields: dict
    af = out.get("additional_fields")
    if af is None:
        out["additional_fields"] = {}
    elif not isinstance(af, dict):
        out["additional_fields"] = {"_raw": str(af)}

    return out


# -----------------------------
# Public Tool Function
# -----------------------------

import base64

async def parse_jd_pdf(
    selected_job_index: Optional[int] = None,
    pdf_artifact_filename: Optional[str] = None,
    artifact_filename: Optional[str] = None,
    model_name: str = "gemini-2.5-pro",
    tool_context=None,
) -> Dict[str, Any]:
    """
    [Step 1] Extracts structured Job Description data from an Arabic PDF.

    This tool reads a "Job Description Card" (بطاقة الوصف الوظيفي) and converts it
    into a clean JSON format required for competency modeling. It handles text extraction
    and includes an OCR fallback for scanned documents.

    Args:
        selected_job_index: If the PDF contains multiple jobs, specify the index (0-based) to extract.
        pdf_artifact_filename: The name of the PDF file uploaded by the user.
        model_name: The Gemini model version to use for extraction.
        tool_context: ADK context (injected automatically).

    Returns:
        A dictionary containing the parsed fields (job_title, duties, financial_grade, etc.).
        If multiple jobs are found and no index is provided, returns a list of jobs.
    """
    if tool_context is None:
        raise ValueError("tool_context is required (ADK injects it).")

    # Helper to extracting bytes from either Object (Local) or Dict (AgentSpace)
    def _extract_bytes(part_obj: Any) -> Optional[bytes]:
        if part_obj is None:
            return None
        # 1. AgentSpace / Gemini Enterprise (Dictionary with base64 string)
        if isinstance(part_obj, dict) and "inlineData" in part_obj:
            try:
                b64_data = part_obj["inlineData"].get("data")
                if b64_data:
                    return base64.b64decode(b64_data)
            except Exception:
                pass
        # 2. Local ADK (Object with inline_data)
        if getattr(part_obj, "inline_data", None):
            return part_obj.inline_data.data
        # 3. Direct data attribute
        if hasattr(part_obj, "data"):
            return part_obj.data
        # 4. Raw bytes
        if isinstance(part_obj, (bytes, bytearray)):
            return bytes(part_obj)
        return None

    # 1) Get PDF bytes
    pdf_part = None

    # a) Explicit artifact filename
    _artifact_name = pdf_artifact_filename or artifact_filename
    if _artifact_name:
        # Handle load_artifact signature safely
        load_fn = getattr(tool_context, "load_artifact")
        if "filename" in inspect.signature(load_fn).parameters:
            loaded = await _maybe_await(load_fn(filename=_artifact_name))
        else:
            loaded = await _maybe_await(load_fn(_artifact_name))
        
        pdf_part = _extract_bytes(loaded)

    # b) From the user's current multimodal message parts
    if pdf_part is None:
        user_content = None
        for attr in ("user_content", "userContent", "user_content_async"):
            if hasattr(tool_context, attr):
                user_content = getattr(tool_context, attr)
                user_content = user_content() if callable(user_content) else user_content
                break
        parts = None
        if user_content is not None:
            parts = getattr(user_content, "parts", None)
            parts = parts() if callable(parts) else parts
        
        if parts:
            for p in parts:
                # Check mime type in Dict (AgentSpace) or Object (Local)
                mime = ""
                if isinstance(p, dict) and "inlineData" in p:
                    mime = p["inlineData"].get("mimeType", "")
                elif getattr(p, "inline_data", None):
                    mime = getattr(p.inline_data, "mime_type", "")
                
                if mime == "application/pdf":
                    pdf_part = _extract_bytes(p)
                    if pdf_part:
                        break

    if pdf_part is None:
        # c) As a last resort, list saved artifacts and load the first PDF we find.
        try:
            list_fn = getattr(tool_context, "list_artifacts", None)
            if list_fn:
                names = await _maybe_await(list_fn())
                if names:
                    pdf_names = [n for n in names if str(n).lower().endswith(".pdf")]
                    if pdf_names:
                        load_fn = getattr(tool_context, "load_artifact")
                        if "filename" in inspect.signature(load_fn).parameters:
                            loaded = await _maybe_await(load_fn(filename=pdf_names[0]))
                        else:
                            loaded = await _maybe_await(load_fn(pdf_names[0]))
                        pdf_part = _extract_bytes(loaded)
        except Exception:
            pass

    if pdf_part is None:
        raise FileNotFoundError(
            "لم أتمكن من العثور على ملف PDF في الرسالة الحالية أو ضمن Artifacts. "
            "رجاءً ارفع ملف PDF (بطاقة الوصف الوظيفي) أو مرّر اسم الـartifact."
        )

    # 2) Extract text per page and detect segments
    page_texts = _extract_page_texts(pdf_part)
    segments = _detect_job_segments(page_texts)
    if not segments:
        raise ValueError("لم يتم العثور على أي 'بطاقة الوصف الوظيفي' داخل المستند.")

    # Cache segments for later selection
    try:
        tool_context.state["jd:segments"] = [dataclasses.asdict(s) for s in segments]
    except Exception:
        pass

    # 3) If no selection, return job list
    if selected_job_index is None:
        return {
            "job_count": len(segments),
            "jobs": [dataclasses.asdict(s) for s in segments],
            "note": "اختر رقم الوظيفة (index) لاستخراج التفاصيل الكاملة."
        }

    # 4) Selection: bounds check
    if selected_job_index < 0 or selected_job_index >= len(segments):
        raise IndexError(f"selected_job_index out of range. Must be 0..{len(segments)-1}")

    seg = segments[selected_job_index]
    subpdf = _make_subpdf(pdf_part, seg.page_start, seg.page_end)
    text_hint = "\n".join(page_texts[seg.page_start: seg.page_end + 1])

    # 5) Gemini extraction
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or ""
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_LOCATION") or "global"
    if not project:
        # Allow local-dev without credentials: return only the text hint for now.
        return {
            "segment": dataclasses.asdict(seg),
            "job": {
                "job_title": seg.title,
                "job_code": None,
                "financial_grade": None,
                "general_group": None,
                "specific_group": None,
                "job_purpose": None,
                "job_location": None,
                "duties": None,
                "qualification": None,
                "experience": None,
                "additional_fields": {"_warning": "GOOGLE_CLOUD_PROJECT not set; Gemini call skipped."},
            },
            "debug": {"text_hint_chars": len(text_hint)},
        }

    if PARSER_MODEL:
        model_name = PARSER_MODEL

    last_err: Optional[str] = None
    for attempt in range(2):  # 1 retry
        try:
            payload = await _call_gemini_extract(
                pdf_part=subpdf,
                text_hint=text_hint,
                images_png=None,
                model_name=model_name,
                project=project,
                location=location,
            )
            job = _validate_job_payload(payload)
            job["_extraction"] = {"method": "pdf", "attempt": attempt + 1}
            return {"segment": dataclasses.asdict(seg), "job": job}
        except Exception as e:
            last_err = str(e)

    # Vision OCR fallback
    try:
        imgs = _render_pages_to_png(pdf_part, seg.page_start, seg.page_end)
        payload = await _call_gemini_extract(
            pdf_part=None,
            text_hint=None,
            images_png=imgs,
            model_name=model_name,
            project=project,
            location=location,
        )
        job = _validate_job_payload(payload)
        job["_extraction"] = {"method": "vision_png", "attempt": 3}
        return {"segment": dataclasses.asdict(seg), "job": job, "warning": f"PDF parse failed twice: {last_err}"}
    except Exception as e:
        raise RuntimeError(f"فشل الاستخراج من PDF حتى بعد OCR. آخر خطأ (PDF): {last_err}. خطأ OCR: {e}")


# -----------------------------
# Local debugging helper (no ADK)
# -----------------------------

def debug_list_segments_from_file(pdf_path: str) -> List[Dict[str, Any]]:
    """Quick local helper (no Gemini): returns detected job segments."""
    pdf_bytes = open(pdf_path, "rb").read()
    texts = _extract_page_texts(pdf_bytes)
    segs = _detect_job_segments(texts)
    return [dataclasses.asdict(s) for s in segs]
