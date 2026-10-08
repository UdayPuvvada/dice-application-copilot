import json

import pytest

from dice_copilot.applicant import Applicant


def test_applicant_requires_real_resume(tmp_path):
    profile = tmp_path / "applicant.json"
    profile.write_text(json.dumps({
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "phone": "3125550100",
        "resume_path": "missing.pdf",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Resume must be"):
        Applicant.load(profile)


def test_resume_rules_select_best_title_match_and_fallback(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    data_resume = folder / "data.pdf"
    java_resume = folder / "java.pdf"
    fallback = folder / "general.pdf"
    for path in (data_resume, java_resume, fallback):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "data|etl", "file": "data.pdf"},
            {"title_pattern": "java|spring", "file": "java.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior Data Engineer", tmp_path) == data_resume
    assert applicant.resume_for("Java Developer", tmp_path) == java_resume
    assert applicant.resume_for("Product Manager", tmp_path) == fallback


def test_resume_rules_prefer_multiple_keywords_in_any_order(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    general = folder / "general.pdf"
    oracle = folder / "oracle.pdf"
    oracle_dba = folder / "oracle-dba.pdf"
    for path in (general, oracle, oracle_dba):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(general),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "oracle", "file": "oracle.pdf"},
            {"title_pattern": "oracle dba", "file": "oracle-dba.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior Oracle SQL DBA", tmp_path) == oracle_dba
    assert applicant.resume_for("DBA for Oracle Cloud", tmp_path) == oracle_dba


def test_resume_rules_tolerate_minor_keyword_typos(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    databricks = folder / "databricks.pdf"
    for path in (fallback, databricks):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[{"title_pattern": "databricks architect", "file": "databricks.pdf"}],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior Data Bricks Archtect", tmp_path) == databricks


def test_resume_rules_do_not_select_on_one_word_from_specific_phrase(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    oracle_fusion = folder / "oracle-fusion.pdf"
    for path in (fallback, oracle_fusion):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[{"title_pattern": "oracle fusion|fusion cloud", "file": "oracle-fusion.pdf"}],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior Cloud Engineer", tmp_path) == fallback


def test_resume_rules_match_full_stack_engineer_with_extra_modifiers(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    full_stack = folder / "full-stack.pdf"
    for path in (fallback, full_stack):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "ai engineer", "file": "general.pdf"},
            {"title_pattern": "full.?stack developer|full.?stack engineer", "file": "full-stack.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("AI Enabled Full Stack Engineer", tmp_path) == full_stack


def test_resume_rules_prefer_specialized_ai_infrastructure_profile(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    general_ai = folder / "ai.pdf"
    ai_infrastructure = folder / "ai-infrastructure.pdf"
    for path in (fallback, general_ai, ai_infrastructure):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "ai engineer", "file": "ai.pdf"},
            {"title_pattern": "ai infrastructure engineer|gpu infrastructure", "file": "ai-infrastructure.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior AI Infrastructure Engineer", tmp_path) == ai_infrastructure


def test_resume_rules_distinguish_oracle_ebs_from_oracle_erp(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    ebs = folder / "ebs.pdf"
    erp = folder / "erp.pdf"
    for path in (fallback, ebs, erp):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "oracle ebs|oracle e-business", "file": "ebs.pdf"},
            {"title_pattern": "oracle erp|oracle fusion administrator", "file": "erp.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Senior Oracle EBS Technical Consultant", tmp_path) == ebs
    assert applicant.resume_for("Oracle Cloud ERP Security Administrator", tmp_path) == erp


def test_resume_rules_prefer_data_profile_for_combined_data_ai_title(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    ai = folder / "ai.pdf"
    data = folder / "data.pdf"
    for path in (fallback, ai, data):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "ai engineer", "file": "ai.pdf"},
            {"title_pattern": "data.*ai.*analytics|data.*ai engineer|data engineer", "file": "data.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    assert applicant.resume_for("Data & AI Engineer - Analytics", tmp_path) == data


def test_resume_rules_use_description_when_title_is_ambiguous(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    fallback = folder / "general.pdf"
    business = folder / "business.pdf"
    security = folder / "security.pdf"
    for path in (fallback, business, security):
        path.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_path=str(fallback),
        resume_folder=str(folder),
        resume_rules=[
            {"title_pattern": "security analyst", "file": "security.pdf"},
            {"title_pattern": "business operations analyst|operations business analyst|business analyst", "file": "business.pdf"},
        ],
    )
    applicant.validate(tmp_path)
    description = "Support business operations through data analysis, auditing, Excel reporting, and process improvement."
    assert applicant.resume_for("Analyst", tmp_path, description) == business


def test_resume_rule_cannot_escape_folder(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 test")
    applicant = Applicant(
        "Jane", "Doe", "jane@example.com", "3125550100",
        resume_folder=str(folder),
        resume_rules=[{"title_pattern": "data", "file": "../outside.pdf"}],
    )
    with pytest.raises(ValueError, match="inside resume_folder"):
        applicant.validate(tmp_path)
