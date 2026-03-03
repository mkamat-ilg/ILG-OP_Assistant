from __future__ import annotations
import io
import base64
from typing import List, Dict, Any
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import fitz  # pymupdf

def pdf_bytes_to_images(pdf_bytes: bytes, max_pages: int = 12, dpi: int = 150) -> List[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: List[bytes] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for i in range(min(doc.page_count, max_pages)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        images.append(pix.tobytes("png"))
    return images

def image_bytes_to_images(img_bytes: bytes) -> List[bytes]:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return [out.getvalue()]

def render_doc_viewer(file_obj: Dict[str, Any], key_prefix: str):
    ext = file_obj.get("ext", "").lower()
    b = file_obj["bytes"]
    zoom = st.slider("Zoom", 50, 200, 110, 5, key=f"{key_prefix}_zoom")
    max_pages = st.number_input("Max pages to render", 1, 30, 10, 1, key=f"{key_prefix}_pages") if ext == "pdf" else 1
    if ext == "pdf":
        imgs = pdf_bytes_to_images(b, max_pages=int(max_pages), dpi=int(72 * (zoom / 100.0) * 2))
        for idx, img in enumerate(imgs, start=1):
            st.image(img, caption=f"Page {idx}", use_container_width=True)
    else:
        imgs = image_bytes_to_images(b)
        st.image(imgs[0], use_container_width=True)


def render_doc_viewer_container(file_obj: Dict[str, Any], key_prefix: str, height_px: int = 700):
    """Render the document inside a fixed-height, scrollable container.

    This keeps adjacent UI (e.g., editable tables) visible while the user scrolls/zooms the document.
    """
    ext = file_obj.get("ext", "").lower()
    b = file_obj["bytes"]

    zoom = st.slider("Zoom", 50, 200, 110, 5, key=f"{key_prefix}_zoom")
    max_pages = st.number_input("Max pages to render", 1, 30, 10, 1, key=f"{key_prefix}_pages") if ext == "pdf" else 1

    if ext == "pdf":
        imgs = pdf_bytes_to_images(b, max_pages=int(max_pages), dpi=int(72 * (zoom / 100.0) * 2))
    else:
        imgs = image_bytes_to_images(b)

    blocks = []
    for i, img in enumerate(imgs, start=1):
        b64 = base64.b64encode(img).decode("utf-8")
        caption = f"Page {i}" if ext == "pdf" else ""
        blocks.append(
            f"""
            <div style='margin-bottom: 12px;'>
              <img src='data:image/png;base64,{b64}' style='width: 100%; height: auto; border: 1px solid rgba(49,51,63,0.15); border-radius: 6px;' />
              {f"<div style='font-size: 12px; color: rgba(49,51,63,0.6); margin-top: 4px;'>{caption}</div>" if caption else ""}
            </div>
            """
        )

    html = f"""
    <div style='height: {int(height_px)}px; overflow-y: auto; padding-right: 6px;'>
      {''.join(blocks)}
    </div>
    """
    components.html(html, height=int(height_px) + 20, scrolling=False)
