"""cp-ui vendors ui-ux-pro-max (MIT) and runs it offline, stdlib only (python -S)."""
import json
import subprocess

from conftest import SKILLS_DIR

UI = SKILLS_DIR / "cp-ui"
VENDOR = UI / "vendor" / "uupm"

LOAD_AND_GENERATE = """
import json, sys
sys.path.insert(0, %r)
import uupm
m = uupm.load()
r = m.design_system.DesignSystemGenerator().generate(%r, 'demo')
assert m.core.search('dashboard', 'style', 1)
print(json.dumps(r))
"""


def run_py(python_cmd, *args):
    r = subprocess.run([python_cmd, *args], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_vendor_has_license_and_pinned_version():
    assert (VENDOR / "LICENSE").read_text().startswith("MIT License")
    assert (VENDOR / "VERSION").read_text().strip() == "2.15.0 @ 2de1134"


def test_vendored_generator_runs_offline(python_cmd):
    code = LOAD_AND_GENERATE % (str(UI / "scripts"), "legal saas dashboard")
    out = run_py(python_cmd, "-S", "-I", "-c", code)
    data = json.loads(out[out.index("{"):])
    assert data["colors"]["primary"].startswith("#")
    assert data["typography"]["heading"]


def test_excluded_files_are_not_vendored():
    assert not (VENDOR / "scripts" / "validate_data.py").exists()
    assert not (VENDOR / "scripts" / "search.py").exists()
    assert not (VENDOR / "data" / "phosphor-icons-upstream.json").exists()
    assert not (VENDOR / "data" / "google-font-licenses.json").exists()
