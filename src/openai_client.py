from __future__ import annotations
import base64, json, os
from typing import List, Dict, Tuple, Any
from openai import OpenAI

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("utf-8")

def _call_vision_json(model: str, images_png: List[bytes], instruction: str, schema_hint: str) -> Any:
    input_content = [{"type": "input_text", "text": instruction + "\n\nReturn ONLY valid JSON.\n" + schema_hint}]
    for img in images_png:
        input_content.append({"type": "input_image", "image_url": f"data:image/png;base64,{_b64_png(img)}"})
    resp = client.responses.create(model=model, input=[{"role": "user", "content": input_content}], temperature=0.1)
    text_parts = []
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    text_parts.append(c.text)
    raw = "\n".join(text_parts).strip()
    if raw.startswith("```"):
        raw = raw.strip("`").replace("json", "", 1).strip()
    return json.loads(raw)

def extract_step1_builder_selections(images_png: List[bytes], model: str = DEFAULT_MODEL) -> List[Dict[str, str]]:
    instruction = (
        "Extract flooring scope from a builder Selection Sheet.\n\n"
        "Rules:\n"
        "- Trades must be one of: Carpet, LVP, Tile.\n"
        "- Room may be a specific room name or an area category like Bedrooms, Living Areas, Wet Areas.\n"
        "- Material Description must include brand/style/color exactly as shown.\n"
        "- Ignore non-flooring items.\n"
    )
    schema_hint = '{ "rows": [{"Room":"string","Trade":"Carpet|LVP|Tile","Material Description":"string"}] }'
    data = _call_vision_json(model, images_png, instruction, schema_hint)
    return [{"Room": str(r.get("Room","")).strip(), "Trade": str(r.get("Trade","")).strip(), "Material Description": str(r.get("Material Description","")).strip()} for r in data.get("rows", [])]

def extract_step2_rooms_transitions(images_png: List[bytes], model: str = DEFAULT_MODEL) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    instruction = (
        "Extract room names and adjacency pairs from a residential floorplan.\n"
        "Return conservative adjacency pairs only where a doorway/opening is visible.\n"
        "Set Transition needed to Yes/No/Describe.\n"
    )
    schema_hint = '{ "rooms":[{"Room":"string"}], "transitions":[{"Room":"string","Adjoining Room":"string","Transition needed":"string"}] }'
    data = _call_vision_json(model, images_png, instruction, schema_hint)
    rooms = [{"Room": str(r.get("Room","")).strip()} for r in data.get("rooms", []) if str(r.get("Room","")).strip()]
    trans = [{"Room": str(t.get("Room","")).strip(), "Adjoining Room": str(t.get("Adjoining Room","")).strip(), "Transition needed": str(t.get("Transition needed","")).strip()} for t in data.get("transitions", [])]
    return rooms, trans
