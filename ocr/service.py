import json
import threading
from importlib.metadata import version
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from paddleocr import PaddleOCR

app = FastAPI(title="Breast Cancer Extractor OCR")
_engine: PaddleOCR | None = None
_lock = threading.Lock()


def get_engine() -> PaddleOCR:
    global _engine
    if _engine is None:
        _engine = PaddleOCR(
            lang="ch",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            engine="paddle",
        )
    return _engine


def result_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        payload = payload["res"]
    return payload if isinstance(payload, dict) else {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "PaddleOCR", "version": version("paddleocr")}


@app.post("/ocr")
async def ocr(image: UploadFile = File(...)) -> dict[str, Any]:
    if image.content_type != "image/png":
        raise HTTPException(status_code=415, detail="OCR accepts sanitized PNG images only")
    try:
        source = Image.open(image.file).convert("RGB")
        source.load()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid image") from exc

    with _lock:
        results = get_engine().predict(np.asarray(source))
    lines: list[dict[str, Any]] = []
    for result in results:
        payload = result_payload(result)
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes", [])
        for index, text in enumerate(texts):
            lines.append({
                "text": text,
                "score": float(scores[index]) if index < len(scores) else None,
                "box": boxes[index].tolist() if index < len(boxes) and hasattr(boxes[index], "tolist")
                else (boxes[index] if index < len(boxes) else None),
            })
    return {
        "engine": "PaddleOCR",
        "version": version("paddleocr"),
        "full_text": "\n".join(line["text"] for line in lines),
        "lines": lines,
    }
