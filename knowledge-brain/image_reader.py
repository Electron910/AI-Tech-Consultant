"""
task1-knowledge-brain/image_reader.py
-------------------------------------
Why this file exists:
Help center articles often hide the real answer inside a screenshot (for example,
which menu tab to click or what a setting is named). This file uses Gemini Vision
to turn screenshots into searchable text linked to the parent article.
"""

import os
import httpx
from google import genai
from google.genai import types
from prompts import ScreenshotDescriptionSchema, VISION_PROMPT_V1

def describe_screenshot(
    image_url: str,
    article_title: str,
    section_heading: str,
    nearby_text: str,
    alt_text: str = "",
    model_name: str = "gemini-2.5-flash",
) -> dict:
    """
    Downloads a screenshot (if accessible) and asks Gemini Vision what settings,
    buttons, and steps are visible inside it.
    Falls back cleanly to alt_text + nearby_text if offline or no API key is set.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key or api_key == "your_gemini_api_key_here":
        return {
            "image_url": image_url,
            "summary": f"Screenshot in '{section_heading}' ({alt_text or 'UI setting view'})",
            "visible_labels_and_buttons": [alt_text] if alt_text else [],
            "steps_shown": [],
            "is_unclear": False,
            "mode": "fallback_metadata",
        }

    try:
        headers = {"User-Agent": "AITechConsultant-KnowledgeBot/1.0 (Educational Capstone)"}
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as http_client:
            resp = http_client.get(image_url)
            resp.raise_for_status()
            image_bytes = resp.content
            mime_type = resp.headers.get("content-type", "image/png").split(";")[0]

        client = genai.Client(api_key=api_key)
        prompt_text = VISION_PROMPT_V1.format(
            article_title=article_title,
            section_heading=section_heading,
            nearby_text=nearby_text[:600],
        )

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt_text,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ScreenshotDescriptionSchema,
                temperature=0.1,
            ),
        )

        parsed = ScreenshotDescriptionSchema.model_validate_json(response.text)
        return {
            "image_url": image_url,
            "summary": parsed.summary,
            "visible_labels_and_buttons": parsed.visible_labels_and_buttons,
            "steps_shown": parsed.steps_shown,
            "is_unclear": parsed.is_unclear,
            "mode": "gemini_vision",
        }

    except Exception as exc:
        return {
            "image_url": image_url,
            "summary": f"Image could not be fully read ({alt_text or 'screenshot'}): {str(exc)[:100]}",
            "visible_labels_and_buttons": [alt_text] if alt_text else [],
            "steps_shown": [],
            "is_unclear": True,
            "mode": "error_fallback",
        }

def format_image_for_search(img_info: dict) -> str:
    """Formats the extracted screenshot details into plain text so search can find it."""
    labels = ", ".join(img_info.get("visible_labels_and_buttons", []))
    steps = " -> ".join(img_info.get("steps_shown", []))
    unclear_note = " (Note: Screenshot resolution is unclear)" if img_info.get("is_unclear") else ""
    parts = [f"[SCREENSHOT DETAILS ({img_info.get('image_url', '')}){unclear_note}: {img_info.get('summary', '')}"]
    if labels:
        parts.append(f"Visible UI Labels/Buttons: {labels}.")
    if steps:
        parts.append(f"UI Steps Shown: {steps}.")
    parts.append("]")
    return " ".join(parts)
