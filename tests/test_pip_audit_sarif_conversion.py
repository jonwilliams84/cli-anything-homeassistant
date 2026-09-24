"""The Dependency Audit job must survive a pip-audit that writes no report.

pip-audit queries PyPI's JSON API per dependency. On 2026-09-24 `Dependency
Audit` on main failed: PyPI answered "503 Backend is unhealthy", pip-audit
raised ServiceError and exited WITHOUT writing pip-audit.json, and the SARIF
conversion then died on FileNotFoundError. The job now (a) retries the scan
and (b) converts with .github/scripts/pip_audit_to_sarif.py, which must degrade
to an empty, valid SARIF when the report is absent or unusable rather than
crashing. These tests assert that behaviour by running the real converter the
way the workflow does.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERTER = REPO_ROOT / ".github" / "scripts" / "pip_audit_to_sarif.py"


def _run_converter(report: Path | None, out: Path) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(CONVERTER)]
    if report is not None:
        argv.append(str(report))
    argv.append(str(out))
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def test_converter_is_present():
    assert CONVERTER.is_file(), f"converter missing: {CONVERTER}"


def test_missing_report_yields_valid_empty_sarif(tmp_path):
    """The exact CI failure shape: pip-audit wrote no JSON at all."""
    out = tmp_path / "pip-audit.sarif"
    proc = _run_converter(tmp_path / "does-not-exist.json", out)
    assert proc.returncode == 0, proc.stderr
    sarif = json.loads(out.read_text())
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"] == []


def test_malformed_report_yields_valid_empty_sarif(tmp_path):
    bad = tmp_path / "pip-audit.json"
    bad.write_text('{"dependencies": [ truncated')
    out = tmp_path / "pip-audit.sarif"
    proc = _run_converter(bad, out)
    assert proc.returncode == 0, proc.stderr
    sarif = json.loads(out.read_text())
    assert sarif["runs"][0]["results"] == []


def test_report_with_vulnerability_produces_rule_and_result(tmp_path):
    report = tmp_path / "pip-audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "requests",
                        "version": "2.31.0",
                        "vulns": [
                            {
                                "id": "GHSA-xxxx",
                                "description": "a real vulnerability",
                                "fix_versions": ["2.32.0"],
                            }
                        ],
                    }
                ],
            }
        )
    )
    out = tmp_path / "pip-audit.sarif"
    proc = _run_converter(report, out)
    assert proc.returncode == 0, proc.stderr
    sarif = json.loads(out.read_text())
    run = sarif["runs"][0]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["GHSA-xxxx"]
    assert len(run["results"]) == 1
    assert run["results"][0]["ruleId"] == "GHSA-xxxx"
    assert run["results"][0]["level"] == "error"
