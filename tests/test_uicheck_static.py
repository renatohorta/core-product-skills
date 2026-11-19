"""`_shared/uicheck.py` — static UI checks (one positive + one negative per rule)."""
from _shared import uicheck

DS = {"style": "x", "colors": {}, "token_files": []}


_n = [0]


def _scan(tmp_path, files, ds=DS, exclude=None):
    _n[0] += 1
    tmp_path = tmp_path / f"p{_n[0]}"
    tmp_path.mkdir()
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return uicheck.scan(tmp_path, exclude or [], ds)


def _rules(res):
    return sorted(c.rule for c in res[0])


def test_checks_catalogue():
    assert set(uicheck.CHECKS) == {
        "raw-color", "img-no-alt", "icon-button-no-name", "outline-removed",
        "zoom-disabled", "missing-lang", "missing-viewport", "tiny-font",
        "emoji-icon", "no-reduced-motion"}
    for meta in uicheck.CHECKS.values():
        assert meta["severity"] in ("critical", "high", "medium", "low")
        assert meta["ux_rule"] and meta["summary"]


def test_img_no_alt(tmp_path):
    r = _scan(tmp_path, {"a.tsx": 'const a = <img src="a.png" />;\n'})
    assert _rules(r) == ["img-no-alt"]
    c = r[0][0]
    assert (c.file, c.line, c.severity) == ("a.tsx", 1, "high")


def test_img_with_alt_ok_even_multiline(tmp_path):
    r = _scan(tmp_path, {"a.tsx": '<img alt="" src="a.png">\n<img\n  src="b.png"\n  alt="b"\n/>\n'})
    assert r[0] == []


def test_icon_button_no_name(tmp_path):
    r = _scan(tmp_path, {"a.tsx": "<button onClick={x}><svg/></button>\n"})
    assert _rules(r) == ["icon-button-no-name"]
    r = _scan(tmp_path, {"b.tsx": '<button aria-label="Close"><svg/></button>\n<button><svg/> Save</button>\n'})
    assert r[0] == []


def test_outline_removed(tmp_path):
    r = _scan(tmp_path, {"a.tsx": '<div className="outline-none">\n'})
    assert _rules(r) == ["outline-removed"]
    r = _scan(tmp_path, {"b.tsx": '<div className="outline-none focus-visible:ring-2">\n'})
    assert r[0] == []
    r = _scan(tmp_path, {"c.css": "a { outline: none; }\n"})
    assert _rules(r) == ["outline-removed"]


def test_zoom_disabled(tmp_path):
    r = _scan(tmp_path, {"a.html": '<meta name="viewport" content="width=device-width, user-scalable=no">\n'})
    assert _rules(r) == ["zoom-disabled"]
    r = _scan(tmp_path, {"b.html": '<meta name="viewport" content="width=device-width, initial-scale=1">\n'})
    assert r[0] == []


def test_missing_lang_and_viewport(tmp_path):
    r = _scan(tmp_path, {"a.html": "<html>\n<body></body>\n</html>\n"})
    assert _rules(r) == ["missing-lang", "missing-viewport"]
    r = _scan(tmp_path, {"b.html": '<html lang="en">\n<meta name="viewport" content="width=device-width">\n</html>\n'})
    assert r[0] == []


def test_lang_viewport_not_for_components(tmp_path):
    r = _scan(tmp_path, {"a.html": "<div>fragment</div>\n", "b.tsx": "<div/>\n"})
    assert r[0] == []


def test_tiny_font(tmp_path):
    r = _scan(tmp_path, {"a.css": "p { font-size: 10px; }\n", "b.tsx": '<p className="text-[9px]">x</p>\n'})
    assert _rules(r) == ["tiny-font", "tiny-font"]
    r = _scan(tmp_path, {"c.css": "p { font-size: 12px; }\n", "d.tsx": '<p className="text-xs text-[14px]">x</p>\n'})
    assert r[0] == []


def test_emoji_icon(tmp_path):
    r = _scan(tmp_path, {"a.html": "<button>🔍 Search</button>\n"})
    assert _rules(r) == ["emoji-icon"]
    r = _scan(tmp_path, {"b.html": "<button>Search 🔍</button>\n<p>🔍 hi</p>\n"})
    assert r[0] == []


def test_raw_color(tmp_path):
    r = _scan(tmp_path, {"a.css": "p { color: #1D4ED8; }\n", "b.tsx": '<div className="bg-[#fff]" style={{color: "rgb(1,2,3)"}}/>\n'})
    assert _rules(r) == ["raw-color", "raw-color"]


def test_raw_color_negatives(tmp_path):
    r = _scan(tmp_path, {
        "a.css": ":root { --brand: #1D4ED8; }\np { color: var(--brand); }\n",
        "tokens.css": "p { color: #fff; }\n",
        "theme.ts": "const c = '#fff'\n",
        "t.css": "p { color: #fff; }\n",
        "l.html": '<a href="#abc">x</a>\n'},
        ds={"token_files": ["t.css"]})
    assert r[0] == []


def test_raw_color_skipped_without_design_system(tmp_path):
    r = _scan(tmp_path, {"a.css": "p { color: #1D4ED8; }\n"}, ds=None)
    assert r[0] == []


def test_no_reduced_motion(tmp_path):
    r = _scan(tmp_path, {"a.css": "@keyframes spin { to { transform: rotate(1turn) } }\n"})
    assert _rules(r) == ["no-reduced-motion"]
    assert r[0][0].file == "(project)"
    r = _scan(tmp_path, {"b.css": "@keyframes s {}\n@media (prefers-reduced-motion: reduce) { * { animation: none } }\n"})
    assert r[0] == []


def test_scan_backend_only_project_scans_zero_files(tmp_path):
    assert _scan(tmp_path, {"app/x.py": "x = 1\n", "y.go": "package y\n"}) == ([], 0)


def test_exclude_and_vendored_dirs(tmp_path):
    r = _scan(tmp_path, {
        "node_modules/p/a.tsx": "<img src='a'/>\n",
        "dist/a.tsx": "<img src='a'/>\n",
        "legacy/a.tsx": "<img src='a'/>\n",
        "src/a.tsx": "<img src='a'/>\n"}, exclude=["legacy/**"])
    assert [c.file for c in r[0]] == ["src/a.tsx"] and r[1] == 1


def test_binary_file_never_crashes(tmp_path):
    p = tmp_path / "a.css"
    p.write_bytes(b"\xff\xfe\x00\x80 p { font-size: 8px }\n")
    r = uicheck.scan(tmp_path, [], None)
    assert r[1] == 1


def test_snippet_truncated(tmp_path):
    r = _scan(tmp_path, {"a.tsx": "<img src='a' " + "x" * 300 + "/>\n"})
    assert len(r[0][0].snippet) <= 160


def test_arrow_handlers_do_not_break_tag_matching(tmp_path):
    r = _scan(tmp_path, {"a.tsx": "<button onClick={() => go()}><svg/></button>\n"})
    assert _rules(r) == ["icon-button-no-name"]
    r = _scan(tmp_path, {"b.tsx": "<a onClick={() => x()}>🔍 Go</a>\n"})
    assert _rules(r) == ["emoji-icon"]
    r = _scan(tmp_path, {"c.tsx": '<img onLoad={() => x()} alt="a">\n'})
    assert r[0] == []
    r = _scan(tmp_path, {"d.tsx": "<img onLoad={() => x()} src=\"a\">\n"})
    assert _rules(r) == ["img-no-alt"]
    r = _scan(tmp_path, {"e.tsx": '<button aria-label="x" onClick={() => go()}><svg/></button>\n'})
    assert r[0] == []


def test_outline_focus_variant_is_not_a_replacement(tmp_path):
    for cls in ("focus:outline-none", "focus-visible:outline-none"):
        r = _scan(tmp_path, {"a.tsx": f'<input className="{cls}" />\n'})
        assert _rules(r) == ["outline-removed"], cls
    for cls in ("outline-none focus:ring-2", "outline-none focus-visible:outline-2",
                "outline-none focus-visible:shadow-md"):
        assert _scan(tmp_path, {"a.tsx": f'<input className="{cls}" />\n'})[0] == [], cls
    assert _scan(tmp_path, {"a.css": "a:focus-visible { outline: none; box-shadow: 0 0 0 2px red; }\n"})[0] == []


def test_raw_color_token_functions_ignored(tmp_path):
    r = _scan(tmp_path, {"a.css": "p { background: hsl(var(--background)); color: rgb(var(--x) / .5); border-color: hsl(theme(colors.x)); }\n"})
    assert r[0] == []
    r = _scan(tmp_path, {"b.css": "p { background: hsl(210 40% 90%); }\n"})
    assert _rules(r) == ["raw-color"]


def test_emoji_icon_not_for_plain_li(tmp_path):
    assert _scan(tmp_path, {"a.html": "<li>✅ Free plan</li>\n"})[0] == []
    assert _rules(_scan(tmp_path, {"b.html": '<ul class="nav"><li>🏠 Home</li></ul>\n'})) == ["emoji-icon"]


def test_reduced_motion_honored_in_script_files(tmp_path):
    r = _scan(tmp_path, {"a.css": "@keyframes s {}\n",
                         "m.ts": "const q = matchMedia('(prefers-reduced-motion: reduce)')\n"})
    assert r[0] == []
    assert r[1] == 1  # only UI files count as scanned
