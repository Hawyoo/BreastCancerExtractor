import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from ocr.service import get_engine

    engine = get_engine()
    print(f"PaddleOCR ready: {type(engine).__name__}")
