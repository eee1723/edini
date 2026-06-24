"""Recipe Manager dashboard — the primary interface for the recipe library.

A three-pane QMainWindow that browses/manages the subnet recipe tree inside the
edini_recipe_manager HDA (or any user-supplied root). It imports recipe_library
directly (no HDA PythonModule — the established Edini pattern) and calls it on
the main thread for light ops (scan, setCurrent, read parms) or a QThread
worker for heavy ops (create HDA, capture tree, rebuild).

Layout:
  left   — QTreeWidget: the recipe tree (containers 📁 / leaves 📄)
  middle — node table + param table for the selected leaf
  right  — Notes editor + exposed-parm sliders + rebuild controls

Wired to MainMenuCommon.xml via edini.ui.open_recipe_manager.
"""
from __future__ import annotations

import importlib
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None

# Defensive import — recipe_library is always present (edini package), but keep
# the pattern uniform with the rest of the UI layer.
from edini import recipe_library as rl

# Default root the dashboard scans. The create_recipe_manager tool builds this
# exact node; the user can point the dashboard elsewhere via the toolbar.
DEFAULT_ROOT = "/obj/edini_recipe_manager"

_CATEGORY_CHOICES = ["", "tube", "extrude", "copy", "boolean",
                     "postprocess", "deform", "misc"]


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread for heavy hou operations (avoid freezing the Houdini UI)
# ─────────────────────────────────────────────────────────────────────────────

class RecipeWorker(QtCore.QThread):
    """Run a recipe_library callable off the UI thread, emit the result.

    Mirrors the ReflectWorker / PiUpdateWorker pattern: hou node/parm calls are
    thread-safe in H21, but they can take seconds (creating an HDA, capturing a
    large tree, rebuilding). The QThread keeps the Houdini UI responsive.
    """
    finished_ok = QtCore.Signal(dict)
    failed = QtCore.Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            if isinstance(result, dict) and result.get("success") is False:
                self.failed.emit(result.get("error", "operation failed"))
            else:
                self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 — worker must not crash the thread
            self.failed.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class RecipeManagerWindow(QtWidgets.QMainWindow):
    """Three-pane dashboard for the recipe library."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Recipe Manager")
        self.resize(1400, 850)

        self._root_path = DEFAULT_ROOT
        self._selected_leaf_path: str | None = None  # currently-selected leaf node path
        self._selected_recipe_id: str | None = None  # recipe_id if captured
        self._scan_cache: dict[str, Any] | None = None  # last scan result (tree dict)
        self._search_text = ""

        # Theme
        try:
            from edini.ui.theme import apply_theme
            apply_theme(self)
        except Exception:
            pass

        self._build_ui()
        self._bind_events()
        self._bootstrap()

    # ── construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Toolbar ─────────────────────────────────────────────────────────
        tb = QtWidgets.QToolBar("main")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(16, 16))
        # Show text on tool buttons (emoji icons don't render reliably across
        # platforms; the Chinese labels are the primary identifier).
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)

        self.act_scan = QtGui.QAction("扫描刷新", self)
        self.act_scan.setToolTip("重新扫描配方树")
        tb.addAction(self.act_scan)

        tb.addWidget(QtWidgets.QLabel(" 根节点: "))
        self.input_root = QtWidgets.QLineEdit(self._root_path)
        self.input_root.setFixedWidth(240)
        tb.addWidget(self.input_root)

        self.act_set_root = QtGui.QAction("应用", self)
        tb.addAction(self.act_set_root)

        tb.addSeparator()
        tb.addWidget(QtWidgets.QLabel(" 搜索: "))
        self.input_search = QtWidgets.QLineEdit()
        self.input_search.setPlaceholderText("过滤配方...")
        self.input_search.setFixedWidth(160)
        tb.addWidget(self.input_search)

        tb.addSeparator()
        self.act_capture_sel = QtGui.QAction("捕获选中", self)
        self.act_capture_sel.setToolTip("捕获当前选中的 subnet 为配方")
        tb.addAction(self.act_capture_sel)
        self.act_new_cat = QtGui.QAction("新建分类", self)
        tb.addAction(self.act_new_cat)
        self.act_create_hda = QtGui.QAction("建主 HDA", self)
        self.act_create_hda.setToolTip("一键创建 edini_recipe_manager HDA")
        tb.addAction(self.act_create_hda)

        # ── Three-pane splitter ─────────────────────────────────────────────
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left: recipe tree
        left = QtWidgets.QWidget()
        left_lay = QtWidgets.QVBoxLayout(left)
        left_lay.setContentsMargins(6, 6, 6, 6)
        self.lbl_stats = QtWidgets.QLabel("—")
        self.lbl_stats.setStyleSheet("color:#6a6e76; padding:2px;")
        left_lay.addWidget(self.lbl_stats)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["配方", "类型", "节点", "状态"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setUniformRowHeights(True)
        left_lay.addWidget(self.tree, 1)
        splitter.addWidget(left)

        # Middle: node table + param table
        mid = QtWidgets.QWidget()
        mid_lay = QtWidgets.QVBoxLayout(mid)
        mid_lay.setContentsMargins(6, 6, 6, 6)
        mid_lay.addWidget(QtWidgets.QLabel("内部节点"))
        self.table_nodes = QtWidgets.QTableWidget(0, 4)
        self.table_nodes.setHorizontalHeaderLabels(["节点", "类型", "输入", "改过参数"])
        self.table_nodes.horizontalHeader().setStretchLastSection(True)
        self.table_nodes.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_nodes.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        mid_lay.addWidget(self.table_nodes, 1)
        mid_lay.addWidget(QtWidgets.QLabel("选中节点的参数 (改过的)"))
        self.table_params = QtWidgets.QTableWidget(0, 3)
        self.table_params.setHorizontalHeaderLabels(["参数", "值", "标记"])
        self.table_params.horizontalHeader().setStretchLastSection(True)
        self.table_params.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        mid_lay.addWidget(self.table_params, 1)
        splitter.addWidget(mid)

        # Right: Notes + exposed parms + rebuild
        right = QtWidgets.QWidget()
        right_lay = QtWidgets.QVBoxLayout(right)
        right_lay.setContentsMargins(6, 6, 6, 6)

        gb_notes = QtWidgets.QGroupBox("配方信息")
        nl = QtWidgets.QVBoxLayout(gb_notes)
        nl.addWidget(QtWidgets.QLabel("Notes"))
        self.edit_notes = QtWidgets.QPlainTextEdit()
        self.edit_notes.setMaximumHeight(140)
        nl.addWidget(self.edit_notes)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(QtWidgets.QLabel("分类:"))
        self.combo_category = QtWidgets.QComboBox()
        self.combo_category.addItems(_CATEGORY_CHOICES)
        hl.addWidget(self.combo_category, 1)
        self.btn_save_notes = QtWidgets.QPushButton("保存 Notes")
        self.btn_save_notes.setObjectName("PrimaryButton")
        hl.addWidget(self.btn_save_notes)
        nl.addLayout(hl)
        right_lay.addWidget(gb_notes)

        gb_exposed = QtWidgets.QGroupBox("暴露参数 (exposed_parms)")
        self.exposed_layout = QtWidgets.QVBoxLayout(gb_exposed)
        self.exposed_layout.addWidget(QtWidgets.QLabel("（选中配方后显示可调参数）"))
        right_lay.addWidget(gb_exposed, 1)

        gb_rebuild = QtWidgets.QGroupBox("重建")
        rl_lay = QtWidgets.QVBoxLayout(gb_rebuild)
        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("目标父节点:"))
        self.input_parent = QtWidgets.QLineEdit("/obj")
        r1.addWidget(self.input_parent, 1)
        rl_lay.addLayout(r1)
        r2 = QtWidgets.QHBoxLayout()
        r2.addWidget(QtWidgets.QLabel("实例名:"))
        self.input_name = QtWidgets.QLineEdit()
        self.input_name.setPlaceholderText("留空=自动")
        r2.addWidget(self.input_name, 1)
        self.btn_rebuild = QtWidgets.QPushButton("重建配方")
        self.btn_rebuild.setObjectName("PrimaryButton")
        r2.addWidget(self.btn_rebuild)
        rl_lay.addLayout(r2)
        right_lay.addWidget(gb_rebuild)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

        self.setCentralWidget(splitter)
        self.setStatusBar(QtWidgets.QStatusBar())

    def _bind_events(self):
        self.act_scan.triggered.connect(self.refresh_tree)
        self.act_set_root.triggered.connect(self._on_apply_root)
        self.act_capture_sel.triggered.connect(self._on_capture_selected)
        self.act_new_cat.triggered.connect(self._on_new_category)
        self.act_create_hda.triggered.connect(self._on_create_hda)
        self.input_search.textChanged.connect(self._on_search_changed)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.table_nodes.itemSelectionChanged.connect(self._on_node_row_selected)
        self.btn_save_notes.clicked.connect(self._on_save_notes)
        self.btn_rebuild.clicked.connect(self._on_rebuild)

        # Auto-refresh on a timer (mirrors main_window's 1500ms scene poll).
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh_tree)
        self._timer.start()

    def _bootstrap(self):
        # Initial scan on the next event-loop tick so the window shows first.
        QtCore.QTimer.singleShot(0, self.refresh_tree)

    # ── tree population (left pane) ────────────────────────────────────────

    def refresh_tree(self):
        """Scan the root and rebuild the QTreeWidget (read-only, main thread)."""
        if hou is None:
            self.lbl_stats.setText("Houdini 不可用")
            return
        result = rl.scan_recipe_tree(self._root_path)
        if not result.get("success"):
            self.lbl_stats.setText(result.get("error", "扫描失败"))
            self.tree.clear()
            self._scan_cache = None
            return
        self._scan_cache = result["tree"]
        self._populate_tree(self._scan_cache)
        leaves = self._count_leaves(self._scan_cache)
        self.lbl_stats.setText(f"{leaves} 配方 · 扫描于 {self._now()}")
        self.statusBar().showMessage(f"扫描完成: {leaves} 个配方", 2000)

    def _populate_tree(self, node_dict: dict, parent_item=None):
        """Recursively fill the QTreeWidget from a scan_recipe_tree result.

        Only top-level rebuild when the root is passed (parent_item=None); for
        children we recurse into the parent item.
        """
        if parent_item is None:
            self.tree.clear()
            # The root itself: create a top-level item, then recurse children.
            if node_dict.get("type") == "container":
                root_item = self._make_tree_item(node_dict, is_root=True)
                self.tree.addTopLevelItem(root_item)
                self._add_children(node_dict, root_item)
                root_item.setExpanded(True)
            else:
                # root is a leaf or missing — show as single row
                self.tree.addTopLevelItem(self._make_tree_item(node_dict))
        else:
            self._add_children(node_dict, parent_item)

    def _add_children(self, node_dict: dict, parent_item: QtWidgets.QTreeWidgetItem):
        for child in node_dict.get("children", []):
            if not self._matches_search(child):
                # Still add containers (they may contain matching leaves), but
                # we prune non-matching leaves. Simpler: add all, let the search
                # just expand matches — but to keep it responsive we add all.
                pass
            item = self._make_tree_item(child)
            parent_item.addChild(item)
            if child.get("type") == "container":
                self._add_children(child, item)

    def _make_tree_item(self, node_dict: dict, is_root=False) -> QtWidgets.QTreeWidgetItem:
        ntype = node_dict.get("type", "ignored")
        # ASCII markers (emoji rendering is unreliable in Houdini's Qt build).
        icon = "[HDA]" if is_root else ("[+]" if ntype == "container" else "[*]")
        name = node_dict.get("name", "?")
        # Search filter: hide non-matching leaves by greying (we keep them so
        # the tree structure stays intact, but dim them).
        matches = self._node_matches_search(node_dict)
        label = f"{icon} {name}" if matches else f"{icon} {name}"
        item = QtWidgets.QTreeWidgetItem([label, ntype, "", ""])
        item.setData(0, QtCore.Qt.UserRole, node_dict.get("path", ""))
        item.setData(0, QtCore.Qt.UserRole + 1, ntype)
        if ntype == "leaf":
            item.setText(2, str(node_dict.get("node_count", "")))
            item.setText(3, node_dict.get("category", ""))
            if not matches and self._search_text:
                # dim non-matching
                f = item.foreground(0)
                f.setColor(QtGui.QColor("#3a3a4a"))
                for c in range(4):
                    item.setForeground(c, f)
        return item

    def _node_matches_search(self, node_dict: dict) -> bool:
        if not self._search_text:
            return True
        q = self._search_text.lower()
        hay = " ".join([
            node_dict.get("name", ""),
            node_dict.get("notes", ""),
            node_dict.get("category", ""),
            node_dict.get("kind", ""),
        ]).lower()
        return q in hay

    def _matches_search(self, node_dict: dict) -> bool:
        return self._node_matches_search(node_dict)

    def _count_leaves(self, node_dict: dict) -> int:
        n = 0
        if node_dict.get("type") == "leaf":
            n += 1
        for c in node_dict.get("children", []):
            n += self._count_leaves(c)
        return n

    # ── selection handling ─────────────────────────────────────────────────

    def _on_tree_selection(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        path = item.data(0, QtCore.Qt.UserRole)
        ntype = item.data(0, QtCore.Qt.UserRole + 1)
        if not path or ntype != "leaf":
            self._selected_leaf_path = None
            self._clear_middle()
            self._clear_right()
            return
        self._selected_leaf_path = path
        self._load_leaf(path)

    def _on_tree_double_click(self, item, _column):
        """Dive into the selected node in Houdini (setCurrent)."""
        path = item.data(0, QtCore.Qt.UserRole)
        if path and hou is not None:
            try:
                node = hou.node(path)
                if node:
                    node.setCurrent(True, clear_all_selected=True)
                    self.statusBar().showMessage(f"已跳转: {path}", 1800)
            except Exception:
                pass

    def _on_tree_context_menu(self, pos):
        """Right-click context menu: new sub-category / new recipe / rename / delete."""
        if hou is None:
            return
        item = self.tree.itemAt(pos)
        menu = QtWidgets.QMenu(self)

        target_path = self._root_path
        target_type = "container"
        if item is not None:
            target_path = item.data(0, QtCore.Qt.UserRole) or self._root_path
            target_type = item.data(0, QtCore.Qt.UserRole + 1) or "container"

        # Actions differ by type
        if target_type == "container":
            act_new_cat = menu.addAction("新建子分类")
            act_new_recipe = menu.addAction("新建配方 (空 subnet)")
            menu.addSeparator()
            act_rename = menu.addAction("重命名")
            act_delete = menu.addAction("删除")
        else:  # leaf
            act_capture = menu.addAction("捕获为配方")
            act_rebuild = menu.addAction("重建...")
            menu.addSeparator()
            act_dive = menu.addAction("进入编辑")
            act_rename = menu.addAction("重命名")
            act_delete = menu.addAction("删除")

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action is None:
            return

        try:
            parent = hou.node(target_path)
            if parent is None:
                return
            if target_type == "container":
                if action == act_new_cat:
                    self._ctx_new_node(parent, "subnet", "新分类", cat=True)
                elif action == act_new_recipe:
                    self._ctx_new_node(parent, "subnet", "新配方", cat=False)
                elif action == act_rename:
                    self._ctx_rename(parent)
                elif action == act_delete:
                    self._ctx_delete(parent)
            else:
                if action == act_capture:
                    worker = RecipeWorker(rl.recipe_capture, target_path)
                    worker.finished_ok.connect(lambda r: self.refresh_tree())
                    worker.failed.connect(lambda e: self.statusBar().showMessage(
                        f"捕获失败: {e}", 3000))
                    worker.start()
                    self._active_worker = worker
                elif action == act_rebuild:
                    self.input_parent.setText(parent.parent().path() if parent.parent() else "/obj")
                    self._on_rebuild()
                elif action == act_dive:
                    parent.setCurrent(True, clear_all_selected=True)
                elif action == act_rename:
                    self._ctx_rename(parent)
                elif action == act_delete:
                    self._ctx_delete(parent)
        except Exception as e:
            self.statusBar().showMessage(f"操作失败: {e}", 3000)

    def _ctx_new_node(self, parent, ntype, default_name, cat=False):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建", "名称:", text=default_name)
        if not ok or not name.strip():
            return
        name = name.strip()
        node = parent.createNode(ntype, name)
        if cat:
            node.setComment("分类容器")
        parent.layoutChildren()
        self.statusBar().showMessage(f"已创建: {node.path()}", 2000)
        self.refresh_tree()

    def _ctx_rename(self, node):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "重命名", "新名称:", text=node.name())
        if not ok or not name.strip():
            return
        node.setName(name.strip())
        self.statusBar().showMessage(f"已重命名: {node.path()}", 2000)
        self.refresh_tree()

    def _ctx_delete(self, node):
        confirm = QtWidgets.QMessageBox.question(
            self, "删除", f"确认删除 {node.path()}？\n（内部节点会一起删除）",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if confirm == QtWidgets.QMessageBox.Yes:
            node.destroy()
            self.statusBar().showMessage("已删除", 2000)
            self.refresh_tree()

    # ── middle pane: node table + param table ──────────────────────────────

    def _load_leaf(self, leaf_path: str):
        """Load a leaf's internal nodes into the middle tables.

        Reads the live subnet's children directly (fast, no recipe.json needed)
        so the view reflects the current scene state.
        """
        self._clear_middle()
        if hou is None:
            return
        try:
            leaf = hou.node(leaf_path)
            if leaf is None:
                return
            kids = [c for c in leaf.children() if not rl._is_ignored_node(c)]
            self.table_nodes.setRowCount(len(kids))
            for row, c in enumerate(kids):
                # count changed params: compare to manifest default (best-effort)
                changed_n = self._count_changed_params(c)
                inputs = ",".join(str(i) for i, src in enumerate(c.inputs())
                                  if src is not None) or "—"
                self.table_nodes.setItem(row, 0, QtWidgets.QTableWidgetItem(c.name()))
                self.table_nodes.setItem(row, 1, QtWidgets.QTableWidgetItem(c.type().name()))
                self.table_nodes.setItem(row, 2, QtWidgets.QTableWidgetItem(inputs))
                self.table_nodes.setItem(row, 3, QtWidgets.QTableWidgetItem(str(changed_n)))
                self.table_nodes.item(row, 0).setData(QtCore.Qt.UserRole, leaf_path + "/" + c.name())
            # Load notes into the right pane too.
            self.edit_notes.setPlainText(leaf.comment() or "")
        except Exception:
            pass

    def _count_changed_params(self, node) -> int:
        """Best-effort count of non-default params for display (heuristic)."""
        try:
            manifest = rl._load_manifest()
            defs = rl._manifest_defaults(node.type().name(), manifest)
            n = 0
            for p in node.parms():
                if rl._is_auto_param(p.name()):
                    continue
                live = rl._json_safe(p.eval())
                default = rl._manifest_lookup(p.name(), defs)
                if default is not None and not rl._values_equal(live, default):
                    n += 1
            return n
        except Exception:
            return 0

    def _on_node_row_selected(self):
        rows = self.table_nodes.selectionModel().selectedRows()
        if not rows or hou is None:
            return
        row = rows[0].row()
        node_path = self.table_nodes.item(row, 0).data(QtCore.Qt.UserRole)
        self._load_node_params(node_path)

    def _load_node_params(self, node_path: str):
        self.table_params.setRowCount(0)
        try:
            node = hou.node(node_path)
            if node is None:
                return
            manifest = rl._load_manifest()
            defs = rl._manifest_defaults(node.type().name(), manifest)
            marked = set()  # no notes-level marked here; per-leaf only
            changed, marked_d, _expr, _warns = rl._classify_parms(
                node, node.type().name(), defs, marked,
                manifest is not None)
            rows = list(changed.items()) + list(marked_d.items())
            self.table_params.setRowCount(len(rows))
            for i, (pname, val) in enumerate(rows):
                self.table_params.setItem(i, 0, QtWidgets.QTableWidgetItem(pname))
                self.table_params.setItem(i, 1, QtWidgets.QTableWidgetItem(str(val)[:60]))
                self.table_params.setItem(i, 2, QtWidgets.QTableWidgetItem(
                    "★" if pname in marked_d else ""))
        except Exception:
            pass

    def _clear_middle(self):
        self.table_nodes.setRowCount(0)
        self.table_params.setRowCount(0)

    def _clear_right(self):
        self.edit_notes.clear()
        self.combo_category.setCurrentIndex(0)
        self._clear_exposed()

    # ── right pane: exposed parms + Notes + rebuild ────────────────────────

    def _clear_exposed(self):
        while self.exposed_layout.count():
            w = self.exposed_layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.exposed_layout.addWidget(QtWidgets.QLabel("（选中配方后显示可调参数）"))

    def _on_save_notes(self):
        if not self._selected_leaf_path or hou is None:
            return
        notes = self.edit_notes.toPlainText()
        # Run on a worker so a slow setComment (rare) doesn't block.
        worker = RecipeWorker(rl.set_node_notes, self._selected_leaf_path, notes)
        worker.finished_ok.connect(lambda r: self.statusBar().showMessage(
            f"Notes 已保存: {self._selected_leaf_path}", 2000))
        worker.failed.connect(lambda e: self.statusBar().showMessage(
            f"保存失败: {e}", 3000))
        worker.start()
        self._active_worker = worker  # keep ref

    def _on_rebuild(self):
        if not self._selected_leaf_path:
            self.statusBar().showMessage("先选中一个配方", 2000)
            return
        # recipe_rebuild needs a recipe_id. The leaf may or may not be captured
        # yet. Best path: capture it first (writes recipe.json), then rebuild.
        leaf_path = self._selected_leaf_path
        parent = self.input_parent.text().strip() or "/obj"
        name = self.input_name.text().strip() or None

        def _capture_then_rebuild():
            cap = rl.recipe_capture(leaf_path)
            if not cap.get("success"):
                return cap
            rid = cap["recipe_id"]
            return rl.recipe_rebuild(rid, parent, name=name)

        self.btn_rebuild.setEnabled(False)
        self.statusBar().showMessage("重建中...", 0)
        worker = RecipeWorker(_capture_then_rebuild)
        worker.finished_ok.connect(self._on_rebuild_done)
        worker.failed.connect(self._on_rebuild_failed)
        worker.start()
        self._active_worker = worker

    def _on_rebuild_done(self, result: dict):
        self.btn_rebuild.setEnabled(True)
        ok = result.get("success")
        verify = result.get("verify", {})
        path = result.get("rebuilt_path", "?")
        if ok and verify.get("ok", True):
            self.statusBar().showMessage(
                f"重建成功: {path} ({result.get('node_count',0)} 节点)", 4000)
        else:
            mism = verify.get("mismatches", [])[:2]
            self.statusBar().showMessage(
                f"重建完成但有差异: {path} — {mism}", 5000)

    def _on_rebuild_failed(self, err: str):
        self.btn_rebuild.setEnabled(True)
        self.statusBar().showMessage(f"重建失败: {err}", 5000)

    # ── toolbar actions ────────────────────────────────────────────────────

    def _on_apply_root(self):
        new_root = self.input_root.text().strip()
        if new_root:
            self._root_path = new_root
            self.refresh_tree()

    def _on_search_changed(self, text):
        self._search_text = text.strip()
        if self._scan_cache is not None:
            self._populate_tree(self._scan_cache)

    def _on_capture_selected(self):
        if hou is None:
            return
        sel = hou.selectedNodes()
        if not sel:
            self.statusBar().showMessage("没有选中节点", 2000)
            return
        path = sel[0].path()
        self.statusBar().showMessage(f"捕获中: {path}...", 0)
        worker = RecipeWorker(rl.recipe_capture, path)
        worker.finished_ok.connect(lambda r: self._on_capture_done(r, path))
        worker.failed.connect(lambda e: self.statusBar().showMessage(
            f"捕获失败: {e}", 3000))
        worker.start()
        self._active_worker = worker

    def _on_capture_done(self, result: dict, path: str):
        n = result.get("node_count", "?")
        self.statusBar().showMessage(f"已捕获: {path} ({n} 节点)", 3000)
        self.refresh_tree()

    def _on_new_category(self):
        if hou is None or not self._root_path:
            return
        # Create a subnet under the root (or selected container) as a category.
        parent_path = self._selected_container_path() or self._root_path
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建分类", "分类名:", text="new_category")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            parent = hou.node(parent_path)
            if parent is None:
                return
            cat = parent.createNode("subnet", name)
            cat.setComment("分类容器")
            parent.layoutChildren()
            self.statusBar().showMessage(f"已建分类: {cat.path()}", 2000)
            self.refresh_tree()
        except Exception as e:
            self.statusBar().showMessage(f"创建失败: {e}", 3000)

    def _selected_container_path(self) -> str | None:
        """Return the path of the selected tree item if it's a container."""
        items = self.tree.selectedItems()
        if not items:
            return None
        item = items[0]
        if item.data(0, QtCore.Qt.UserRole + 1) == "container":
            return item.data(0, QtCore.Qt.UserRole)
        return None

    def _on_create_hda(self):
        self.statusBar().showMessage("创建主 HDA...", 0)
        worker = RecipeWorker(rl.create_recipe_manager)
        worker.finished_ok.connect(self._on_hda_created)
        worker.failed.connect(lambda e: self.statusBar().showMessage(
            f"创建失败: {e}", 4000))
        worker.start()
        self._active_worker = worker

    def _on_hda_created(self, result: dict):
        path = result.get("hda_path", DEFAULT_ROOT)
        self._root_path = path
        self.input_root.setText(path)
        self.statusBar().showMessage(f"已创建: {path}", 3000)
        self.refresh_tree()

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.now().strftime("%H:%M:%S")

    def closeEvent(self, event):
        # Release the singleton so reopen creates a fresh window.
        try:
            import edini.ui.windows as wm
            if wm._recipe_manager_window is self:
                wm._recipe_manager_window = None
        except Exception:
            pass
        super().closeEvent(event)
