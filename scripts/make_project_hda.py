"""One-shot: author the edini::project HDA definition.

Run ONCE via hython to (re)generate otls/edini_project.hda:
    hython scripts/make_project_hda.py

The .hda is committed to the repo and auto-loaded by Houdini via
HOUDINI_OTLSCAN_PATH ($EDINI_PATH/otls). Do NOT run at Houdini startup.
"""
import os
import hou


def main() -> None:
    otls_dir = os.path.join(os.path.dirname(__file__), "..", "otls")
    os.makedirs(otls_dir, exist_ok=True)
    hda_file = os.path.abspath(os.path.join(otls_dir, "edini_project.hda"))

    # Clean any pre-existing temp node.
    obj = hou.node("/obj")
    tmp = obj.createNode("subnet", "edini_project_author_tmp")
    tmp_path = tmp.path()
    try:
        # Create the digital asset from the subnet.
        tmp.createDigitalAsset(
            name="edini::project",
            hda_file_name=hda_file,
            description="Edini Project — a procedural-modeling project agent container",
        )
        # NOTE: createDigitalAsset changes the node's type IN PLACE, which
        # invalidates the `tmp` Python reference (hou.ObjectWasDeleted on
        # next access). Re-fetch by path before touching it again.
        tmp = hou.node(tmp_path)
        d = tmp.type().definition()
        # Minimal default parms: none. The hidden __edini_state parm and
        # design params are added per-instance at runtime by create_project_hda.
        d.save(hda_file)
    finally:
        # Re-fetch in case it was invalidated above; never let cleanup raise.
        try:
            hou.node(tmp_path).destroy()
        except Exception:
            pass

    print(f"[ok] wrote {hda_file}")


if __name__ == "__main__":
    main()
