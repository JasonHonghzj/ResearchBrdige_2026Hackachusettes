"""Catch malformed nesting that can move a brief outside its navigation panel."""
from html.parser import HTMLParser
from pathlib import Path


class PageStructure(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = {}
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            ident = attrs["id"]
            if ident in self.ids:
                self.errors.append(f"duplicate id: {ident}")
            self.ids[ident] = list(self.stack)
        if tag not in self.VOID:
            self.stack.append((tag, attrs.get("id")))

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f"unexpected </{tag}> inside {self.stack[-1:]}")
        else:
            self.stack.pop()


def test_demo_panels_are_balanced_and_inside_their_own_view():
    page = PageStructure()
    page.feed((Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8"))
    assert not page.errors, page.errors
    assert not page.stack, page.stack
    for prefix, wrapper in (("p", "view-gap"), ("b", "view-bridge")):
        for number in range(1, 7):
            parents = page.ids[f"{prefix}{number}"]
            assert ("div", wrapper) in parents
            assert not any(tag == "section" for tag, _ in parents), parents
    assert ("section", "p6") in page.ids["brief"]
    assert ("section", "p5") in page.ids["bars"]
