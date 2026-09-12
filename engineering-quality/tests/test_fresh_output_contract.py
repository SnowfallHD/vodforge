from quality_harness.security import fresh_output_contract_probe


def test_fresh_output_contract_accepts_quiet_aac_and_rejects_invalid_outputs(tmp_path):
    scenario, findings = fresh_output_contract_probe(tmp_path)
    assert scenario["status"] == "passed", scenario["evidence"]
    assert not findings
    assert any("quiet AAC" in item for item in scenario["evidence"])
