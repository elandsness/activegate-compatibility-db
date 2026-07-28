import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Represents a source citation for a compatibility finding."""

    source_url: str
    source_title: str
    source_type: str  # 'release_notes', 'extension_docs', 'end_of_support', 'hub'
    relevant_text: str
    extracted_date: str
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_type": self.source_type,
            "relevant_text": self.relevant_text,
            "extracted_date": self.extracted_date,
            "confidence": self.confidence,
        }


class CitationGenerator:
    """
    Generates citations for compatibility findings.
    Links back to source text/release notes for explainability.
    """

    def __init__(self):
        self.source_registry = {}

    def register_source(self, url: str, title: str, source_type: str):
        """Register a source document."""
        self.source_registry[url] = {
            "title": title,
            "type": source_type,
            "registered_at": datetime.now().isoformat(),
        }

    def generate_citation(
        self, source_url: str, relevant_text: str, confidence: float = 0.8
    ) -> Optional[Citation]:
        """
        Generate a citation for a source.

        Args:
            source_url: URL of the source document
            relevant_text: Text from the source that's relevant
            confidence: Confidence score for this citation

        Returns:
            Citation object or None if source not found
        """
        source_info = self.source_registry.get(source_url)

        if not source_info:
            logger.warning(f"Source not registered: {source_url}")
            return None

        return Citation(
            source_url=source_url,
            source_title=source_info["title"],
            source_type=source_info["type"],
            relevant_text=relevant_text[:500],  # Limit text length
            extracted_date=source_info["registered_at"],
            confidence=confidence,
        )

    def generate_citations_from_issues(self, issues: List) -> List[Citation]:
        """Generate citations from a list of issues."""
        citations = []

        for issue in issues:
            if hasattr(issue, "source_url") and issue.source_url:
                citation = self.generate_citation(
                    source_url=issue.source_url,
                    relevant_text=issue.source_text or issue.message,
                    confidence=getattr(issue, "confidence", 0.5),
                )
                if citation:
                    citations.append(citation)

        return citations

    def format_citation_text(self, citation: Citation) -> str:
        """Format a citation for display."""
        lines = [
            f"Source: {citation.source_title}",
            f"URL: {citation.source_url}",
            f"Type: {citation.source_type}",
            f'Relevant: "{citation.relevant_text[:200]}..."',
            f"Confidence: {citation.confidence:.0%}",
            f"Extracted: {citation.extracted_date}",
        ]
        return "\n".join(lines)

    def format_citations_for_output(self, citations: List[Citation]) -> str:
        """Format multiple citations for output."""
        if not citations:
            return "No sources cited."

        output = ["Sources:", "-" * 40]

        for i, citation in enumerate(citations, 1):
            output.append(f"\n[{i}] {citation.source_title}")
            output.append(f"    URL: {citation.source_url}")
            output.append(f"    Type: {citation.source_type}")
            output.append(f"    Confidence: {citation.confidence:.0%}")

        return "\n".join(output)


class QueryProcessor:
    """
    Processes natural language queries and converts them to structured checks.
    """

    def __init__(self, reasoner, semantic_search=None, citation_generator=None):
        self.reasoner = reasoner
        self.semantic_search = semantic_search
        self.citation_generator = citation_generator

    REQUIRED_CONTEXT_FIELDS = [
        "current_activegate_version",
        "target_activegate_version",
        "managed_cluster_version",
        "os_family",
        "os_version",
        "extensions",
    ]

    def process_query(self, query: str, context: Optional[Dict] = None) -> Dict:
        """
        Process a natural language query.

        Args:
            query: Natural language query (e.g., "Can I run extension X on AG 1.335?")

        Returns:
            Dict with parsed parameters and result
        """
        query = query.lower()

        # Extract version information
        import re

        version_pattern = r"(\d+\.\d+(?:\.\d+)*)"
        versions = re.findall(version_pattern, query)

        # Determine query type
        if "extension" in query or "ext" in query:
            query_type = "extension_compatibility"
        elif "os" in query or "windows" in query or "linux" in query:
            query_type = "os_compatibility"
        elif "managed" in query or "cluster" in query:
            query_type = "managed_compatibility"
        else:
            query_type = "general_compatibility"

        merged_context = self._build_and_merge_context(query, context)
        missing_fields = self._get_missing_context_fields(merged_context)
        merged_context["next_required_field"] = (
            missing_fields[0] if missing_fields else None
        )

        return {
            "query_type": query_type,
            "versions_found": versions,
            "query": query,
            "context": merged_context,
            "missing_fields": missing_fields,
            "ready_for_decision": len(missing_fields) == 0,
            "follow_up_prompt": self._build_follow_up_prompt(
                merged_context, missing_fields
            ),
        }

    def _build_and_merge_context(self, query: str, context: Optional[Dict]) -> Dict:
        """Extract compatibility context from the query and merge with prior context."""
        merged = {
            "cluster_version": None,
            "os_family": None,
            "os_version": None,
            "current_activegate_version": None,
            "target_activegate_version": None,
            "managed_cluster_version": None,
            "extensions": None,
            "extensions_known": False,
            "next_required_field": None,
        }

        if context:
            merged.update(context)

        extracted = self._extract_context_from_query(query)
        for key, value in extracted.items():
            if value is not None:
                merged[key] = value

        # In interview mode, map short replies to the field we explicitly requested.
        pending_field = merged.get("next_required_field")
        if pending_field and pending_field in self.REQUIRED_CONTEXT_FIELDS:
            if pending_field == "extensions":
                field_is_missing = not merged.get("extensions_known", False)
            else:
                field_is_missing = not merged.get(pending_field)

            if field_is_missing:
                pending_value = self._extract_value_for_field_from_answer(
                    pending_field, query
                )
                if pending_value is not None:
                    if pending_field == "extensions":
                        merged["extensions"] = pending_value
                        merged["extensions_known"] = True
                    else:
                        merged[pending_field] = pending_value

        # Treat cluster and managed cluster as aliases unless explicitly set differently.
        if merged.get("managed_cluster_version") and not merged.get("cluster_version"):
            merged["cluster_version"] = merged["managed_cluster_version"]
        if merged.get("cluster_version") and not merged.get("managed_cluster_version"):
            merged["managed_cluster_version"] = merged["cluster_version"]

        return merged

    def _extract_value_for_field_from_answer(self, field: str, query: str):
        """Extract value from a short answer for a specific requested field."""
        import re

        normalized = query.strip().lower()
        version_pattern = r"(\d+\.\d+(?:\.\d+)*)"

        if field in [
            "current_activegate_version",
            "target_activegate_version",
            "managed_cluster_version",
        ]:
            match = re.search(version_pattern, normalized)
            return match.group(1) if match else None

        if field == "os_family":
            distro_tokens = [
                ("red hat enterprise linux coreos", "Red Hat Enterprise Linux CoreOS"),
                ("rhcos", "Red Hat Enterprise Linux CoreOS"),
                ("red hat enterprise linux", "Red Hat Enterprise Linux"),
                ("rhel", "Red Hat Enterprise Linux"),
                ("suse linux enterprise server", "SUSE Linux Enterprise Server"),
                ("sles", "SUSE Linux Enterprise Server"),
                ("centos stream", "CentOS Stream"),
                ("almalinux", "AlmaLinux"),
                ("alpine linux", "Alpine Linux"),
                ("amazon linux", "Amazon Linux"),
                ("azure linux", "Azure Linux"),
                ("bottlerocket", "Bottlerocket"),
                ("debian", "Debian"),
                ("fedora", "Fedora"),
                ("oracle linux", "Oracle Linux"),
                ("rocky linux", "Rocky Linux"),
                ("opensuse", "openSUSE"),
                ("ubuntu", "Ubuntu"),
                ("centos", "CentOS"),
            ]
            if "windows" in normalized:
                return "windows"
            for token, canonical in distro_tokens:
                if token in normalized:
                    return canonical
            if "linux" in normalized:
                return "linux"
            return None

        if field == "os_version":
            patterns = [
                r"([0-9]{2}\.[0-9]{2})",  # ubuntu style
                r"([0-9]{4})",  # windows year
                r"([0-9]+(?:\.[0-9]+)?)",  # generic numeric
            ]
            for pattern in patterns:
                match = re.search(pattern, normalized)
                if match:
                    return match.group(1)
            return None

        if field == "extensions":
            if normalized in ["none", "no", "n/a", "na"]:
                return []
            if any(
                phrase in normalized
                for phrase in ["no extensions", "none installed", "without extensions"]
            ):
                return []

            matches = re.findall(
                r"([a-z0-9][a-z0-9_-]{1,})\s*[:@]\s*(\d+\.\d+(?:\.\d+)*)",
                normalized,
            )
            if matches:
                return [
                    {"id": ext_id, "version": ext_version}
                    for ext_id, ext_version in matches
                ]
            return None

        return None

    def _extract_context_from_query(self, query: str) -> Dict:
        """Extract required compatibility context from a natural language message."""
        import re

        result = {
            "cluster_version": None,
            "os_family": None,
            "os_version": None,
            "current_activegate_version": None,
            "target_activegate_version": None,
            "managed_cluster_version": None,
            "extensions": None,
            "extensions_known": False,
        }

        version_pattern = r"(\d+\.\d+(?:\.\d+)*)"

        # ActiveGate current -> target upgrades.
        from_to = re.search(
            rf"(?:from|current(?:\s+activegate)?(?:\s+version)?)\s+{version_pattern}.{{0,40}}(?:to|target|desired)\s+{version_pattern}",
            query,
        )
        if from_to:
            versions = re.findall(version_pattern, from_to.group(0))
            if len(versions) >= 2:
                result["current_activegate_version"] = versions[0]
                result["target_activegate_version"] = versions[1]

        explicit_current = re.search(
            rf"current(?:\s+activegate)?(?:\s+version)?\s*[:=]?\s*{version_pattern}",
            query,
        )
        if explicit_current:
            vals = re.findall(version_pattern, explicit_current.group(0))
            if vals:
                result["current_activegate_version"] = vals[-1]

        explicit_target = re.search(
            rf"(?:target|desired)(?:\s+activegate)?(?:\s+version)?\s*[:=]?\s*{version_pattern}",
            query,
        )
        if explicit_target:
            vals = re.findall(version_pattern, explicit_target.group(0))
            if vals:
                result["target_activegate_version"] = vals[-1]

        managed_match = re.search(
            rf"managed\s+cluster(?:\s+version)?\s*[:=]?\s*{version_pattern}",
            query,
        )
        if managed_match:
            vals = re.findall(version_pattern, managed_match.group(0))
            if vals:
                result["managed_cluster_version"] = vals[-1]

        cluster_match = re.search(
            rf"(?<!managed\s)cluster(?:\s+version)?\s*[:=]?\s*{version_pattern}",
            query,
        )
        if cluster_match:
            vals = re.findall(version_pattern, cluster_match.group(0))
            if vals:
                result["cluster_version"] = vals[-1]

        distro_tokens = [
            ("red hat enterprise linux coreos", "Red Hat Enterprise Linux CoreOS"),
            ("rhcos", "Red Hat Enterprise Linux CoreOS"),
            ("red hat enterprise linux", "Red Hat Enterprise Linux"),
            ("rhel", "Red Hat Enterprise Linux"),
            ("suse linux enterprise server", "SUSE Linux Enterprise Server"),
            ("sles", "SUSE Linux Enterprise Server"),
            ("centos stream", "CentOS Stream"),
            ("almalinux", "AlmaLinux"),
            ("alpine linux", "Alpine Linux"),
            ("amazon linux", "Amazon Linux"),
            ("azure linux", "Azure Linux"),
            ("bottlerocket", "Bottlerocket"),
            ("debian", "Debian"),
            ("fedora", "Fedora"),
            ("oracle linux", "Oracle Linux"),
            ("rocky linux", "Rocky Linux"),
            ("opensuse", "openSUSE"),
            ("ubuntu", "Ubuntu"),
            ("centos", "CentOS"),
        ]

        os_family = None
        if "windows" in query:
            os_family = "windows"
        else:
            lowered_query = query.lower()
            for token, canonical in distro_tokens:
                if token in lowered_query:
                    os_family = canonical
                    break
            if not os_family and "linux" in lowered_query:
                os_family = "linux"
        if os_family:
            result["os_family"] = os_family

        os_version_patterns = [
            r"os\s+version\s*[:=]?\s*([a-z0-9\._-]+)",
            r"windows\s+([0-9]{4}|[0-9]{2}h[0-9])",
            r"ubuntu\s+([0-9]{2}\.[0-9]{2})",
            r"rhel\s+([0-9]+(?:\.[0-9]+)?)",
            r"centos\s+([0-9]+(?:\.[0-9]+)?)",
            r"linux\s+([0-9]+(?:\.[0-9]+)?)",
        ]
        for pattern in os_version_patterns:
            os_match = re.search(pattern, query)
            if os_match:
                result["os_version"] = os_match.group(1)
                break

        # Extensions can be explicit list or explicit "none installed".
        if any(
            phrase in query
            for phrase in [
                "no extensions",
                "none installed",
                "without extensions",
                "extensions: none",
            ]
        ):
            result["extensions"] = []
            result["extensions_known"] = True
        else:
            ext_matches = []
            explicit_exts_match = re.search(
                r"extensions?\s*[:=]\s*(.+)$",
                query,
            )
            if explicit_exts_match:
                ext_segment = explicit_exts_match.group(1)
                ext_matches = re.findall(
                    r"([a-z0-9][a-z0-9_-]{1,})\s*[:@]\s*(\d+\.\d+(?:\.\d+)*)",
                    ext_segment,
                )
            else:
                ext_matches = re.findall(
                    r"extension\s+([a-z0-9][a-z0-9_-]{1,})\s+(?:version\s*)?(\d+\.\d+(?:\.\d+)*)",
                    query,
                )

            if ext_matches:
                result["extensions"] = [
                    {"id": ext_id, "version": ext_version}
                    for ext_id, ext_version in ext_matches
                ]
                result["extensions_known"] = True

        # Fallback: if two versions are present and AG versions are still missing.
        if (
            not result["current_activegate_version"]
            or not result["target_activegate_version"]
        ):
            all_versions = re.findall(version_pattern, query)
            if len(all_versions) >= 2:
                result["current_activegate_version"] = (
                    result["current_activegate_version"] or all_versions[0]
                )
                result["target_activegate_version"] = (
                    result["target_activegate_version"] or all_versions[1]
                )

        return result

    def _get_missing_context_fields(self, context: Dict) -> List[str]:
        """Return missing required fields for a safe compatibility decision."""
        missing = []
        for field in self.REQUIRED_CONTEXT_FIELDS:
            if field == "extensions":
                if not context.get("extensions_known", False):
                    missing.append(field)
                continue

            if not context.get(field):
                missing.append(field)

        return missing

    def _build_follow_up_prompt(self, context: Dict, missing_fields: List[str]) -> str:
        """Build interview-style follow-up text when required context is missing."""
        if not missing_fields:
            return ""

        field_labels = {
            "cluster_version": "Cluster version",
            "os_family": "OS family (Linux or Windows)",
            "os_version": "OS version",
            "current_activegate_version": "Current ActiveGate version",
            "target_activegate_version": "Desired ActiveGate version",
            "managed_cluster_version": "Managed Cluster version",
            "extensions": "Installed extensions and versions (or 'none')",
        }

        known_lines = []
        if context.get("current_activegate_version"):
            known_lines.append(
                f"- Current ActiveGate: {context['current_activegate_version']}"
            )
        if context.get("target_activegate_version"):
            known_lines.append(
                f"- Desired ActiveGate: {context['target_activegate_version']}"
            )
        if context.get("cluster_version"):
            known_lines.append(f"- Cluster: {context['cluster_version']}")
        if context.get("managed_cluster_version"):
            known_lines.append(
                f"- Managed Cluster: {context['managed_cluster_version']}"
            )
        if context.get("os_family"):
            known_lines.append(f"- OS family: {context['os_family']}")
        if context.get("os_version"):
            known_lines.append(f"- OS version: {context['os_version']}")
        if context.get("extensions_known", False):
            if context.get("extensions"):
                ext_text = ", ".join(
                    f"{ext['id']}:{ext['version']}" for ext in context["extensions"]
                )
                known_lines.append(f"- Extensions: {ext_text}")
            else:
                known_lines.append("- Extensions: none")

        next_missing_field = missing_fields[0]
        next_missing_label = field_labels[next_missing_field]

        response_parts = [
            "I need a few required details before I can return a GO/NO-GO decision.",
            f"Please provide: {next_missing_label}.",
        ]

        if known_lines:
            response_parts.extend(["", "Details I already have:", *known_lines])

        response_parts.extend(
            [
                "",
                "I will ask for the next required field after this one.",
            ]
        )

        return "\n".join(response_parts)

    def parse_structured_input(self, input_data: Dict) -> Dict:
        """
        Parse structured input (from CLI/API) into compatibility check parameters.

        Args:
            input_data: Dict with current_state and target_state

        Returns:
            Parameters for compatibility check
        """
        params = {
            "current_version": input_data.get("current_activegate_version"),
            "target_version": input_data.get("target_activegate_version"),
            "os_family": input_data.get("os_family"),
            "os_version": input_data.get("os_version"),
            "managed_cluster_version": input_data.get("managed_cluster_version"),
            "extensions": input_data.get("extensions", []),
        }

        return params

    def format_result_for_display(self, result) -> str:
        """Format compatibility result for user display."""
        output = []

        # Status header
        status_emoji = {
            "GO": "✅",
            "GO_WITH_CAUTION": "⚠️",
            "NO_GO": "❌",
            "UNKNOWN": "❓",
        }

        emoji = status_emoji.get(result.status.value, "❓")
        output.append(f"\n{emoji} Status: {result.status.value}")
        output.append(
            f"Upgrading: {result.current_activegate_version} → {result.target_activegate_version}"
        )

        if result.managed_cluster_version != "N/A":
            output.append(f"Managed Cluster: {result.managed_cluster_version}")

        output.append(f"Confidence: {result.confidence:.0%}")

        # Issues
        if result.issues:
            output.append(f"\n🚫 Issues ({len(result.issues)}):")
            for issue in result.issues:
                output.append(f"  - [{issue.severity.upper()}] {issue.message}")
                if issue.recommendation:
                    output.append(f"    → {issue.recommendation}")

        # Warnings
        if result.warnings:
            output.append(f"\n⚠️ Warnings ({len(result.warnings)}):")
            for warning in result.warnings:
                output.append(f"  - {warning.message}")
                if warning.recommendation:
                    output.append(f"    → {warning.recommendation}")

        # Recommendations
        if result.recommendations:
            output.append("\n📋 Recommendations:")
            for rec in result.recommendations:
                output.append(f"  • {rec}")

        # Citations
        if result.citations:
            output.append(f"\n📚 Sources ({len(result.citations)}):")
            for cite in result.citations:
                output.append(f"  - {cite['source_title']}: {cite['source_url']}")

        return "\n".join(output)
