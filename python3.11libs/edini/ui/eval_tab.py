"""EvalDashboard — Evaluation results view for Edini."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from edini.eval.store import EvalStore
from edini.ui.theme import accent_color, fs


# Color constants
COLOR_GREEN = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED = "#ef4444"
COLOR_BG = "#0d0d1a"
COLOR_CARD = "#18182a"
COLOR_TEXT = "#e5e5eb"
COLOR_MUTED = "#71717a"
COLOR_BORDER = "#252540"


def _score_color(score: float) -> str:
    if score >= 0.85:
        return COLOR_GREEN
    elif score >= 0.70:
        return COLOR_YELLOW
    return COLOR_RED


def _score_emoji(score: float) -> str:
    if score >= 0.85:
        return "\U0001f7e2"  # 🟢
    elif score >= 0.70:
        return "\U0001f7e1"  # 🟡
    return "\U0001f534"  # 🔴


_TREND_SYMBOLS = {"improving": "\u2191", "declining": "\u2193", "stable": "\u2192"}
_TREND_COLORS = {"improving": COLOR_GREEN, "declining": COLOR_RED, "stable": COLOR_MUTED}
_EM_DASH = "\u2014"  # — em dash (cannot use \u in f-strings pre-3.12)


class _ScoreCard(QtWidgets.QFrame):
    """A single dimension score card with label, value, and trend arrow."""

    def __init__(self, label: str, score: float | None = None,
                 trend: str = "", parent=None):
        super().__init__(parent)
        self._label_text = label
        self._score = score
        self._trend = trend
        self._build_ui()

    def _build_ui(self):
        self.setFixedSize(150, 80)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(
            f"_ScoreCard {{"
            f"  background: {COLOR_CARD};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 8px;"
            f"  padding: 8px;"
            f"}}"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Label
        label = QtWidgets.QLabel(self._label_text)
        label.setStyleSheet(
            f"color:{COLOR_MUTED};font-size:{fs(9)};border:none;"
        )
        layout.addWidget(label)

        # Score + trend row
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)

        if self._score is not None:
            score_lbl = QtWidgets.QLabel(f"{self._score:.2f}")
            score_lbl.setStyleSheet(
                f"color:{_score_color(self._score)};"
                f"font-size:{fs(14)};font-weight:bold;border:none;"
            )
            row.addWidget(score_lbl)

            if self._trend:
                sym = _TREND_SYMBOLS.get(self._trend, "\u2192")
                tcol = _TREND_COLORS.get(self._trend, COLOR_MUTED)
                trend_lbl = QtWidgets.QLabel(sym)
                trend_lbl.setStyleSheet(
                    f"color:{tcol};font-size:{fs(11)};border:none;"
                )
                row.addWidget(trend_lbl)
        else:
            na = QtWidgets.QLabel("\u2014")
            na.setStyleSheet(
                f"color:{COLOR_MUTED};font-size:{fs(14)};border:none;"
            )
            row.addWidget(na)

        row.addStretch()
        layout.addLayout(row)

    def set_score(self, score: float | None, trend: str = ""):
        self._score = score
        self._trend = trend
        # Rebuild score display
        item = self.layout().itemAt(1)
        if item:
            old_row = item.layout()
            if old_row:
                # Clear old row
                while old_row.count():
                    w = old_row.takeAt(0)
                    if w and w.widget():
                        w.widget().deleteLater()
                # Re-populate
                if self._score is not None:
                    score_lbl = QtWidgets.QLabel(f"{self._score:.2f}")
                    score_lbl.setStyleSheet(
                        f"color:{_score_color(self._score)};"
                        f"font-size:{fs(14)};font-weight:bold;border:none;"
                    )
                    old_row.addWidget(score_lbl)
                    if self._trend:
                        sym = _TREND_SYMBOLS.get(self._trend, "\u2192")
                        tcol = _TREND_COLORS.get(self._trend, COLOR_MUTED)
                        trend_lbl = QtWidgets.QLabel(sym)
                        trend_lbl.setStyleSheet(
                            f"color:{tcol};font-size:{fs(11)};border:none;"
                        )
                        old_row.addWidget(trend_lbl)
                else:
                    na = QtWidgets.QLabel("\u2014")
                    na.setStyleSheet(
                        f"color:{COLOR_MUTED};font-size:{fs(14)};border:none;"
                    )
                    old_row.addWidget(na)
                old_row.addStretch()


class _TrendChart(QtWidgets.QWidget):
    """Custom-painted trend line chart for evaluation scores."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._dimensions = [
            "avg_score", "avg_tool_accuracy", "avg_task_completion",
            "avg_efficiency", "avg_reliability", "avg_cost",
        ]
        self._colors = [
            "#22c55e", "#3b82f6", "#a855f7",
            "#f59e0b", "#ec4899", "#06b6d4",
        ]
        self._visible = {d: True for d in self._dimensions}
        self.setMinimumHeight(200)

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):  # noqa: N802
        if not self._data:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 40

        chart_w = w - margin * 2
        chart_h = h - margin * 2

        painter.fillRect(0, 0, w, h, QtGui.QColor(COLOR_BG))

        if chart_w <= 0 or chart_h <= 0 or len(self._data) < 2:
            painter.setPen(QtGui.QColor(COLOR_MUTED))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter, "Not enough data"
            )
            painter.end()
            return

        step_x = chart_w / (len(self._data) - 1)

        for di, dim in enumerate(self._dimensions):
            if not self._visible.get(dim, True):
                continue

            values = [
                d[dim] for d in self._data
                if d.get(dim) is not None
            ]
            if len(values) < 2:
                continue

            min_v = min(values)
            max_v = max(values)
            diff = max(0.01, max_v - min_v)

            color = QtGui.QColor(self._colors[di % len(self._colors)])
            pen = QtGui.QPen(color, 2)
            painter.setPen(pen)

            path = QtGui.QPainterPath()
            first = True
            for i, d in enumerate(self._data):
                val = d.get(dim)
                if val is None:
                    continue
                x = margin + i * step_x
                y = margin + chart_h - ((val - min_v) / diff) * chart_h
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)

            painter.drawPath(path)

        painter.end()

    def toggle_dimension(self, dim: str, visible: bool):
        if dim in self._visible:
            self._visible[dim] = visible
            self.update()


class EvalTab(QtWidgets.QWidget):
    """Evaluation dashboard tab — overview cards + trend chart + session list."""

    navigate_to_session = QtCore.Signal(str)

    def __init__(self, store: EvalStore | None = None, parent=None):
        super().__init__(parent)
        self._store = store or EvalStore()
        self._filter_dimension: str | None = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background:{COLOR_BG};")
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ── Title ──
        title = QtWidgets.QLabel("\U0001f4ca Agent Evaluation Dashboard")
        title.setStyleSheet(
            f"color:{COLOR_TEXT};font-size:{fs(14)};"
            f"font-weight:bold;border:none;"
        )
        main_layout.addWidget(title)

        # ── ① Summary Cards ──
        self._cards_layout = QtWidgets.QHBoxLayout()
        self._cards_layout.setSpacing(8)

        self._dim_labels = [
            ("total", "Total"),
            ("tool_accuracy", "Tool Acc"),
            ("task_completion", "Task Comp"),
            ("efficiency", "Efficiency"),
            ("reliability", "Reliability"),
            ("cost", "Cost"),
        ]
        self._card_widgets: dict[str, _ScoreCard] = {}

        for dim_key, label in self._dim_labels:
            card = _ScoreCard(label)
            self._card_widgets[dim_key] = card
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        main_layout.addLayout(self._cards_layout)

        # ── ② Trend Chart ──
        chart_section = QtWidgets.QVBoxLayout()
        chart_section.setSpacing(4)

        chart_header = QtWidgets.QHBoxLayout()
        chart_label = QtWidgets.QLabel("Trend")
        chart_label.setStyleSheet(
            f"color:{COLOR_TEXT};font-size:{fs(11)};"
            f"font-weight:bold;border:none;"
        )
        chart_header.addWidget(chart_label)
        chart_header.addStretch()

        for days, lbl in [(7, "7d"), (14, "14d"), (30, "30d")]:
            btn = QtWidgets.QPushButton(lbl)
            btn.setFixedSize(36, 22)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  color:{COLOR_MUTED};background:{COLOR_CARD};"
                f"  border:1px solid {COLOR_BORDER};"
                f"  border-radius:4px;font-size:{fs(9)};"
                f"}}"
                f"QPushButton:hover {{"
                f"  color:{COLOR_TEXT};border-color:{accent_color()};"
                f"}}"
            )
            btn.clicked.connect(
                lambda checked, d=days, b=btn: self._load_trend(d)
            )
            chart_header.addWidget(btn)

        chart_section.addLayout(chart_header)

        self._trend_chart = _TrendChart()
        chart_section.addWidget(self._trend_chart)
        main_layout.addLayout(chart_section)

        # ── ③ Session List ──
        list_section = QtWidgets.QVBoxLayout()
        list_section.setSpacing(4)

        list_header = QtWidgets.QHBoxLayout()
        list_label = QtWidgets.QLabel("Sessions")
        list_label.setStyleSheet(
            f"color:{COLOR_TEXT};font-size:{fs(11)};"
            f"font-weight:bold;border:none;"
        )
        list_header.addWidget(list_label)
        list_header.addStretch()

        refresh_btn = QtWidgets.QPushButton("\U0001f504 Refresh")
        refresh_btn.setStyleSheet(
            f"QPushButton {{"
            f"  color:{COLOR_MUTED};background:{COLOR_CARD};"
            f"  border:1px solid {COLOR_BORDER};"
            f"  border-radius:4px;padding:3px 8px;font-size:{fs(9)};"
            f"}}"
            f"QPushButton:hover {{"
            f"  color:{COLOR_TEXT};border-color:{accent_color()};"
            f"}}"
        )
        refresh_btn.clicked.connect(self._load_data)
        list_header.addWidget(refresh_btn)

        list_section.addLayout(list_header)

        self._session_table = QtWidgets.QTableWidget()
        self._session_table.setColumnCount(5)
        self._session_table.setHorizontalHeaderLabels(
            ["", "Score", "Date", "Title", "Calls"]
        )
        self._session_table.setAlternatingRowColors(True)
        self._session_table.horizontalHeader().setStretchLastSection(True)
        self._session_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self._session_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        self._session_table.verticalHeader().setVisible(False)
        self._session_table.setShowGrid(False)
        self._session_table.setStyleSheet(
            f"QTableWidget {{"
            f"  background:{COLOR_BG};color:{COLOR_TEXT};"
            f"  font-size:{fs(10)};"
            f"  border:1px solid {COLOR_BORDER};border-radius:4px;"
            f"  alternate-background-color:{COLOR_CARD};"
            f"}}"
            f"QTableWidget::item {{ padding: 4px 8px; border: none; }}"
            f"QTableWidget::item:selected {{"
            f"  background:{COLOR_CARD}; color:{accent_color()};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{COLOR_CARD};color:{COLOR_MUTED};"
            f"  border:none;border-bottom:1px solid {COLOR_BORDER};"
            f"  padding:4px 8px;font-size:{fs(9)};"
            f"}}"
        )
        self._session_table.itemClicked.connect(self._on_session_clicked)
        self._session_table.itemDoubleClicked.connect(
            self._on_session_double_clicked
        )
        list_section.addWidget(self._session_table)

        main_layout.addLayout(list_section, 1)

    def _load_data(self):
        """Load latest data from store."""
        self._load_summary()
        self._load_trend(14)
        self._load_session_list()

    def _load_summary(self):
        """Update score cards with recent averages."""
        recent = self._store.get_recent_sessions(limit=7)
        if not recent:
            for key in self._card_widgets:
                self._card_widgets[key].set_score(None)
            return

        # Compare with previous 7 for trend
        prev = self._store.get_recent_sessions(limit=14)
        mid = len(prev) // 2

        dim_keys = [
            "total_score", "tool_accuracy", "task_completion",
            "efficiency", "reliability", "cost",
        ]

        for i, (dim_key, _) in enumerate(self._dim_labels):
            scores = [
                s.get(dim_keys[i]) for s in recent
                if s.get(dim_keys[i]) is not None
            ]
            avg = sum(scores) / len(scores) if scores else None

            trend = ""
            if mid > 0 and len(prev) > mid:
                recent_scores = [
                    s.get(dim_keys[i]) for s in prev[:mid]
                    if s.get(dim_keys[i]) is not None
                ]
                prev_scores = [
                    s.get(dim_keys[i]) for s in prev[mid:]
                    if s.get(dim_keys[i]) is not None
                ]
                if recent_scores and prev_scores:
                    r_avg = sum(recent_scores) / len(recent_scores)
                    p_avg = sum(prev_scores) / len(prev_scores)
                    diff = r_avg - p_avg
                    if diff > 0.03:
                        trend = "improving"
                    elif diff < -0.03:
                        trend = "declining"
                    else:
                        trend = "stable"

            if dim_key in self._card_widgets:
                self._card_widgets[dim_key].set_score(avg, trend)

    def _load_trend(self, days: int = 14):
        """Update trend chart."""
        data = self._store.get_daily_trend(days=days)
        self._trend_chart.set_data(data)

    def _load_session_list(self):
        """Populate session table."""
        if self._filter_dimension:
            sessions = self._store.get_bottom_sessions(
                limit=50, dimension=self._filter_dimension
            )
        else:
            sessions = self._store.get_recent_sessions(limit=50)

        self._session_table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            score = s.get("total_score") or 0.0

            # Quality dot
            dot = QtWidgets.QLabel(_score_emoji(score))
            dot.setStyleSheet("border:none;")
            self._session_table.setCellWidget(row, 0, dot)

            # Score
            score_item = QtWidgets.QTableWidgetItem(f"{score:.2f}")
            score_item.setForeground(QtGui.QColor(_score_color(score)))
            self._session_table.setItem(row, 1, score_item)

            # Date
            date_str = (s.get("evaluated_at") or "")[:10]
            self._session_table.setItem(
                row, 2, QtWidgets.QTableWidgetItem(date_str)
            )

            # Title / session_id
            sid = s.get("session_id", "")
            title_item = QtWidgets.QTableWidgetItem(sid[:40])
            title_item.setToolTip(sid)
            self._session_table.setItem(row, 3, title_item)

            # Call count
            cnt_item = QtWidgets.QTableWidgetItem(
                str(s.get("tool_calls_count", 0))
            )
            cnt_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self._session_table.setItem(row, 4, cnt_item)

        self._session_table.resizeColumnsToContents()

    def _on_session_clicked(self, item):
        """Single click — show detail tooltip."""
        row = item.row()
        sid_item = self._session_table.item(row, 3)
        if not sid_item:
            return
        sid = sid_item.toolTip() or sid_item.text()
        detail = self._store.get_session_detail(sid)
        if not detail:
            return
        s = detail["session"]
        parts = [
            f"Total: {s.get('total_score', _EM_DASH)}",
            f"Tool: {s.get('tool_accuracy', _EM_DASH)}",
            f"Task: {s.get('task_completion', _EM_DASH)}",
            f"Eff: {s.get('efficiency', _EM_DASH)}",
            f"Rel: {s.get('reliability', _EM_DASH)}",
            f"Cost: {s.get('cost', _EM_DASH)}",
        ]
        if detail.get("judge_logs"):
            for jl in detail["judge_logs"][:2]:
                resp = jl.get("response", "")[:80]
                parts.append(
                    f"Judge [{jl['dimension']}]: {resp}"
                )
        QtWidgets.QToolTip.showText(
            QtGui.QCursor.pos(), "\n".join(parts)
        )

    def _on_session_double_clicked(self, item):
        """Double click — navigate to session browsing mode."""
        row = item.row()
        sid_item = self._session_table.item(row, 3)
        if sid_item:
            sid = sid_item.toolTip() or sid_item.text()
            self.navigate_to_session.emit(sid)

    def refresh(self):
        """Public method to refresh dashboard data."""
        self._load_data()
