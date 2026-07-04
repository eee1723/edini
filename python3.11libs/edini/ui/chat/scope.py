"""ScopeConfig — describes a chat window's scope identity.

THE single legal place to express differences between windows.
Components read config fields but NEVER branch on `scope_id` string.
(Enforced by tests/test_scope_discipline.py in Stage 6.)

Schema for scene_data_provider's returned dict (spec §5.2):
    {hip, path, selected, nodes, node_type?, params_summary?}  — None → "—"
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScopeConfig:
    scope_id: str                              # "agent" | "project_hda"
    window_title: str                          # shown in header
    accent_override: str | None                # None=follow global theme; "#rrggbb"=fixed
    header_badge: str | None                   # small label next to title (e.g. node path)
    left_panel_kind: str                       # "global_sessions" | "node_versions"
    show_change_tree: bool
    show_eval_button: bool
    show_attachment_bar: bool
    show_param_snapshot: bool                  # HDA-only
    scene_data_provider: Callable[[], dict]    # returns scene info dict
