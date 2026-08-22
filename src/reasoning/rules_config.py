"""Configurable compatibility rules — loaded from YAML / JSON or env vars.

Priority (highest wins):
    1. Explicit ``load_rules_from_file(path)`` call
    2. ``COMPATIBILITY_RULES_PATH`` env var (YAML or JSON file)
    3. Individual ``COMPAT_*`` env vars
    4. Hardcoded defaults

This allows environments to override deprecation lists, thresholds, etc.
without touching code.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


DEFAULT_RULES: Dict[str, Any] = {
    "min_confidence_for_go": 0.8,
    "min_confidence_for_caution": 0.5,
    "critical_issues": ["incompatible", "end_of_support", "unsupported_version"],
    "warning_issues": ["deprecated", "requires_upgrade", "low_confidence"],
    "os_version_check": True,
    "extension_version_check": True,
    "managed_cluster_check": True,
}

# Hard-coded fallback version sets (used only when the graph has no data).
DEFAULT_DEPRECATED: set[str] = {"1.300", "1.310", "1.320", "1.325"}
DEFAULT_EOS: set[str] = {"1.280", "1.290", "1.300"}


def _env_list(key: str) -> list[str] | None:
    val = os.environ.get(key)
    if not val:
        return None
    return [v.strip() for v in val.split(",") if v.strip()]


def load_rules_from_file(path: str | Path) -> Dict[str, Any]:
    """Load compatibility rules from a YAML or JSON file."""
    path = Path(path)
    if not path.exists():
        logger.warning("Rules file not found: %s", path)
        return DEFAULT_RULES.copy()

    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)  # JSON is always supported
        if not isinstance(data, dict):
            raise ValueError("Rules file must contain a top-level JSON object")
        logger.info("Loaded %d rule keys from %s", len(data), path)
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse rules file %s: %s", path, exc)

    # Try YAML if pyyaml is installed
    try:
        import yaml  # type: ignore[import-untyped]
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        logger.info("Loaded %d rule keys from %s (YAML)", len(data), path)
        return data
    except Exception as exc:
        logger.error("Failed to parse %s as YAML: %s", path, exc)
        return DEFAULT_RULES.copy()


def load_rules_from_env() -> Dict[str, Any]:
    """Merge env-var overrides into the default rules dict."""
    rules = DEFAULT_RULES.copy()

    # Thresholds
    go_conf = os.environ.get("COMPAT_CONFIDENCE_GO")
    if go_conf:
        rules["min_confidence_for_go"] = float(go_conf)

    caution_conf = os.environ.get("COMPAT_CONFIDENCE_CAUTION")
    if caution_conf:
        rules["min_confidence_for_caution"] = float(caution_conf)

    # Custom deprecated / EOS versions (comma-separated)
    dep_list = _env_list("COMPAT_DEPRECATED_VERSIONS")
    if dep_list:
        rules["_deprecated_versions"] = dep_list  # internal, consumed by reasoner

    eos_list = _env_list("COMPAT_EOS_VERSIONS")
    if eos_list:
        rules["_eos_versions"] = eos_list

    # Boolean toggles
    for flag in ("os_version_check", "extension_version_check", "managed_cluster_check"):
        env_key = f"COMPAT_{flag.upper()}"
        val = os.environ.get(env_key)
        if val is not None:
            rules[flag] = val.lower() not in {"0", "false", "no"}

    # Custom critical / warning issue categories
    crit = _env_list("COMPAT_CRITICAL_ISSUES")
    if crit:
        rules["critical_issues"] = crit

    warn = _env_list("COMPAT_WARNING_ISSUES")
    if warn:
        rules["warning_issues"] = warn

    return rules


def load_rules() -> Dict[str, Any]:
    """Load compatibility rules — file path > env vars > defaults."""
    # 1. Explicit file path from env
    rules_path = os.environ.get("COMPATIBILITY_RULES_PATH")
    if rules_path:
        return load_rules_from_file(rules_path)

    # 2. Env var overrides
    return load_rules_from_env()


def get_default_deprecated() -> set[str]:
    """Return the default deprecated version set."""
    dep = os.environ.get("COMPAT_DEPRECATED_VERSIONS")
    if dep:
        return {v.strip() for v in dep.split(",") if v.strip()}
    return DEFAULT_DEPRECATED.copy()


def get_default_eos() -> set[str]:
    """Return the default end-of-support version set."""
    eos = os.environ.get("COMPAT_EOS_VERSIONS")
    if eos:
        return {v.strip() for v in eos.split(",") if v.strip()}
    return DEFAULT_EOS.copy()
