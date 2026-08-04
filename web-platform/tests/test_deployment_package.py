from __future__ import annotations

import importlib
import sys


def test_web_api_does_not_depend_on_parent_careerflow_package(monkeypatch) -> None:
    """The Vercel root is web-platform/, so imports must remain self-contained."""
    monkeypatch.setitem(sys.modules, "careerflow", None)
    module = importlib.import_module("api.workflows")
    assert callable(module.validate_draft_bundle)
    assert callable(module.markdown_to_html)


def test_compatibility_helpers_preserve_expected_contracts() -> None:
    from shared.careerflow_compat import extract_jd_emails, safe_attachment_name

    assert extract_jd_emails("Apply via HR@Example.com or hr@example.com") == ["hr@example.com"]
    assert safe_attachment_name('Alex: Analyst/Intern', '.pdf') == "Alex- Analyst-Intern.pdf"
