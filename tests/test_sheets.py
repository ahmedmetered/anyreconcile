"""The Sheets push is tested with a fake gspread, so no network or credentials are needed."""

import sys
import types

import pytest

from anyreconcile.sheets import push_exceptions


class FakeTab:
    def __init__(self):
        self.cleared = False
        self.updated = None

    def clear(self):
        self.cleared = True

    def update(self, values, range_name):
        self.updated = (values, range_name)


def fake_gspread(existing_tab):
    mod = types.ModuleType("gspread")

    class WorksheetNotFound(Exception):
        pass

    class Book:
        def worksheet(self, name):
            if existing_tab is None:
                raise WorksheetNotFound(name)
            return existing_tab

        def add_worksheet(self, name, rows, cols):
            self.created = (name, rows, cols)
            return FakeTab()

    mod.WorksheetNotFound = WorksheetNotFound
    mod.service_account = lambda filename: types.SimpleNamespace(open=lambda title: Book())
    return mod


def test_replaces_the_exceptions_tab(tmp_path, monkeypatch):
    tab = FakeTab()
    monkeypatch.setitem(sys.modules, "gspread", fake_gspread(tab))
    csv_path = tmp_path / "exceptions.csv"
    csv_path.write_text('a,reason\n1,no deposit\n2,"two, candidates"\n')
    n = push_exceptions(csv_path, tmp_path / "key.json", "Books")
    assert n == 2 and tab.cleared
    assert tab.updated == ([["a", "reason"], ["1", "no deposit"], ["2", "two, candidates"]], "A1")


def test_creates_the_tab_when_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "gspread", fake_gspread(None))
    csv_path = tmp_path / "exceptions.csv"
    csv_path.write_text("a,reason\n")
    assert push_exceptions(csv_path, tmp_path / "key.json", "Books") == 0


def test_missing_package_gives_install_hint(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "gspread", None)  # makes "import gspread" fail
    with pytest.raises(RuntimeError, match=r"anyreconcile\[sheets\]"):
        push_exceptions(tmp_path / "x.csv", tmp_path / "k.json", "Books")
