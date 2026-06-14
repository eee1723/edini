"""
诊断脚本：找出 Houdini 21 中"带距离标尺的网格"对应的 display set 名称。
在 Houdini Python Shell 中粘贴运行。
"""
import hou

desktop = hou.ui.curDesktop()
viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
viewport = viewer.curViewport()
vp_settings = viewport.settings()

# ══════════════════════════════════════════════════════════════
# 1. 列出 ALL displaySetType 枚举值（含数字 ID）
# ══════════════════════════════════════════════════════════════
print("=== ALL displaySetType values ===")
for attr_name in sorted(dir(hou.displaySetType)):
    if attr_name.startswith("_"):
        continue
    try:
        ds_type = getattr(hou.displaySetType, attr_name)
        if callable(ds_type):
            continue
        ds = vp_settings.displaySet(ds_type)
        label = ""
        try:
            label = ds.label() or ""
        except:
            pass
        hidden = ds.isHidden()
        print(f"  {attr_name:30s}  hidden={hidden}  label={label}")
    except Exception as e:
        print(f"  {attr_name:30s}  ERROR: {e}")

# ══════════════════════════════════════════════════════════════
# 2. 查看 DisplayModel 的子选项（可能有 wireframe overlay）
# ══════════════════════════════════════════════════════════════
print("\n=== DisplayModel sub-options ===")
model_ds = vp_settings.displaySet(hou.displaySetType.DisplayModel)
for attr_name in sorted(dir(model_ds)):
    if attr_name.startswith("_"):
        continue
    try:
        val = getattr(model_ds, attr_name)
        if callable(val):
            try:
                result = val()
                if result is not None:
                    print(f"  {attr_name}() = {result}")
            except:
                pass
        else:
            print(f"  {attr_name} = {val}")
    except Exception as e:
        pass

# ══════════════════════════════════════════════════════════════
# 3. 查看 viewport.settings() 顶层方法（showGrid, showGuides 等）
# ══════════════════════════════════════════════════════════════
print("\n=== ViewportSettings methods (grid/guide related) ===")
for attr_name in sorted(dir(vp_settings)):
    if any(kw in attr_name.lower() for kw in ["grid", "guide", "plane", "ground", "ruler", "scale", "reference", "construction"]):
        try:
            val = getattr(vp_settings, attr_name)
            if callable(val):
                try:
                    result = val()
                    print(f"  vp_settings.{attr_name}() = {result}")
                except:
                    print(f"  vp_settings.{attr_name}() = <call failed>")
            else:
                print(f"  vp_settings.{attr_name} = {val}")
        except:
            pass

# ══════════════════════════════════════════════════════════════
# 4. 尝试通过 setHidden 禁用所有 display set
# ══════════════════════════════════════════════════════════════
print("\n=== Force-hide ALL display sets ===")
hidden_count = 0
for attr_name in sorted(dir(hou.displaySetType)):
    if attr_name.startswith("_"):
        continue
    try:
        ds_type = getattr(hou.displaySetType, attr_name)
        if callable(ds_type):
            continue
        ds = vp_settings.displaySet(ds_type)
        ds.setHidden(True)
        hidden_count += 1
    except:
        pass
print(f"  Hidden {hidden_count} display sets")

# ══════════════════════════════════════════════════════════════
# 5. 测试截图 — 用当前 viewport 状态直接 flipbook
# ══════════════════════════════════════════════════════════════
import os
out_dir = os.path.join(os.path.expanduser("~"), "screenshots")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "capture_no_grid_test.png")

base_settings = viewer.flipbookSettings()
settings = base_settings.stash() if hasattr(base_settings, "stash") else base_settings
settings.output(out_path)
settings.outputToMPlay(False)
settings.frameRange((1, 1))
try:
    settings.resolution((800, 600))
except:
    pass

# 先打印 flipbookSettings 上的可用属性
print("\n=== FlipbookSettings attributes ===")
for attr_name in sorted(dir(settings)):
    if attr_name.startswith("_"):
        continue
    try:
        val = getattr(settings, attr_name)
        if callable(val):
            continue
        print(f"  settings.{attr_name} = {val}")
    except:
        pass

viewer.flipbook(viewport, settings)

if os.path.exists(out_path):
    print(f"\n  Screenshot saved: {out_path}  ({os.path.getsize(out_path)/1024:.1f} KB)")
else:
    print(f"\n  FAIL: no file at {out_path}")

print("\n=== DONE ===")
