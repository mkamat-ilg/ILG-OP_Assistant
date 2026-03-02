from __future__ import annotations
import base64
import json
import os
from typing import List, Dict, Tuple, Any

from openai import OpenAI

# ---------
# Model
# ---------
# You asked for "OpenAI LLM 5.2". Use the GPT‑5.2 model name you have enabled in your account.
# If your org has a specific deployment/model alias, set it via env var OPENAI_MODEL.
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("utf-8")


def _call_vision_json(model: str, images_png: List[bytes], instruction: str, schema_hint: str) -> Any:
    """
    Calls the Responses API with image inputs and returns parsed JSON.
    The prompt is designed to enforce JSON-only output.
    """
    input_content = [{"type": "input_text", "text": instruction + "\n\nReturn ONLY valid JSON.\n" + schema_hint}]
    for img in images_png:
        input_content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{_b64_png(img)}",
        })

    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": input_content}],
        temperature=0.1,
    )

    # Responses API returns output text segments; safest is to join all "output_text"
    text_parts = []
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text_parts.append(c.text)
    raw = "\n".join(text_parts).strip()

    # Strip accidental markdown fences if any
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    return json.loads(raw)


# ------------------------
# Step 1 extractor
# ------------------------
def extract_step1_builder_selections(images_png: List[bytes], model: str = DEFAULT_MODEL) -> List[Dict[str, str]]:
    """
    Output rows:
      Room | Trade | Material Description
    Note: 'Room' may be an area label (e.g., 'Bedrooms') depending on selection sheet wording.
    Trades are expected to be separate: Carpet / LVP / Tile.
    """
    instruction = (
        "You are extracting flooring scope from a builder Selection Sheet. "
        "Identify all flooring-related selections and express them as rows.\n\n"
        "Rules:\n"
        "- Trades must be one of: 'Carpet', 'LVP', 'Tile'.\n"
        "- Room can be a specific room name if stated, or an area category like 'Bedrooms', 'Living Areas', 'Wet Areas'.\n"
        "- Material Description must include brand/style/color text exactly as shown.\n"
        "- Do NOT include appliances, paint, plumbing, etc.\n"
        "- If multiple tile items exist (e.g., wall tile Bath 1, Bath 2), include them as separate rows under Trade='Tile'.\n"
    )

    schema_hint = (
        "JSON schema:\n"
        "{\n"
        '  "rows": [\n'
        '    {"Room": "string", "Trade": "Carpet|LVP|Tile", "Material Description": "string"}\n'
        "  ]\n"
        "}\n"
    )

    data = _call_vision_json(model, images_png, instruction, schema_hint)
    rows = data.get("rows", [])
    # normalize keys
    out = []
    for r in rows:
        out.append({
            "Room": str(r.get("Room", "")).strip(),
            "Trade": str(r.get("Trade", "")).strip(),
            "Material Description": str(r.get("Material Description", "")).strip(),
        })
    return out


# ------------------------
# Step 2 extractor
# ------------------------
def extract_step2_rooms_transitions(images_png: List[bytes], model: str = DEFAULT_MODEL) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Output:
      rooms: [{"Room": "..."}]
      transitions: [{"Room": "...", "Adjoining Room": "...", "Transition needed": "Yes|No|Describe"}]
    """
    instruction = (
        "You are extracting room names and adjacency/transition needs from a residential floorplan.\n\n"
        "Tasks:\n"
        "1) List every room/space label visible (e.g., BR 1, Bath 2, Loft, Laundry, Great Room / Kit / Foyer, WIC, HVAC, Pantry, Garage).\n"
        "2) Create adjacency pairs for rooms that directly connect (share a doorway/opening). Use the drawing to infer adjacency.\n"
        "3) For each adjacency, set 'Transition needed' as:\n"
        "   - 'Yes' if the adjacent spaces are likely to have different flooring types,\n"
        "   - 'No' if likely the same,\n"
        "   - or a short description if uncertain.\n\n"
        "Be conservative: include fewer adjacency pairs rather than guessing wildly.\n"
        "Return JSON only."
    )

    schema_hint = (
        "JSON schema:\n"
        "{\n"
        '  "rooms": [{"Room":"string"}],\n'
        '  "transitions": [{"Room":"string","Adjoining Room":"string","Transition needed":"string"}]\n'
        "}\n"
    )

    data = _call_vision_json(model, images_png, instruction, schema_hint)
    rooms = data.get("rooms", [])
    transitions = data.get("transitions", [])

    rooms_out = [{"Room": str(r.get("Room", "")).strip()} for r in rooms if str(r.get("Room", "")).strip()]
    trans_out = []
    for t in transitions:
        trans_out.append({
            "Room": str(t.get("Room", "")).strip(),
            "Adjoining Room": str(t.get("Adjoining Room", "")).strip(),
            "Transition needed": str(t.get("Transition needed", "")).strip(),
        })
    return rooms_out, trans_out
