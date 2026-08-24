from pathlib import Path

ROOT = Path(__file__).parents[1]


def add_field(client, patient_id: int, field_name: str, value: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/observations",
        json={
            "field_name": field_name,
            "value": value,
            "confidence": "LOW",
            "source_mode": "RECORDED",
            "operator": "local-user",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_pr_observation_exposes_percentage_followup_even_when_initially_negative(client):
    patient = client.post("/api/patients", json={"patient_code": "pr-followup-001"}).json()
    add_field(client, patient["id"], "primary_biopsy_performed", "YES")
    add_field(client, patient["id"], "primary_pr", "NEGATIVE")

    detail = client.get(f"/api/patients/{patient['id']}").json()
    pr = next(item for item in detail["observations"] if item["field_name"] == "primary_pr")
    followup = next(item for item in pr["conditional_followups"] if item["field_name"] == "primary_pr_detail")

    assert followup["field_label"] == "原发灶免疫组化PR:补充填空"
    assert followup["depends_on"] == {
        "field": "primary_pr",
        "equals": "POSITIVE",
        "otherwise": "NOT_APPLICABLE",
    }
    assert "primary_pr_detail" in detail["conditional_na_fields"]

    response = client.patch(
        f"/api/observations/{pr['id']}",
        json={"value": "POSITIVE", "operator": "local-user", "reason": "人工改为阳性"},
    )
    assert response.status_code == 200
    updated = client.get(f"/api/patients/{patient['id']}").json()
    assert "primary_pr_detail" not in updated["conditional_na_fields"]

    preview = client.get("/api/data-preview?verified_only=false").json()
    row = next(item for item in preview["rows"] if item["patient_id"] == patient["id"])
    assert row["statuses"]["primary_pr_detail"] == "EMPTY"


def test_review_ui_renders_and_persists_newly_applicable_followups():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="review-conditional-followups"' in html
    assert "function renderConditionalFollowups(observation)" in javascript
    assert "reviewDependencySatisfied(parentValue,item.depends_on)" in javascript
    assert "请输入具体数值、百分比或说明" in javascript
    assert "async function persistConditionalFollowups" in javascript
    assert "field_name:draft.field_name" in javascript
