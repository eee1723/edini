"""One-shot: author the edini::project HDA definition (SOP context).

Run ONCE via hython to (re)generate otls/edini_project.hda:
    hython scripts/make_project_hda.py

The .hda is committed to the repo and auto-loaded by Houdini via
HOUDINI_OTLSCAN_PATH ($EDINI_PATH/otls). Do NOT run at Houdini startup.

**SOP context (not Object).** This HDA is authored from a subnet INSIDE a geo
node's SOP network, so it registers in the Sop node-type category. Instances
live inside a geo and their internal network is a SOP environment — exactly
what rooted build_assembly needs (it creates box/attribwrangle/copytopoints
SOPs directly). An Object-context HDA can't host SOP children, which is why
this was switched from Object to SOP context.
"""
import os
import hou


def main() -> None:
    otls_dir = os.path.join(os.path.dirname(__file__), "..", "otls")
    os.makedirs(otls_dir, exist_ok=True)
    hda_file = os.path.abspath(os.path.join(otls_dir, "edini_project.hda"))

    # Author from a subnet INSIDE a geo → SOP-context HDA.
    obj = hou.node("/obj")
    geo = obj.createNode("geo", "edini_project_author_tmp")
    geo_path = geo.path()
    try:
        # Inside the geo's SOP network, create a subnet. A subnet inside a geo
        # is a SOP-context node; createDigitalAsset on it yields a Sop-category
        # HDA type that can be instanced inside any geo.
        subnet = geo.createNode("subnet", "inner")
        subnet_path = subnet.path()
        subnet.createDigitalAsset(
            name="edini::project",
            hda_file_name=hda_file,
            description="Edini Project — a procedural-modeling project agent container (SOP)",
        )
        # createDigitalAsset changes the node's type IN PLACE, invalidating the
        # Python reference. Re-fetch by path before touching it again.
        subnet = hou.node(subnet_path)
        d = subnet.type().definition()
        # Minimal default parms: none. The hidden __edini_state parm and design
        # params are added per-instance at runtime by create_project_hda.
        d.save(hda_file)

        # Confirm the type category is Sop (sanity check).
        t = hou.nodeType(hou.sopNodeTypeCategory(), "edini::project")
        cat = t.category().name() if t else "NOT FOUND"
        if cat != "Sop":
            raise RuntimeError(
                f"edini::project HDA is in '{cat}' category, expected 'Sop'. "
                "The authoring sequence must create the asset from a subnet "
                "INSIDE a geo, not from an /obj subnet."
            )
        print(f"[ok] type category: {cat}")
    finally:
        # Never let cleanup raise.
        try:
            hou.node(geo_path).destroy()
        except Exception:
            pass

    print(f"[ok] wrote {hda_file}")


if __name__ == "__main__":
    main()
