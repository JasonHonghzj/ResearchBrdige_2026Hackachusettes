"""Replace the brief panel, footer and banner. Anchored on unique markers, with
a structural assertion afterwards -- the previous attempt reported success while
having truncated the file, so validity is checked, not assumed."""
from pathlib import Path

p = Path("static/index.html")
s = p.read_text(encoding="utf-8")
before = len(s)

# ---- brief panel: from the opening div to the end of the email block ----
A = '    <div class="brief">'
B = 'removed as unsupported.</div>\n    </div>'
assert s.count(A) == 1, f"brief anchor x{s.count(A)}"
assert s.count(B) == 1, f"email tail anchor x{s.count(B)}"
a = s.index(A)
b = s.index(B) + len(B)
assert b > a, "anchors out of order"
assert b - a < 6000, f"brief block unexpectedly large: {b-a} chars"
s = s[:a] + '    <div class="brief" id="brief"><p style="color:var(--ink-3)">loading…</p></div>' + s[b:]

# ---- footer ----
F = '  <p class="foot">'
G = '</p>\n  </div><!-- /view-scout -->'
assert s.count(F) == 1 and s.count(G) == 1
f = s.index(F)
g = s.index(G) + len('</p>')
assert g > f and g - f < 1500, f"foot block unexpected: {g-f}"
s = s[:f] + '''  <p class="foot" id="foot">
    <b>Everything in this view is served live</b> from the Scout API — the grid, the confirmed gaps,
    their maturity counts and the reject pile all come from <span class="mono">/api/scout/*</span> over
    79,940 PubMed papers, and the figures update if the data does. The claim check in step 04 is a
    scripted walkthrough of the verification gate on a fixed example; accepting arbitrary input is the
    one piece still to build.
  </p>''' + s[g:]

# ---- banner + styles ----
s = s.replace('<span class="tag mock scout-only">Illustrative mockup</span>',
              '<span class="tag live-tag scout-only">Live data</span>')
assert '#tip{' in s
s = s.replace('#tip{', '''.live{
  font-family:"IBM Plex Mono",monospace;font-size:9px;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;color:var(--good);border:1px solid currentColor;border-radius:3px;
  padding:1px 4px;margin-left:7px;vertical-align:1px
}
.tag.live-tag{background:transparent;border-color:var(--good);color:var(--good)}
.err{background:var(--warn-soft);color:var(--warn);border-radius:5px;padding:11px 13px;font-size:12.5px;line-height:1.55}
#tip{''', 1)

# ---- structural gate: the check the last attempt skipped ----
need = ['</style>', '</script>', 'id="view-scout"', 'id="view-bridge"',
        'id="p1"', 'id="p2"', 'id="p3"', 'id="p4"', 'id="p5"', 'id="p6"',
        'id="map"', 'id="plog"', 'id="corpuskv"', 'id="gapcard"', 'id="gapmeta"',
        'id="rejects"', 'id="bars"', 'id="valkv"', 'id="valcaveat"', 'id="brief"',
        'id="foot"', 'id="tip"', '/static/bridge.js']
missing = [n for n in need if n not in s]
assert not missing, f"MISSING after patch: {missing}"
assert s.count('</section>') >= 6, f"sections: {s.count('</section>')}"
assert len(s) > 30000, f"file shrank to {len(s)} from {before}"

p.write_text(s, encoding="utf-8")
print(f"ok: {before} -> {len(s)} bytes; all {len(need)} structural anchors present")
