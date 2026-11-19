"""Loader for the vendored ui-ux-pro-max (MIT) — stdlib only, offline.

    import uupm; m = uupm.load()
    m.core.search(query, domain, max_results)
    m.design_system.DesignSystemGenerator().generate(query, project_name)
"""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "uupm"


def load():
    scripts = str(VENDOR_DIR / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return SimpleNamespace(**{n: importlib.import_module(n)
                              for n in ("core", "design_system", "preview")})
