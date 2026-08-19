import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from ocr.service import get_engine

    engine = get_engine()
    image = Image.new("RGB", (480, 120), "white")
    ImageDraw.Draw(image).text((24, 40), "HER2 2+  Ki-67 30%", fill="black")
    results = list(engine.predict(np.asarray(image)))
    print(f"PaddleOCR inference warm-up passed: {len(results)} result(s)")
