import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Dict, List, Optional

# Note: the app factory calls logging.basicConfig; leaf modules should not.
logger = logging.getLogger(__name__)


def _structured_log(logger, level, msg, **kwargs):  # type: ignore[no-untyped-def]
    """Log with correlation_id and context when available."""
    ctx = " ".join(f"{k}={v}" for k, v in kwargs.items())
    extra = {"correlation_id": kwargs.get("correlation_id", "")} if kwargs else {}
    log_fn = getattr(logger, level)
    log_fn("%s %s", msg.strip(), ctx, extra=extra)  # type: ignore[no-untyped-call]


def _cache_key(current: str, target: str, os_family: str | None, os_ver: str | None, managed: str | None, exts: list | None) -> str:
    """Create a cache key from check parameters."""
    parts = {
        "c": current, "t": target,
        "o": os_family or "", "ov": os_ver or "",
        "m": managed or "", "e": json.dumps(exts or [], sort_keys=True),
    }
    raw = json.dumps(parts, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]



class CompatibilityStatus(Enum):
    GO = "GO"
    GO_WITH_CAUTION = "GO_WITH_CAUTION"
    NO_GO = "NO_GO"
    UNKNOWN = "UNKNOWN"


@dataclass
class CompatibilityIssue:
    """Represents a single compatibility issue found during reasoning."""

    severity: str  # 'critical', 'warning', 'info'
    category: str  # 'version', 'os', 'extension', 'managed_cluster', 'deprecation'
    message: str
    source_url: Optional[str] = None
    source_text: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "source_url": self.source_url,
            "source_text": self.source_text,
            "recommendation": self.recommendation,
        }


@dataclass
class CompatibilityResult:
    """Complete result of a compatibility check."""

    status: CompatibilityStatus
    current_activegate_version: str
    target_activegate_version: str
    managed_cluster_version: str = "N/A"
    issues: List[CompatibilityIssue] = field(default_factory=list)
    warnings: List[CompatibilityIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    citations: List[Dict] = field(default_factory=list)
    confidence: float = 0.0
    checked_factors: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "current_activegate_version": self.current_activegate_version,
            "target_activegate_version": self.target_activegate_version,
            "managed_cluster_version": self.managed_cluster_version,
            "issues": [i.to_dict() for i in self.issues],
            "warnings": [w.to_dict() for w in self.warnings],
            "recommendations": self.recommendations,
            "citations": self.citations,
            "confidence": self.confidence,
            "checked_factors": self.checked_factors,
        }


class CompatibilityReasoner:
    """
    Core reasoning engine for determining ActiveGate upgrade compatibility.
    Applies rules and logic to make go/no-go decisions.
    """

    def __init__(self, graph_query=None):
        """
        Initialize the reasoner.

        Args:
            graph_query: Optional GraphQuery instance for database lookups
        """
        from src.reasoning.rules_config import load_rules  # avoid circular import

        self.graph_query = graph_query
        self._deprecated_cache: set[str] | None = None
        self._eos_cache: set[str] | None = None
        self.rules = load_rules()

    def _make_cache(self):  # type: ignore[no-untyped-def]
        """Create LRU cache for check_upgrade_compatibility (256 entries)."""
        return lru_cache(maxsize=256)(self._check_impl)

    @property
    def _cached_check(self):  # type: ignore[no-untyped-def]
        return self._make_cache()

    def check_upgrade_compatibility(
        self,
        current_version: str,
        target_version: str,
        os_family: Optional[str] = None,
        os_version: Optional[str] = None,
        managed_cluster_version: Optional[str] = None,
        extensions: Optional[List[Dict]] = None,
        use_graph: bool = False,
    ) -> "CompatibilityResult":
        """Check upgrade compatibility — cached via LRU cache."""
        _structured_log(
            logger, "info",
            f"Compatibility check: {current_version} -> {target_version}",
            correlation_id=getattr(self, "_correlation_id", ""),
        )
        # Convert extensions to tuple for hashability (lru_cache requires hashable args)
        extensions_hashable = tuple(
            tuple(sorted(ext.items())) if isinstance(ext, dict) else ext
            for ext in (extensions or [])
        )
        return self._cached_check(  # type: ignore[no-any-return]
            current_version, target_version, os_family, os_version,
            managed_cluster_version, extensions_hashable, use_graph,
        )

    def clear_cache(self) -> None:
        """Clear the LRU check cache (useful between test runs)."""
        if hasattr(self, "_cached_check"):
            self._cached_check.cache_clear()  # type: ignore[union-attr]


    def _load_deprecated_versions(self) -> set[str]:
        """Load deprecated version list from the graph, falling back to hardcoded defaults."""
        if self._deprecated_cache is not None:
            return self._deprecated_cache
        if self.graph_query:
            try:
                rows = self.graph_query.graph_conn.execute("""
                    MATCH (v:ActiveGateVersion)-[:DEPRECATED_IN]->(dep)
                    RETURN v.version AS version
                """)
                self._deprecated_cache = {r["version"] for r in rows}
                return self._deprecated_cache
            except Exception:
                pass  # Fall through to hardcoded defaults
        from src.reasoning.rules_config import DEFAULT_DEPRECATED  # avoid circular import
        self._deprecated_cache = DEFAULT_DEPRECATED.copy()
        return self._deprecated_cache

    def _load_eos_versions(self) -> set[str]:
        """Load end-of-support version list from the graph, falling back to hardcoded defaults."""
        if self._eos_cache is not None:
            return self._eos_cache
        if self.graph_query:
            try:
                rows = self.graph_query.graph_conn.execute("""
                    MATCH (v:ActiveGateVersion)-[:END_OF_SUPPORT]->(eos)
                    RETURN v.version AS version
                """)
                self._eos_cache = {r["version"] for r in rows}
                return self._eos_cache
            except Exception:
                pass  # Fall through to hardcoded defaults
        from src.reasoning.rules_config import DEFAULT_EOS
        self._eos_cache = DEFAULT_EOS.copy()
        return self._eos_cache

    def _load_compatibility_rules(self) -> Dict:
        """Load compatibility rules and thresholds."""
        return {
            "min_confidence_for_go": 0.8,
            "min_confidence_for_caution": 0.5,
            "critical_issues": [
                "incompatible",
                "end_of_support",
                "unsupported_version",
            ],
            "warning_issues": [
                "deprecated",
                "requires_upgrade",
                "low_confidence",
            ],
            "os_version_check": True,
            "extension_version_check": True,
            "managed_cluster_check": True,
        }

    def _check_impl(
        self,
        current_version: str,
        target_version: str,
        os_family: Optional[str] = None,
        os_version: Optional[str] = None,
        managed_cluster_version: Optional[str] = None,
        extensions: Optional[List[Dict]] = None,
        use_graph: bool = False,
    ) -> CompatibilityResult:
        """Core check logic (called through cached public method)."""
        _structured_log(logger, "info", f"Checking upgrade: {current_version} -> {target_version}")

        issues = []
        warnings = []
        citations = []
        checked_factors = {}

        # 1. Check version compatibility
        version_issues, version_warnings = self._check_version_compatibility(
            current_version, target_version
        )
        issues.extend(version_issues)
        warnings.extend(version_warnings)
        checked_factors["version"] = "checked"

        # 2. Check OS compatibility
        if os_family:
            os_issues, os_warnings = self._check_os_compatibility(
                target_version, os_family, os_version
            )
            issues.extend(os_issues)
            warnings.extend(os_warnings)
            checked_factors["os"] = "checked"

        # 3. Check Managed cluster compatibility
        if managed_cluster_version:
            mc_issues, mc_warnings = self._check_managed_cluster_compatibility(
                target_version, managed_cluster_version
            )
            issues.extend(mc_issues)
            warnings.extend(mc_warnings)
            checked_factors["managed_cluster"] = "checked"

        # 4. Check extension compatibility
        if extensions:
            ext_issues, ext_warnings = self._check_extension_compatibility(
                target_version, extensions
            )
            issues.extend(ext_issues)
            warnings.extend(ext_warnings)
            checked_factors["extensions"] = "checked"

        # 5. Check for deprecations
        dep_issues, dep_warnings = self._check_deprecations(target_version)
        issues.extend(dep_issues)
        warnings.extend(dep_warnings)
        checked_factors["deprecations"] = "checked"

        # 6. Check for end-of-support
        eos_issues = self._check_end_of_support(target_version)
        issues.extend(eos_issues)
        checked_factors["end_of_support"] = "checked"

        # 7. Query graph if available and requested
        if use_graph and self.graph_query:
            graph_result = self._check_via_graph(
                current_version,
                target_version,
                managed_cluster_version,
                os_family,
                extensions,
            )
            issues.extend(graph_result.get("issues", []))
            warnings.extend(graph_result.get("warnings", []))
            citations.extend(graph_result.get("citations", []))

        # 8. Determine final status
        issues = self._dedupe_issues(issues)
        warnings = self._dedupe_issues(warnings)

        status = self._determine_status(issues, warnings)

        # 9. Generate recommendations
        recommendations = self._generate_recommendations(issues, warnings)

        # 10. Calculate confidence
        confidence = self._calculate_confidence(issues, warnings)

        return CompatibilityResult(
            status=status,
            current_activegate_version=current_version,
            target_activegate_version=target_version,
            managed_cluster_version=managed_cluster_version or "N/A",
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            citations=citations,
            confidence=confidence,
            checked_factors=checked_factors,
        )

    @staticmethod
    def _dedupe_issues(items: List[CompatibilityIssue]) -> List[CompatibilityIssue]:
        """Remove repeated issue/warning entries while preserving first-seen order."""
        seen = set()
        deduped = []

        for item in items:
            key = (
                item.severity,
                item.category,
                item.message,
                item.recommendation,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    def _check_version_compatibility(self, current: str, target: str) -> tuple:
        """Check if the version upgrade is valid."""
        issues = []
        warnings = []

        try:
            current_parts = [int(x) for x in current.split(".")]
            target_parts = [int(x) for x in target.split(".")]

            # Target should be >= current
            if target_parts < current_parts:
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="version",
                        message=f"Target version {target} is older than current version {current}",
                        recommendation="Select a target version >= current version",
                    )
                )
            elif target_parts == current_parts:
                warnings.append(
                    CompatibilityIssue(
                        severity="warning",
                        category="version",
                        message=f"Target version {target} is the same as current version {current}",
                        recommendation="No upgrade needed if already on this version",
                    )
                )
            else:
                # Valid upgrade path
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="version",
                        message=f"Upgrading from {current} to {target}",
                        recommendation=None,
                    )
                )
        except Exception as e:
            issues.append(
                CompatibilityIssue(
                    severity="critical",
                    category="version",
                    message=f"Could not parse version: {e}",
                    recommendation="Verify version format (e.g., 1.335)",
                )
            )

        return issues, warnings

    def _check_os_compatibility(
        self, ag_version: str, os_family: str, os_version: str = None
    ) -> tuple:
        """Check OS compatibility for ActiveGate."""
        issues = []
        warnings = []

        # Known supported OS versions based on the Dynatrace Linux support matrix.
        supported_os = {
            "windows": ["2016", "2019", "2022"],
            "linux": [],
            "almalinux": ["8", "9", "10"],
            "alpine linux": [
                "3.10",
                "3.11",
                "3.12",
                "3.13",
                "3.14",
                "3.15",
                "3.16",
                "3.17",
                "3.18",
                "3.19",
                "3.20",
                "3.21",
                "3.22",
                "3.23",
            ],
            "amazon linux": ["2023"],
            "azure linux": ["2", "3"],
            "bottlerocket": ["1"],
            "centos stream": ["9"],
            "debian": ["11", "12", "13"],
            "fedora": ["42", "43", "44"],
            "oracle linux": ["7", "8", "9", "10"],
            "red hat enterprise linux": ["7", "8", "9", "10"],
            "rhel": ["7", "8", "9", "10"],
            "red hat enterprise linux coreos": ["4.14", "4.15", "4.16"],
            "rhcos": ["4.14", "4.15", "4.16"],
            "rocky linux": ["8", "9", "10"],
            "suse linux enterprise server": [
                "12.5",
                "15.4",
                "15.5",
                "15.6",
                "15.7",
                "16.0",
            ],
            "sles": ["12.5", "15.4", "15.5", "15.6", "15.7", "16.0"],
            "ubuntu": ["16.04", "18.04", "20.04", "22.04", "24.04", "26.04"],
            "opensuse": ["15.6", "16.0"],
            "centos": ["7", "8", "9"],
        }

        os_family_lower = os_family.lower()

        if os_family_lower == "linux":
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="os",
                    message=f"Linux provided without distro for AG {ag_version}",
                    recommendation="Provide a specific Linux distro (for example: Red Hat Enterprise Linux, Debian, Ubuntu, SLES, Rocky Linux).",
                )
            )
            return issues, warnings

        if os_family_lower in supported_os:
            if os_version:
                # Check specific version
                version_num = os_version.strip()
                supported = supported_os[os_family_lower]

                if supported and version_num not in supported:
                    warnings.append(
                        CompatibilityIssue(
                            severity="warning",
                            category="os",
                            message=f"OS version {os_version} may not be explicitly supported for AG {ag_version}",
                            recommendation=f'Ensure OS is one of: {", ".join(supported)}',
                        )
                    )
            else:
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="os",
                        message=f"OS family {os_family} supported but specific version not checked",
                        recommendation="Provide OS version for detailed compatibility check",
                    )
                )
        else:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="os",
                    message=f"OS family {os_family} not in known supported list",
                    recommendation="Verify OS is supported by Dynatrace",
                )
            )

        return issues, warnings

    def _check_managed_cluster_compatibility(
        self, ag_version: str, managed_version: str
    ) -> tuple:
        """Check Managed cluster version compatibility."""
        issues = []
        warnings = []

        try:
            ag_parts = [int(x) for x in ag_version.split(".")]
            mc_parts = [int(x) for x in managed_version.split(".")]

            # ActiveGate typically requires Managed version >= AG version - 5
            min_managed = [ag_parts[0], max(0, ag_parts[1] - 5), 0]

            if mc_parts < min_managed:
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="managed_cluster",
                        message=f"Managed cluster {managed_version} may be too old for AG {ag_version}",
                        recommendation=f"Upgrade Managed cluster to at least {min_managed[0]}.{min_managed[1]}.0",
                    )
                )
            else:
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="managed_cluster",
                        message=f"AG {ag_version} compatible with Managed {managed_version}",
                        recommendation=None,
                    )
                )
        except Exception as e:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="managed_cluster",
                    message=f"Could not verify Managed cluster compatibility: {e}",
                    recommendation="Manually verify Managed cluster version compatibility",
                )
            )

        return issues, warnings

    def _check_extension_compatibility(
        self, ag_version: str, extensions: List[Dict]
    ) -> tuple:
        """Check extension compatibility."""
        issues = []
        warnings = []

        for ext in extensions:
            ext_id = ext.get("id", "unknown")
            ext_version = ext.get("version", "unknown")

            # Check for known incompatible extensions or version requirements
            # This is a simplified check - in production would query graph/knowledge base

            if ext_version:
                # Simple version parsing check
                try:
                    ext_parts = [int(x) for x in ext_version.split(".")]
                    ag_parts = [int(x) for x in ag_version.split(".")]

                    # If extension is much newer than AG, might have issues
                    if ext_parts[0] > ag_parts[0]:
                        warnings.append(
                            CompatibilityIssue(
                                severity="warning",
                                category="extension",
                                message=f"Extension {ext_id} v{ext_version} may require newer AG",
                                recommendation="Verify extension supports AG version",
                            )
                        )
                except (ValueError, TypeError):
                    warnings.append(
                        CompatibilityIssue(
                            severity="info",
                            category="extension",
                            message=f"Could not verify extension {ext_id} compatibility",
                            recommendation=None,
                        )
                    )

        return issues, warnings

    def _check_deprecations(self, version: str) -> tuple:
        """Check for deprecated versions using graph-first lookup."""
        issues = []
        warnings = []

        deprecated_versions = self._load_deprecated_versions()

        if version in deprecated_versions:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="deprecation",
                    message=f"ActiveGate {version} is deprecated",
                    recommendation="Consider upgrading to a newer version",
                )
            )

        return issues, warnings

    def _check_end_of_support(self, version: str) -> List[CompatibilityIssue]:
        """Check for end-of-support versions using graph-first lookup."""
        issues = []

        eos_versions = self._load_eos_versions()

        if version in eos_versions:
            issues.append(
                CompatibilityIssue(
                    severity="critical",
                    category="end_of_support",
                    message=f"ActiveGate {version} has reached end of support",
                    recommendation="Upgrade to a supported version immediately",
                )
            )

        return issues

    def _check_via_graph(
        self,
        current: str,
        target: str,
        managed: str = None,
        os: str = None,
        extensions: list = None,
    ) -> Dict:
        """Check compatibility via graph database."""
        if not self.graph_query:
            return {}

        try:
            result = self.graph_query.check_activegate_compatibility(
                activegate_version=target,
                managed_version=managed or "1.335",
                os_family=os,
                extensions=([e.get("id") for e in extensions] if extensions else None),
            )

            # Convert graph result to issues
            issues = []
            warnings = []
            citations = []

            for issue_msg in result.get("issues", []):
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="graph",
                        message=issue_msg,
                        recommendation=None,
                    )
                )

            for warn_msg in result.get("warnings", []):
                warnings.append(
                    CompatibilityIssue(
                        severity="warning",
                        category="graph",
                        message=warn_msg,
                        recommendation=None,
                    )
                )

            for unknown_msg in result.get("unknown_extensions", []):
                warnings.append(
                    CompatibilityIssue(
                        severity="warning",
                        category="extension_unknown",
                        message=unknown_msg,
                        recommendation="Add verified extension compatibility constraints before decision",
                    )
                )

            return {
                "issues": issues,
                "warnings": warnings,
                "citations": citations,
            }
        except Exception as e:
            logger.error(f"Error checking via graph: {e}")
            return {}

    def _determine_status(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> CompatibilityStatus:
        """Determine final compatibility status."""
        if any(w.category == "extension_unknown" for w in warnings):
            return CompatibilityStatus.UNKNOWN

        # Critical issues = NO_GO
        critical_issues = [i for i in issues if i.severity == "critical"]
        if critical_issues:
            return CompatibilityStatus.NO_GO

        # Warnings = GO_WITH_CAUTION
        if warnings:
            return CompatibilityStatus.GO_WITH_CAUTION

        # Clean = GO
        return CompatibilityStatus.GO

    def _generate_recommendations(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> List[str]:
        """Generate recommendations based on issues and warnings."""
        recommendations = []

        for issue in issues:
            if issue.recommendation:
                recommendations.append(issue.recommendation)

        for warning in warnings:
            if warning.recommendation and warning.recommendation not in recommendations:
                recommendations.append(warning.recommendation)

        return recommendations

    def _calculate_confidence(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> float:
        """Calculate confidence score."""
        base_confidence = 1.0

        # Reduce for critical issues
        critical_count = len([i for i in issues if i.severity == "critical"])
        base_confidence -= critical_count * 0.3

        # Reduce for warnings
        warning_count = len(warnings)
        base_confidence -= warning_count * 0.1

        return max(0.0, min(1.0, base_confidence))
