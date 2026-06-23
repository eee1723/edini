"""Tests for parameter UI grouping + derived hiding (Batch 4).

P4 regression: derived params were installed into the SAME visible folder as
primary params, so a 20-param asset showed ~half "(auto)" controls the user
should never touch. The fix routes derived params into a separate
"Derived (auto)" folder and supports ``ui.group`` on primaries to split
controls across multiple folders.

These tests use a fake hou (FolderParmTemplate / ParmTemplateGroup mocks) to
verify the folder structure without a real Houdini.
"""
from __future__ import annotations

import sys
from unittest import mock

if "hou" not in sys.modules:
    sys.modules["hou"] = mock.MagicMock(name="hou")

from edini import harness as h  # noqa: E402


# ── Fake hou primitives that record structure ─────────────────────────────

class FakeFolder:
    """Records its symbol/label and the parm templates added to it."""
    def __init__(self, symbol, label, folder_type=None):
        self.symbol = symbol
        self.label = label
        self.parms = []  # parm names added
        self.added_folders = []

    def addParmTemplate(self, tmpl):
        if isinstance(tmpl, FakeFolder):
            self.added_folders.append(tmpl)
        else:
            self.parms.append(tmpl.name)


class FakeParmTemplate:
    def __init__(self, name, label=None):
        self.name = name
        self.label = label or name


class FakeParmTemplateGroup:
    def __init__(self):
        self.folders = []

    def append(self, folder):
        self.folders.append(folder)


def _make_hou():
    """A fake hou with the classes the installer touches."""
    hou = mock.MagicMock(name="hou")

    class _FolderType:
        Tabs = 0
    hou.folderType = _FolderType()

    hou.FolderParmTemplate.side_effect = (
        lambda sym, lbl, folder_type=None: FakeFolder(sym, lbl, folder_type))
    hou.FloatParmTemplate.side_effect = (
        lambda name, label, *a, **k: FakeParmTemplate(name, label))
    hou.ParmTemplateGroup.side_effect = FakeParmTemplateGroup
    return hou


# ── _sanitize_folder_name ────────────────────────────────────────────────

class TestSanitizeFolderName:
    def test_basic(self):
        assert h._sanitize_folder_name("Wheels") == "Wheels"

    def test_spaces_and_punct(self):
        assert h._sanitize_folder_name("Wheels & Frame") == "Wheels___Frame"

    def test_auto_label(self):
        assert h._sanitize_folder_name("Derived (auto)") == "Derived__auto_"


# ── Folder grouping ───────────────────────────────────────────────────────

class TestInstallGrouping:
    def _root_with_group(self):
        """A fake root node whose parmTemplateGroup() returns a fresh group."""
        hou = _make_hou()
        group = FakeParmTemplateGroup()
        root = mock.MagicMock()
        root.parmTemplateGroup.return_value = group
        root.setParmTemplateGroup = mock.MagicMock()
        return root, hou, group

    def test_all_primary_one_group(self):
        root, hou, group = self._root_with_group()
        t1 = hou.FloatParmTemplate("a", "A")
        t2 = hou.FloatParmTemplate("b", "B")
        h._install_params_via_template_group(
            root, hou, [t1, t2],
            grouping=[("a", "Parameters", False), ("b", "Parameters", False)])
        # one folder, both parms in it
        assert len(group.folders) == 1
        assert set(group.folders[0].parms) == {"a", "b"}

    def test_primary_split_into_groups(self):
        root, hou, group = self._root_with_group()
        h._install_params_via_template_group(
            root, hou,
            [hou.FloatParmTemplate("w1", "W1"), hou.FloatParmTemplate("f1", "F1")],
            grouping=[("w1", "Wheels", False), ("f1", "Frame", False)])
        labels = [f.label for f in group.folders]
        assert "Wheels" in labels and "Frame" in labels
        assert len(group.folders) == 2

    def test_derived_go_to_separate_auto_folder(self):
        """THE P4 fix: derived params land in 'Derived (auto)', not the main
        Parameters folder."""
        root, hou, group = self._root_with_group()
        h._install_params_via_template_group(
            root, hou,
            [hou.FloatParmTemplate("primary", "P"),
             hou.FloatParmTemplate("derived_x", "DX")],
            grouping=[("primary", "Parameters", False),
                      ("derived_x", "Derived (auto)", True)])
        # Two folders: Parameters (primary) + Derived (auto) (derived)
        labels = [f.label for f in group.folders]
        assert "Parameters" in labels
        assert "Derived (auto)" in labels
        # The primary folder has ONLY primary; derived folder has ONLY derived
        prim = next(f for f in group.folders if f.label == "Parameters")
        der = next(f for f in group.folders if f.label == "Derived (auto)")
        assert prim.parms == ["primary"]
        assert der.parms == ["derived_x"]

    def test_derived_folder_appended_last(self):
        root, hou, group = self._root_with_group()
        h._install_params_via_template_group(
            root, hou,
            [hou.FloatParmTemplate("d", "D"), hou.FloatParmTemplate("p", "P")],
            grouping=[("d", "Derived (auto)", True),
                      ("p", "Parameters", False)])
        # Primary folder must come BEFORE derived regardless of input order
        labels = [f.label for f in group.folders]
        assert labels.index("Parameters") < labels.index("Derived (auto)")

    def test_no_grouping_falls_back_to_single_folder(self):
        """Legacy callers (grouping=None) get the old single-folder behavior."""
        root, hou, group = self._root_with_group()
        h._install_params_via_template_group(
            root, hou,
            [hou.FloatParmTemplate("a", "A"), hou.FloatParmTemplate("b", "B")])
        assert len(group.folders) == 1
        assert group.folders[0].label == "Parameters"


# ── _install_spare_params end-to-end (mocked hou) ────────────────────────

class TestInstallSpareParamsEndToEnd:
    def _setup(self):
        """Configure the REAL hou module in sys.modules with fake classes.

        _install_spare_params does a local `import hou as _hou`, so we must
        configure sys.modules['hou'] itself (not a separate mock) for the
        FloatParmTemplate/FolderParmTemplate fakes to take effect.
        """
        class FakeFolder:
            def __init__(self, symbol, label, folder_type=None):
                self.symbol = symbol
                self.label = label
                self.parms = []
                self.added_folders = []

            def addParmTemplate(self, tmpl):
                if isinstance(tmpl, FakeFolder):
                    self.added_folders.append(tmpl)
                else:
                    self.parms.append(tmpl.name)

        class FakeParmTemplate:
            def __init__(self, name, label=None):
                self.name = name
                self.label = label or name
            # _build_float_parm_template calls setMin/setMax/setMinValueStr/...
            def setMin(self, v): pass
            def setMax(self, v): pass
            def setMinValueStr(self, v): pass
            def setMaxValueStr(self, v): pass

        class FakeParmTemplateGroup:
            def __init__(self):
                self.folders = []
            def append(self, folder):
                self.folders.append(folder)

        class _FolderType:
            Tabs = 0

        hou = mock.MagicMock(name="hou")
        hou.folderType = _FolderType()
        hou.FolderParmTemplate.side_effect = (
            lambda sym, lbl, folder_type=None: FakeFolder(sym, lbl, folder_type))
        # FloatParmTemplate is called many ways; accept any positional/kwargs
        hou.FloatParmTemplate.side_effect = (
            lambda *a, **k: FakeParmTemplate(
                a[0] if a else k.get("name"), a[1] if len(a) > 1 else k.get("label")))
        hou.ParmTemplateGroup = FakeParmTemplateGroup
        # Install into sys.modules so the harness's local `import hou` finds it.
        sys.modules["hou"] = hou

        group = FakeParmTemplateGroup()
        root = mock.MagicMock()
        root.path.return_value = "/obj/sb"
        root.parmTemplateGroup.return_value = group
        root.setParmTemplateGroup = mock.MagicMock()
        return hou, root, group

    def test_primary_group_field_read_from_ui(self):
        """ui.group on a primary param routes it to a named folder."""
        hou, root, group = self._setup()
        params_spec = {
            "wheel_r": {"default": 0.35, "ui": {"group": "Wheels"}},
            "bb_drop": {"default": 0.07, "ui": {"group": "Frame"}},
        }
        result = h._install_spare_params(root, params_spec, derived_values={})
        labels = [f.label for f in group.folders]
        assert "Wheels" in labels and "Frame" in labels
        # result records the group
        assert result["wheel_r"]["group"] == "Wheels"

    def test_derived_routed_to_auto_folder(self):
        hou, root, group = self._setup()
        params_spec = {
            "wheel_r": {"default": 0.35},
            "bb_height": {"kind": "derived", "from": "wheel_r - 0.07"},
        }
        derived = {"bb_height": {"value": 0.28, "label": "BB Height"}}
        result = h._install_spare_params(root, params_spec, derived_values=derived)
        labels = [f.label for f in group.folders]
        assert "Derived (auto)" in labels
        der = next(f for f in group.folders if f.label == "Derived (auto)")
        assert "bb_height" in der.parms
        # primary NOT in derived folder
        prim = next(f for f in group.folders if f.label == "Parameters")
        assert "bb_height" not in prim.parms
        assert result["bb_height"]["group"] == "Derived (auto)"

    def test_derived_still_installed_as_channel(self):
        """Hiding in a folder must NOT break channel binding — hou.ch still
        resolves because the parm exists on root."""
        hou, root, group = self._setup()
        params_spec = {"wheel_r": {"default": 0.35}}
        derived = {"bb_height": {"value": 0.28}}
        result = h._install_spare_params(root, params_spec, derived_values=derived)
        # derived still has a channel_path → consumers can hou.ch("../bb_height")
        assert "channel_path" in result["bb_height"]
        assert result["bb_height"]["installed"] is True
