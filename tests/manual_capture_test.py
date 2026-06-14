"""
手动截图测试脚本 — 在 Houdini Python Shell 中逐段运行。
排查：线框残留 / 参考平面 / 分辨率 / flipbook 参数。
"""

import hou, os

# ══════════════════════════════════════════════════════════════
# 1. 先确保场景中有可渲染的几何体
# ══════════════════════════════════════════════════════════════
obj = hou.node("/obj")
if obj is None:
    raise RuntimeError("No /obj context")

# 创建一个测试球体
test_geo = obj.createNode("geo", "capture_test_target")
sphere = test_geo.createNode("sphere", "test_sphere")
sphere.parm("type").set(1)   # polygon
sphere.parm("radx").set(1.0)
sphere.parm("rady").set(1.0)
sphere.parm("radz").set(1.0)
sphere.setDisplayFlag(True)
sphere.setRenderFlag(True)

# ══════════════════════════════════════════════════════════════
# 2. 获取 viewport 并检查当前显示状态
# ══════════════════════════════════════════════════════════════
desktop = hou.ui.curDesktop()
viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
if viewer is None:
    raise RuntimeError("No Scene Viewer found")

viewport = viewer.curViewport()
vp_settings = viewport.settings()

# 打印所有 display sets 的隐藏状态
print("=== Current Display Set States ===")
for attr_name in dir(hou.displaySetType):
    if attr_name.startswith("_"):
        continue
    try:
        ds_type = getattr(hou.displaySetType, attr_name)
        ds = vp_settings.displaySet(ds_type)
        hidden = ds.isHidden()
        print(f"  {attr_name}: hidden={hidden}")
    except Exception:
        pass

# 打印当前 shading mode
model_ds = vp_settings.displaySet(hou.displaySetType.DisplayModel)
print(f"\n  ShadedMode: {model_ds.shadedMode()}")

# ══════════════════════════════════════════════════════════════
# 3. 应用截图设置（模拟 capture_review 的设置）
# ══════════════════════════════════════════════════════════════
print("\n=== Applying Screenshot Settings ===")

# 隐藏所有可能干扰的显示元素
HIDE_LIST = [
    "Grid",
    "ReferencePlane",
    "GroundPlane",
    "ConstructionPlane",
    "BackgroundImage",
    "GuideGeometry",
    "ParticleDisplay",
]
for name in HIDE_LIST:
    try:
        ds_type = getattr(hou.displaySetType, name, None)
        if ds_type is None:
            continue
        ds = vp_settings.displaySet(ds_type)
        print(f"  Hide {name}: was hidden={ds.isHidden()}")
        ds.setHidden(True)
    except Exception as e:
        print(f"  Hide {name}: SKIP ({e})")

# 设置 shading 为 smooth
model_ds.setShadedMode(hou.glShadingType.Smooth)
print("  Shading: set to Smooth")

# ══════════════════════════════════════════════════════════════
# 4. 测试 flipbook 参数（不同分辨率）
# ══════════════════════════════════════════════════════════════
out_dir = os.path.join(os.path.expanduser("~"), "screenshots")
os.makedirs(out_dir, exist_ok=True)

RESOLUTIONS = [
    (640, 480),
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1920, 1080),
]

for w, h in RESOLUTIONS:
    out_path = os.path.join(out_dir, f"capture_test_{w}x{h}.png")

    base_settings = viewer.flipbookSettings()
    settings = base_settings.stash() if hasattr(base_settings, "stash") else base_settings
    settings.output(out_path)
    settings.outputToMPlay(False)
    settings.frameRange((1, 1))

    # 设置分辨率
    try:
        settings.resolution((w, h))
    except Exception:
        pass  # 某些版本可能不支持

    viewer.flipbook(viewport, settings)

    if os.path.exists(out_path):
        size_kb = os.path.getsize(out_path) / 1024
        print(f"  {w}x{h}: OK ({size_kb:.1f} KB) → {out_path}")
    else:
        print(f"  {w}x{h}: FAIL — file not created")

# ══════════════════════════════════════════════════════════════
# 5. 测试不同 shading 模式
# ══════════════════════════════════════════════════════════════
SHADING_TESTS = {
    "smooth": hou.glShadingType.Smooth,
    "flat": hou.glShadingType.Flat,
    "wire": hou.glShadingType.Wire,
}

for name, mode in SHADING_TESTS.items():
    out_path = os.path.join(out_dir, f"capture_test_shade_{name}.png")
    model_ds.setShadedMode(mode)

    base_settings = viewer.flipbookSettings()
    settings = base_settings.stash() if hasattr(base_settings, "stash") else base_settings
    settings.output(out_path)
    settings.outputToMPlay(False)
    settings.frameRange((1, 1))
    try:
        settings.resolution((800, 600))
    except Exception:
        pass

    viewer.flipbook(viewport, settings)

    if os.path.exists(out_path):
        print(f"  shade={name}: OK → {out_path}")
    else:
        print(f"  shade={name}: FAIL")

# ══════════════════════════════════════════════════════════════
# 6. 恢复 shading
# ══════════════════════════════════════════════════════════════
model_ds.setShadedMode(hou.glShadingType.Smooth)
print("\n=== Done. Restored shading to Smooth ===")
