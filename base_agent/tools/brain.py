"""
Step 2 - The Brain (AI Generation)

Generates the Competency JSON contract from a parsed Job Description payload.

Design goals:
- Output matches the exact JSON contract expected by the PPTX renderer (Step 3).
- 1 main technical competency, 2–3 sub-topics, 4 proficiency levels per topic.
- Modern Standard Arabic (MSA), government HR competency tone.
- Domain/regulation-focused by default; tool/skill-focused only for purely functional support roles.
- No lookup tables; infer metadata from the job text itself.
- Strict validation via Pydantic; 1 retry on invalid outputs.

This module is meant to be called by the *agent reasoning* (not as an ADK tool).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator


DEFAULT_COMP_TYPE = "الكفاءة الفنية التخصصية"


def _clean_json_text(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    # Strip fenced blocks if present
    t = re.sub(r"^\s*```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    # Keep from first { or [ to last matching } or ]
    start_candidates = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not start_candidates:
        return t
    start = min(start_candidates)
    t = t[start:]
    end = max(t.rfind("}"), t.rfind("]"))
    if end != -1:
        t = t[: end + 1]
    return t.strip()


def _normalize_lines(value: Union[str, List[str], None]) -> str:
    """Normalize proficiency text into newline-separated items without an explicit bullet glyph.

    The PPT template is expected to apply bullet formatting itself.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        lines = [str(x).strip() for x in value if str(x).strip()]
    else:
        lines = [ln.strip() for ln in str(value).splitlines() if ln.strip()]

    cleaned: List[str] = []
    for ln in lines:
        ln = re.sub(r"^\s*[-*••]\s*", "", ln)  # remove any leading bullet
        ln = ln.replace("•", "").strip()
        if ln:
            cleaned.append(ln)
    return "\n".join(cleaned)


class ClarificationNeeded(BaseModel):
    needs_clarification: Literal[True] = True
    candidates: List[str] = Field(..., min_length=2, max_length=5)
    question: str = Field(..., min_length=6)
    reason: Optional[str] = None


class CompetencyTopic(BaseModel):
    title: str = Field(..., min_length=2)
    desc: str = Field(..., min_length=6)
    expert: str
    advanced: str
    intermediate: str
    beginner: str

    @field_validator("expert", "advanced", "intermediate", "beginner", mode="before")
    @classmethod
    def normalize_bullets(cls, v):
        return _normalize_lines(v)


class CompetencyJob(BaseModel):
    competency_name: str = Field(..., min_length=2)
    definition: str = Field(..., min_length=10)
    comp_type: str = Field(default=DEFAULT_COMP_TYPE)
    job_group: str = Field(..., min_length=2)
    department: str = Field(..., min_length=2)
    topics: List[CompetencyTopic] = Field(..., min_length=2, max_length=3)

    @field_validator("comp_type", mode="before")
    @classmethod
    def default_comp_type(cls, v):
        v = (v or "").strip()
        return v or DEFAULT_COMP_TYPE


CompetencyBrainOutput = Union[List[CompetencyJob], ClarificationNeeded]


BRAIN_PROMPT_AR = """\
أنت استشاري خبير في إعداد "أطر الكفاءات الفنية التخصصية" للجهات الحكومية (قطر).
المرجع: الدليل الإرشادي 2025 + Examples.pptx.

مهمتك: تحويل بيانات الوظيفة (JSON) إلى مصفوفة كفاءات فنية دقيقة واحترافية.

### أولاً: قواعد الهيكلة واللغة (Main Rules)

1. **العنوان الرئيسي والفرعي (Noun Phrases):**
   - يجب أن تكون العناوين "عبارات اسمية" حصراً.
   - ✅ صحيح: "إعداد التقارير المالية"، "الرقابة الهندسية".
   - ❌ خطأ: "يقوم بإعداد..."، "أن يراقب...".

2. **التعريف (Definition):**
   - استخدم الصيغة الموحدة: "القدرة على [فعل المصدر] + [موضوع العمل] + [السياق/المعيار]".
   - مثال: "القدرة على إجراء الأنشطة المحاسبية وإدارة النقد بما يتماشى مع المعايير الدولية."

3. **الاختصاص (Core Technical):**
   - ركّز على الكفاءات الفنية *الجوهرية* المرتبطة بمجال الوظيفة (هندسة، قانون، تفتيش).
   - تجنب المهارات العامة (تواصل، طباعة) إلا إذا كانت هي جوهر العمل (مثلاً لوظيفة سكرتير: "إدارة المراسلات الحكومية").

### ثانياً: معايير المستويات (Bloom's Taxonomy)

استخدم الأفعال التالية بدقة لضمان التدرج:

1. **مبتدئ (Beginner):**
   - الأفعال: يحدد، يصف، يعدد، يتبع، ينفذ (بإشراف)، يساعد في.
   - المؤشر: إلمام بالمفاهيم الأساسية، العمل ضمن توجيهات.

2. **متوسط (Intermediate):**
   - الأفعال: يشرح، يطبق (باستقلالية)، يحلل، يعد، يراجع، يعالج.
   - المؤشر: حل مشكلات اعتيادية، العمل باستقلالية، ضمان دقة البيانات.

3. **متقدم (Advanced):**
   - الأفعال: يقيم، يشخص، يصمم، يطور، يوجه، يقود (فرق عمل)، يحسن.
   - المؤشر: خبرة عميقة، التعامل مع حالات معقدة، تحسين الإجراءات.

4. **خبير (Expert):**
   - الأفعال: يبتكر، يستحدث، يرسم استراتيجيات، يضع معايير، يقود (منظومة).
   - المؤشر: مرجعية معرفية، قيادة التغيير، رؤية مستقبلية.

### ثالثاً: جودة المحتوى (Developed Bullets)
**هذه أهم خطوة:** يجب أن تكون كل نقطة (Bullet Point) "ثرية وتفصيلية" وليست مجرد كلمات مقتضبة.

### رابعاً: متطلبات التعبئة (Mapping)
- **comp_type:** استخدم القيمة الموجودة في الحقل `general_group` من المدخلات.
- **job_group:** استخدم القيمة الموجودة في الحقل `specific_group` من المدخلات.
- **department:** استخدم القيمة الموجودة في الحقل `job_location` من المدخلات.
- **الكمية:** اكتب 3-5 نقاط لكل مستوى.

### خامساً: المخرجات (JSON Contract)

أعد مصفوفة تحتوي عنصراً واحداً فقط:
[
  {
    "competency_name": "اسم الكفاءة (عبارة اسمية)",
    "definition": "القدرة على...",
    "comp_type": "...",
    "job_group": "...",
    "department": "...",
    "topics": [
      {
        "title": "الموضوع الفرعي 1 (عبارة اسمية)",
        "desc": "وصف الموضوع...",
        "expert": "• يبتكر...\\n• يضع...",
        "advanced": "• يطور...\\n• يقيم...",
        "intermediate": "• يطبق...\\n• يعد...",
        "beginner": "• يساعد في...\\n• يتبع..."
      },
      ... (موضوعان أو ثلاثة فقط)
    ]
  }
]

إذا كان الوصف غامضاً جداً، أعد:
{ "needs_clarification": true, "candidates": ["..."], "question": "...", "reason": "..." }
"""


def build_brain_prompt(job_payload: Dict[str, Any], *, chosen_competency: Optional[str] = None) -> str:
    """Build the Step-2 prompt from the extracted job payload.

    If the user has selected a main competency (after a clarification turn),
    we explicitly steer the model to use it.
    """
    job_json = json.dumps(job_payload, ensure_ascii=False, indent=2)

    steer = ""
    if chosen_competency:
        steer = (
            "\n\nملاحظة: المستخدم اختار الكفاءة التالية، التزم بها:\n"
            f"{chosen_competency}\n"
        )

    return (
        BRAIN_PROMPT_AR.replace("{DEFAULT_COMP_TYPE}", DEFAULT_COMP_TYPE)
        + steer
        + "\n\nبيانات الوظيفة المستخرجة (JSON):\n"
        + job_json
        + "\n\nتذكير: التزم بأفعال Bloom's Taxonomy لكل مستوى."
    )


def _load_rulebook_bytes_from_path(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _call_gemini_generate(
    *,
    prompt: str,
    model_name: str,
    project: str,
    location: str,
    rulebook_pdf_bytes: Optional[bytes] = None,
    temperature: float = 0.15,
) -> str:
    """
    Low-level Gemini call (Vertex via google-genai).
    Returns raw text (expected to be JSON).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(api_version="v1"),
    )

    contents: List[Any] = []
    if rulebook_pdf_bytes:
        contents.append(types.Part.from_bytes(data=rulebook_pdf_bytes, mime_type="application/pdf"))
        contents.append("مرجع إضافي: الدليل الإرشادي للكفاءات (للاستئناس بالتعريفات فقط).")

    contents.append(prompt)

    resp = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=temperature,
            top_p=0.8,
        ),
    )
    return getattr(resp, "text", "") or ""


def _parse_brain_output(raw_text: str) -> CompetencyBrainOutput:
    cleaned = _clean_json_text(raw_text)
    data = json.loads(cleaned)

    # Clarification mode
    if isinstance(data, dict) and data.get("needs_clarification") is True:
        return ClarificationNeeded.model_validate(data)

    # Normal mode: list with one CompetencyJob
    if not isinstance(data, list):
        raise ValueError("Brain output must be a JSON array (normal mode) or clarification object.")
    jobs = [CompetencyJob.model_validate(item) for item in data]
    if len(jobs) != 1:
        # Enforce "one job per run"
        jobs = jobs[:1]
    return jobs


def generate_competency_json(
    job_payload: Dict[str, Any],
    *,
    model_name: str = "gemini-2.5-pro",
    rulebook_pdf_path: Optional[str] = None,
    rulebook_pdf_bytes: Optional[bytes] = None,
    temperature: float = 0.15,
    retry: int = 1,
    chosen_competency: Optional[str] = None,
) -> CompetencyBrainOutput:
    """
    Step 2 entrypoint.

    Inputs:
      job_payload: output from Step 1 for the selected job (dict).
      rulebook_pdf_path/rulebook_pdf_bytes: optional context document.
      retry: number of *additional* attempts after a validation failure (default 1).

    Returns:
      - List[CompetencyJob] (length 1) OR
      - ClarificationNeeded (if the model cannot identify a main technical competency).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or ""
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_LOCATION") or "global"

    if rulebook_pdf_bytes is None and rulebook_pdf_path:
        rulebook_pdf_bytes = _load_rulebook_bytes_from_path(rulebook_pdf_path)

    prompt = build_brain_prompt(job_payload, chosen_competency=chosen_competency)

    if not project:
        # Local/dev fallback (no model call): return clarification object to avoid broken files.
        return ClarificationNeeded(
            candidates=[
                "تنظيم/تشريعات المجال الوظيفي",
                "إدارة الامتثال والحوكمة",
                "تحليل البيانات (عند اللزوم)"
            ],
            question="لم يتم تهيئة GOOGLE_CLOUD_PROJECT. اختر الكفاءة الأنسب للوظيفة:",
            reason="تعذر استدعاء Gemini محليًا بدون إعدادات مشروع Vertex AI.",
        )

    last_err: Optional[str] = None
    attempts = 1 + max(0, int(retry))

    for _ in range(attempts):
        raw = _call_gemini_generate(
            prompt=prompt,
            model_name=model_name,
            project=project,
            location=location,
            rulebook_pdf_bytes=rulebook_pdf_bytes,
            temperature=temperature,
        )
        try:
            out = _parse_brain_output(raw)

            # Force header fields to match JD template fields when available
            # Header_CompType   <- general_group
            # Header_JobGroup   <- specific_group
            # Header_Department <- job_location
            if isinstance(out, list) and out:
                gg = (job_payload.get("general_group") or job_payload.get("المجموعة العامة") or "").strip()
                sg = (job_payload.get("specific_group") or job_payload.get("المجموعة النوعية") or "").strip()
                jl = (job_payload.get("job_location") or job_payload.get("تقع هذه الوظيفة") or "").strip()

                job0 = out[0]
                updates = {}
                if gg:
                    updates["comp_type"] = gg
                if sg:
                    updates["job_group"] = sg
                if jl:
                    updates["department"] = jl

                if updates:
                    # pydantic v2
                    if hasattr(job0, "model_copy"):
                        out[0] = job0.model_copy(update=updates)
                    else:
                        for k, v in updates.items():
                            setattr(job0, k, v)

            return out
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = str(e)

    raise RuntimeError(f"Brain step failed after {attempts} attempts. Last error: {last_err}")