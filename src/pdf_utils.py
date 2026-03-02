from __future__ import annotations
import io
from typing import List, Dict, Any
import streamlit as st
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
