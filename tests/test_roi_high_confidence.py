import io

from PIL import Image

from app.ocr import _compose_ai_ocr_text, _crop_region_png


def test_roi_context_is_explicitly_high_confidence_but_not_verified():
    text = _compose_ai_ocr_text(
        "整页OCR正文",
        [
            {
                "region_type": "primary_ihc",
                "label": "原发灶ER/PR/HER2/Ki-67及其他IHC",
                "full_text": "ER 90%\nPR 80%\nHER2 2+",
            }
        ],
    )

    assert "【人工标注高信度ROI】" in text
    assert "类型：primary_ihc" in text
    assert "标签：原发灶ER/PR/HER2/Ki-67及其他IHC" in text
    assert "ER 90%" in text
    assert "不等于字段值已经人工确认" in text
    assert "优先参考对应ROI" in text
    assert "不要仅因存在ROI就自动提高confidence" in text


def test_no_roi_keeps_full_page_ocr_unchanged():
    assert _compose_ai_ocr_text("整页OCR正文", []) == "整页OCR正文"


def test_roi_crop_is_clamped_to_sanitized_image_bounds():
    source = Image.new("RGB", (100, 80), "white")
    payload = _crop_region_png(
        source,
        {"x": 90, "y": 70, "width": 30, "height": 30},
    )

    assert payload is not None
    with Image.open(io.BytesIO(payload)) as cropped:
        assert cropped.size == (10, 10)
