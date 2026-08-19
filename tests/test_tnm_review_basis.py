from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_tnm_basis_is_gated_in_core_review_renderer():
    app_js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'const showTnmBasis=["clinical_stage","pathological_stage"].includes(observation.field_name)&&basis.length>0;' in app_js
    assert 'basisBox.hidden=!showTnmBasis;' in app_js
    assert 'basisBox.innerHTML=showTnmBasis?' in app_js


def test_review_inline_no_longer_hides_tnm_basis_after_render():
    review_js = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")
    assert 'const TNM_FIELDS = new Set([' not in review_js
    assert 'basisBox && !TNM_FIELDS.has(observation.field_name)' not in review_js
