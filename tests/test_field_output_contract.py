from app.knowledge import extraction_prompt, questionnaire_field_index
from app.main import field_output_requirement, normalize_observation_value


def test_display_labels_are_normalized_to_canonical_field_values():
    assert normalize_observation_value("smoking_history", "否") == "NO"
    assert normalize_observation_value("smoking_history", "无") == "NO"
    assert normalize_observation_value("smoking_history", "是") == "YES"
    assert normalize_observation_value("primary_er", "阳性") == "POSITIVE"
    assert normalize_observation_value("primary_er", "阴性") == "NEGATIVE"
    assert normalize_observation_value("pre_mmg_single_lesion", "多发") == "MULTIPLE"


def test_positioned_field_contract_explains_yes_no_mapping_to_the_model():
    definition = questionnaire_field_index()["smoking_history"]
    contract = field_output_requirement("smoking_history", definition)

    assert "smoking_history" in contract
    assert "是→YES" in contract
    assert "否→NO" in contract
    assert "不详→UNKNOWN" in contract
    assert "解释和原文只能放入raw_text" in contract


def test_general_extraction_prompt_requires_canonical_value_codes():
    prompt, _ = extraction_prompt("ADMISSION", "无吸烟饮酒等不良嗜好。")
    assert "value必须使用字段values或form_options中定义的标准编码" in prompt
    assert "不能返回中文显示标签或解释性句子" in prompt
    assert "二维值写成25×18，末尾不要添加逗号、乘号或NA" in prompt


def test_positioned_measurement_contract_forbids_a_trailing_delimiter():
    definition = questionnaire_field_index()["pre_us_tumor_size_mm"]
    contract = field_output_requirement("pre_us_tumor_size_mm", definition)
    assert "二维直接写如25×18" in contract
    assert "末尾不得添加逗号、乘号或NA" in contract
