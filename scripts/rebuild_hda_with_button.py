"""Add a 'Capture All Recipes' button to the edini_recipe_manager HDA.

Run this ONCE in the Houdini Python Source Editor / Python Shell. It uses the
hou.HDADefinition API to programmatically add a button parm whose callback
captures every leaf subnet inside the HDA into the recipe library (writing
recipe.json + python_script for each, and rebuilding the index). After this,
adding a new recipe is just: dive into the HDA, build a subnet, set its Notes,
tweak the params you care about (they'll be auto-marked via the manifest diff),
then click the button — edini sees the new recipe on its next recipe_list.

Usage (inside Houdini):
    import sys; sys.path.insert(0, r"E:\\edini\\python3.11libs")
    import importlib
    import scripts.rebuild_hda_with_button as b
    importlib.reload(b)
    print(b.main())

Or paste the body of main() directly. Safe to re-run (it replaces the button
if it already exists rather than duplicating it).
"""
import hou

HDA_TYPE = "edini_recipe_manager"
# The button lives on the HDA's top-level parm interface. Its callback runs in
# the HDA node's context, so hou.node('.') is the HDA instance being clicked.
BUTTON_PARM = "capture_all_recipes"
BUTTON_LABEL = "Capture All Recipes"

# The callback script itself. Kept as a string so it is embedded in the HDA
# definition (no external file dependency). It captures the whole tree, then
# surfaces a short summary so the user knows what happened.
CALLBACK_SCRIPT = r"""
node = hou.node('.')
try:
    import sys
    edini_lib = r"E:\\edini\\python3.11libs"
    if edini_lib not in sys.path:
        sys.path.insert(0, edini_lib)
    from edini import recipe_library as rl
    r = rl.recipe_capture_tree(node.path())
    if not r.get('success'):
        hou.ui.displayMessage(
            "Capture failed:\n" + r.get('error', 'unknown error'),
            title="Edini Recipe Capture", severity=hou.severityType.Error)
    else:
        n_cap = r.get('captured_count', 0)
        n_skip = r.get('skipped_count', 0)
        skipped = r.get('skipped', [])
        msg = "Captured {} recipe(s).".format(n_cap)
        if n_skip:
            msg += "\nSkipped {}:".format(n_skip)
            for s in skipped[:8]:
                msg += "\n  - {}: {}".format(s.get('recipe_id', '?'),
                                              s.get('error', '?'))
            if len(skipped) > 8:
                msg += "\n  ... ({} more)".format(len(skipped) - 8)
        hou.ui.displayMessage(msg, title="Edini Recipe Capture")
except Exception as e:
    import traceback
    hou.ui.displayMessage(
        "Capture error:\n" + traceback.format_exc(),
        title="Edini Recipe Capture", severity=hou.severityType.Error)
""".strip()


def _find_definition():
    """Locate the edini_recipe_manager HDA definition (any installed copy)."""
    for cat in hou.nodeTypeCategories().values():
        try:
            types = cat.nodeTypes()
        except Exception:
            continue
        for name, nt in types.items():
            # Match the base name regardless of category path.
            if name.split("/")[-1] == HDA_TYPE or name == HDA_TYPE:
                d = nt.definition()
                if d is not None:
                    return d
    return None


def _replace_or_add_button(group):
    """Add (or replace) the capture button in the HDA's parm template group.

    Re-running the script must not stack duplicate buttons, so remove any
    existing entry with the same parm name first.
    """
    try:
        group.remove(BUTTON_PARM)
    except Exception:
        pass
    btn = hou.ButtonParmTemplate(BUTTON_PARM, BUTTON_LABEL)
    btn.setHelp(
        "Capture every leaf subnet inside this HDA into the recipe library. "
        "Each leaf's node network + author-marked parameters + Notes are "
        "serialized to recipe.json with a readable python_script for edini to "
        "use as reference material. Run this after adding/editing subnets.")
    btn.setScript(CALLBACK_SCRIPT, script_type="python")
    group.append(btn)


def main():
    """Install the capture button on the HDA definition and save it."""
    d = _find_definition()
    if d is None:
        return ("ERROR: HDA definition '{}' not found. Create the recipe "
                "manager HDA first (recipe_library.create_recipe_manager)."
                .format(HDA_TYPE))

    group = d.parmTemplateGroup()
    _replace_or_add_button(group)
    d.setParmTemplateGroup(group)

    # Persist to the .hda so the button survives scene reload + travels in git.
    hda_file = d.libraryFilePath()
    d.save(hda_file)
    hou.hda.reloadFile(hda_file)
    return ("OK: '{}' button added to {} and saved to {}.\n"
            "Click it inside an instance of the HDA to capture recipes."
            .format(BUTTON_LABEL, HDA_TYPE, hda_file))


# Allow `execfile`/paste-to-shell: run main() on import only when hou is real.
try:
    _ = hou.applicationVersionString()  # raises if hou is a stub
    RESULT = main()
except Exception as _e:
    RESULT = "NOT RUN (no live Houdini): {}".format(_e)
