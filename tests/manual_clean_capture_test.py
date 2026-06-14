"""
诊断脚本 #2：测试 ConstructionPlane / ReferencePlane 隐藏 + 白边排查。
在 Houdini Python Shell 中粘贴运行。
"""
import hou, os

out_dir = os.path.join(os.path.expanduser("~"), "screenshots")
os.makedirs(out_dir, exist_ok=True)

desktop = hou.ui.curDesktop()
viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
viewport = viewer.curViewport()
vp_settings = viewport.settings()

# ══════════════════════════════════════════════════════════════
# 1. 检查 ConstructionPlane / ReferencePlane 当前状态
# ══════════════════════════════════════════════════════════════
print("=== Plane Visibility ===")
try:
    cp = viewer.constructionPlane()
    print(f"  ConstructionPlane.isVisible() = {cp.isVisible()}")
except Exception as e:
    print(f"  ConstructionPlane: ERROR {e}")

try:
    rp = viewer.referencePlane()
    print(f"  ReferencePlane.isVisible() = {rp.isVisible()}")
except Exception as e:
    print(f"  ReferencePlane: ERROR {e}")

# ══════════════════════════════════════════════════════════════
# 2. 强制隐藏两个 plane + 所有 guides
# ══════════════════════════════════════════════════════════════
print("\n=== Force Hiding Everything ===")
try:
    viewer.constructionPlane().setIsVisible(False)
    print("  ConstructionPlane → hidden")
except Exception as e:
    print(f"  FAIL: {e}")

try:
    viewer.referencePlane().setIsVisible(False)
    print("  ReferencePlane → hidden")
except Exception as e:
    print(f"  FAIL: {e}")

for guide_name in dir(hou.viewportGuide):
    if guide_name.startswith("_"):
        continue
    guide = getattr(hou.viewportGuide, guide_name)
    if callable(guide):
        continue
    try:
        vp_settings.enableGuide(guide, False)
    except:
        pass
print("  All guides → hidden")

try:
    vp_settings.setOrthoRuler(hou.viewportGridRuler.Hide)
    print("  OrthoRuler → Hide")
except:
    pass

# ══════════════════════════════════════════════════════════════
# 3. 截图测试（无 resolution / 有 resolution / viewport 原始尺寸）
# ══════════════════════════════════════════════════════════════
tests = [
    ("native_viewport", None),
    ("640x480", (640, 480)),
    ("800x600", (800, 600)),
    ("960x540", (960, 540)),
    ("1024x768", (1024, 768)),
    ("1280x720", (1280, 720)),
]

for label, res in tests:
    out_path = os.path.join(out_dir, f"clean_test_{label}.png")

    settings = viewer.flipbookSettings().stash() if hasattr(viewer.flipbookSettings(), "stash") else viewer.flipbookSettings()
    settings.output(out_path)
    settings.outputToMPlay(False)
    settings.frameRange((1, 1))
    if res is not None:
        try:
            settings.resolution(res)
        except:
            pass

    viewer.flipbook(viewport, settings)

    if os.path.exists(out_path):
        size_kb = os.path.getsize(out_path) / 1024
        # 用 PIL 检查实际尺寸
        try:
            from PIL import Image
            img = Image.open(out_path)
            w, h = img.size
            # 检查四边是否全白（白边检测）
            corners = [
                img.getpixel((10, 10)),
                img.getpixel((w-10, 10)),
                img.getpixel((10, h-10)),
                img.getpixel((w-10, h-10)),
            ]
            img.close()
            all_white = all(sum(c[:3]) > 700 for c in corners if isinstance(c, tuple))
            print(f"  {label}: {w}x{h} {size_kb:.1f}KB  white_corners={all_white}")
        except:
            print(f"  {label}: {size_kb:.1f}KB (no PIL)")
    else:
        print(f"  {label}: FAIL - no file")

# ══════════════════════════════════════════════════════════════
# 4. 恢复
# ══════════════════════════════════════════════════════════════
try:
    viewer.constructionPlane().setIsVisible(True)
except:
    pass
try:
    viewer.referencePlane().setIsVisible(True)
except:
    pass

print("\n=== DONE ===")
