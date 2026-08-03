"""Project-type workflow definitions shared by API, agents and stage gates."""

from __future__ import annotations

from typing import Final

PROJECT_TYPES: Final[tuple[str, ...]] = ("software", "embedded", "hybrid")
WORKFLOW_VERSION: Final[str] = "phase2.v1"

WORKFLOW_STAGES: Final[dict[str, tuple[str, ...]]] = {
    "software": (
        "problem_discovery", "market_research", "product_definition",
        "solution_design", "development", "testing", "iteration",
    ),
    "embedded": (
        "problem_discovery", "market_research", "product_definition",
        "hardware_design", "procurement", "maker", "firmware",
        "hardware_testing", "iteration",
    ),
    "hybrid": (
        "problem_discovery", "market_research", "product_definition",
        "solution_design", "protocol_design", "development", "testing",
        "hardware_design", "procurement", "maker", "firmware",
        "hardware_testing", "integration_testing", "iteration",
    ),
}

WORKFLOW_LABELS: Final[dict[str, str]] = {
    "software": "纯软件",
    "embedded": "嵌入式",
    "hybrid": "软硬件混合",
}

# Compatibility aliases found in pre-Phase-2 project files and Agent route
# metadata. New persistence and user-facing labels use canonical keys.
LEGACY_STAGE_ALIASES: Final[dict[str, str]] = {
    "discovery": "problem_discovery",
    "planning": "product_definition",
    "learning": "iteration",
    "hardware_development": "hardware_design",
}

# Hybrid projects share discovery/research/decision stages, then work in
# independent tracks. ``stages_for`` is the durable compatibility projection
# used by clients that persist one current stage; tracks expose the
# authoritative parallel-work view without dropping any hardware stage.
WORKFLOW_TRACKS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "software": {"software": WORKFLOW_STAGES["software"]},
    "embedded": {"hardware": WORKFLOW_STAGES["embedded"]},
    "hybrid": {
        # After the shared decision stage these tracks are independently
        # actionable. The linear WORKFLOW_STAGES entry above remains available
        # to clients that can only persist one current_stage value.
        "software": ("development", "testing"),
        "hardware": ("hardware_design", "procurement", "maker", "firmware", "hardware_testing"),
        "protocol": ("protocol_design",),
        "integration": ("integration_testing",),
    },
}


def stages_for(project_type: str) -> tuple[str, ...]:
    """Return a validated workflow stage sequence."""
    return WORKFLOW_STAGES.get(project_type, WORKFLOW_STAGES["software"])


def normalize_stage(stage: str, project_type: str = "software") -> str:
    """Normalize legacy stage names without changing new workflow semantics."""
    candidate = LEGACY_STAGE_ALIASES.get(stage, stage)
    if candidate not in stages_for(project_type) and stage == "hardware_development":
        candidate = "hardware_design" if project_type in {"embedded", "hybrid"} else "development"
    return candidate


def tracks_for(project_type: str) -> dict[str, tuple[str, ...]]:
    """Return parallel work tracks for a project type."""
    return WORKFLOW_TRACKS.get(project_type, WORKFLOW_TRACKS["software"])


def classify_project_type(*, goal: str = "", description: str = "", evidence: str = "") -> dict[str, str]:
    """Classify a project conservatively from user-visible discovery signals.

    This is a proposal only. The caller must persist it as unconfirmed until
    the user accepts the project type.
    """
    text = " ".join((goal, description, evidence)).lower()
    hardware_terms = ("esp32", "arduino", "stm32", "固件", "开发板", "传感器", "串口", "接线", "电路", "硬件")
    software_terms = ("网站", "网页", "应用", "app", "软件", "后台", "api", "dashboard", "web")
    has_hardware = any(term in text for term in hardware_terms)
    has_software = any(term in text for term in software_terms)
    if has_hardware and has_software:
        project_type = "hybrid"
    elif has_hardware:
        project_type = "embedded"
    else:
        project_type = "software"
    matched = sum(term in text for term in hardware_terms + software_terms)
    confidence = "high" if matched >= 3 else "medium" if matched else "low"
    return {"project_type": project_type, "confidence": confidence, "source": "discovery_heuristic"}
