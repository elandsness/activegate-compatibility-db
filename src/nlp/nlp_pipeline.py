import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.nlp.compatibility_extractor import (
    CompatibilityExtractor,
    CompatibilityStatement,
)
from src.nlp.entity_extractor import EntityExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    source_url: str
    source_title: str
    entities: Dict
    compatibility_statements: List
    version_pairs: List
    summary: Dict
    confidence_scores: Dict
    extraction_timestamp: str


class NLPPipeline:
    """Main NLP pipeline for extracting compatibility information from release notes."""

    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.compatibility_extractor = CompatibilityExtractor()

    def process_document(
        self, text: str, source_url: str = "", source_title: str = ""
    ) -> ExtractionResult:
        """
        Process a document (release note, doc page, etc.) and extract all compatibility information.
        """
        logger.info(f"Processing document: {source_title}")

        # Extract entities
        entities = self.entity_extractor.extract_all_entities(text)
        logger.info(
            f"Extracted {len(entities['versions'])} versions, {len(entities['os_versions'])} OS versions, {len(entities['extensions'])} extensions"
        )

        # Extract compatibility statements
        statements = self.compatibility_extractor.extract_statements(text)
        logger.info(f"Extracted {len(statements)} compatibility statements")

        # Extract version pairs
        version_pairs = self.compatibility_extractor.extract_version_pairs(text)
        logger.info(f"Extracted {len(version_pairs)} version upgrade pairs")

        # Summarize statements
        summary = self.compatibility_extractor.summarize_statements(statements)

        # Calculate confidence scores for each component
        confidence_scores = self._calculate_confidence_scores(entities, statements)

        # Create result object
        result = ExtractionResult(
            source_url=source_url,
            source_title=source_title,
            entities=self._serialize_entities(entities),
            compatibility_statements=self._serialize_statements(statements),
            version_pairs=version_pairs,
            summary=summary,
            confidence_scores=confidence_scores,
            extraction_timestamp=self._get_timestamp(),
        )

        return result

    def process_batch(self, documents: List[Dict]) -> List[ExtractionResult]:
        """
        Process a batch of documents.

        Args:
            documents: List of dicts with 'text', 'url', and 'title' keys

        Returns:
            List of ExtractionResult objects
        """
        results = []
        for doc in documents:
            try:
                result = self.process_document(
                    text=doc.get("content", ""),
                    source_url=doc.get("url", ""),
                    source_title=doc.get("title", "Unknown"),
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Error processing document {doc.get('title', 'Unknown')}: {e}"
                )

        return results

    def _serialize_entities(self, entities: Dict) -> Dict:
        """Serialize entity extraction results for JSON storage."""
        serialized = {}

        # Serialize versions
        serialized["versions"] = []
        for version, context in entities["versions"]:
            serialized["versions"].append(
                {
                    "version": str(version),
                    "major": version.major,
                    "minor": version.minor,
                    "patch": version.patch,
                    "raw": version.raw,
                    "context": context[:100],  # Truncate context for storage
                }
            )

        # Copy other entity types as-is
        serialized["os_versions"] = entities["os_versions"]
        serialized["extensions"] = entities["extensions"]

        return serialized

    def _serialize_statements(
        self, statements: List[CompatibilityStatement]
    ) -> List[Dict]:
        """Serialize compatibility statements for JSON storage."""
        return [
            {
                "type": s.statement_type,
                "subject_version": s.subject_version,
                "related_version": s.related_version,
                "component": s.component,
                "subject_component": s.subject_component,
                "object_component": s.object_component,
                "confidence": s.confidence,
                "raw_text": s.raw_text,
            }
            for s in statements
        ]

    def _calculate_confidence_scores(
        self, entities: Dict, statements: List[CompatibilityStatement]
    ) -> Dict:
        """Calculate overall confidence scores for each component."""
        scores = {
            "activegate": self._avg_confidence(
                [s for s in statements if s.component == "activegate"]
            ),
            "os": self._avg_confidence([s for s in statements if s.component == "os"]),
            "extension": self._avg_confidence(
                [s for s in statements if s.component == "extension"]
            ),
            "managed_cluster": self._avg_confidence(
                [s for s in statements if s.component == "managed_cluster"]
            ),
        }
        return scores

    @staticmethod
    def _avg_confidence(statements: List[CompatibilityStatement]) -> float:
        """Calculate average confidence for a list of statements."""
        if not statements:
            return 0.0
        return sum(s.confidence for s in statements) / len(statements)

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp."""
        from datetime import datetime

        return datetime.now().isoformat()


class ExtractedFact:
    """Represents a single extracted fact ready for storage in the graph."""

    def __init__(
        self,
        fact_type: str,
        subject: str,
        predicate: str,
        object_val: Optional[str],
        confidence: float,
        source_url: str,
        source_text: str,
        subject_type: str = "unknown",
        object_type: str = "unknown",
    ):
        self.fact_type = (
            fact_type  # 'compatibility', 'version_relation', 'deprecation', etc.
        )
        self.subject = subject
        self.predicate = (
            predicate  # e.g., 'COMPATIBLE_WITH', 'REQUIRES', 'DEPRECATED_IN'
        )
        self.object = object_val
        self.confidence = confidence
        self.source_url = source_url
        self.source_text = source_text
        self.subject_type = subject_type
        self.object_type = object_type

    def to_dict(self) -> Dict:
        return {
            "fact_type": self.fact_type,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "source_text": self.source_text,
            "subject_type": self.subject_type,
            "object_type": self.object_type,
        }


class FactConverter:
    """Convert extraction results into graph-ready facts."""

    @staticmethod
    def _is_activegate_version(value: Optional[str]) -> bool:
        """Return true when value looks like an ActiveGate version (1.x)."""
        if not value:
            return False
        return bool(re.match(r"^1\.\d+(?:\.\d+)?$", value.strip()))

    @staticmethod
    def convert_to_facts(extraction_result: ExtractionResult) -> List[ExtractedFact]:
        """Convert extraction result into a list of facts for graph storage."""
        facts = []

        # Convert compatibility statements to facts
        for stmt in extraction_result.compatibility_statements:
            fact_type = "compatibility_statement"
            subject_type = stmt.get(
                "subject_component", stmt.get("component", "unknown")
            )
            object_type = stmt.get("object_component", "unknown")
            predicate = FactConverter._map_statement_to_predicate(
                stmt["type"], object_type
            )
            object_val = stmt["related_version"] if stmt["related_version"] else None

            # Normalize and enrich facts
            base_conf = float(stmt.get("confidence", 0.5))
            adjusted_conf = base_conf
            if stmt.get("subject_version"):
                adjusted_conf = min(1.0, adjusted_conf + 0.05)
            if subject_type and subject_type != "unknown":
                adjusted_conf = min(1.0, adjusted_conf + 0.05)

            subj_val = stmt["subject_version"] or "unknown"

            # Keep ActiveGate subjects tied to release versions only.
            if subject_type == "activegate":
                if FactConverter._is_activegate_version(stmt.get("subject_version")):
                    subj_val = str(stmt.get("subject_version")).strip()
                else:
                    fallback_version = FactConverter._extract_activegate_version(
                        extraction_result.source_title, extraction_result.source_url
                    )
                    if not FactConverter._is_activegate_version(fallback_version):
                        continue
                    subj_val = str(fallback_version).strip()

            # If this is an extension-related statement try to resolve the extension name from extracted entities
            if subject_type == "extension":
                exts = (
                    extraction_result.entities.get("extensions", [])
                    if extraction_result.entities
                    else []
                )
                match = None
                for e in exts:
                    # match by explicit version when possible
                    if (
                        e.get("version")
                        and stmt.get("subject_version")
                        and e.get("version") == stmt.get("subject_version")
                    ):
                        match = e
                        break
                if match:
                    # normalize id-friendly name
                    name = match.get("name") or "extension"
                    norm = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                    subj_val = norm

            fact = ExtractedFact(
                fact_type=fact_type,
                subject=subj_val,
                predicate=predicate,
                object_val=object_val,
                confidence=adjusted_conf,
                source_url=extraction_result.source_url,
                source_text=stmt["raw_text"],
                subject_type=subject_type,
                object_type=object_type,
            )
            facts.append(fact)

        # Convert version pairs to upgrade path facts
        for pair in extraction_result.version_pairs:
            fact = ExtractedFact(
                fact_type="upgrade_path",
                subject=pair["from_version"],
                predicate="UPGRADEABLE_TO",
                object_val=pair["to_version"],
                confidence=0.8,
                source_url=extraction_result.source_url,
                source_text=pair["raw_text"],
                subject_type="activegate",
                object_type="activegate",
            )
            facts.append(fact)

        # Convert OS entities into support facts for ActiveGate releases.
        activegate_version = FactConverter._extract_activegate_version(
            extraction_result.source_title, extraction_result.source_url
        )
        if activegate_version:
            facts.extend(
                FactConverter._build_os_support_facts(
                    extraction_result, activegate_version
                )
            )

        return facts

    @staticmethod
    def _extract_activegate_version(
        source_title: str, source_url: str
    ) -> Optional[str]:
        """Extract ActiveGate version from source metadata."""
        title_match = re.search(
            r"activegate\s+(\d+\.\d+(?:\.\d+)?)", source_title, re.IGNORECASE
        )
        if title_match:
            return title_match.group(1)

        url_match = re.search(r"sprint-(\d+)", source_url, re.IGNORECASE)
        if url_match:
            return f"1.{url_match.group(1)}"

        return None

    @staticmethod
    def _normalize_os_versions(version_value: str) -> List[str]:
        """Normalize OS version strings into individual version tokens."""
        if not version_value:
            return []

        versions = []
        for chunk in version_value.split(","):
            token = chunk.strip()
            if not token:
                continue
            if "-" in token:
                bounds = [part.strip() for part in token.split("-", 1)]
                versions.extend([bound for bound in bounds if bound])
            else:
                versions.append(token)
        return versions

    @staticmethod
    def _build_os_support_facts(
        extraction_result: ExtractionResult, activegate_version: str
    ) -> List[ExtractedFact]:
        """Create compatibility facts from extracted OS entities."""
        os_entities = extraction_result.entities.get("os_versions", [])
        facts = []
        seen = set()

        for os_entry in os_entities:
            family = str(os_entry.get("family", "os")).strip().title()
            versions = FactConverter._normalize_os_versions(
                str(os_entry.get("version", "")).strip()
            )

            for version in versions:
                if not re.match(r"^\d+(?:\.\d+){0,2}$", version):
                    continue

                object_value = f"{family} {version}"
                signature = (activegate_version, object_value.lower())
                if signature in seen:
                    continue
                seen.add(signature)

                facts.append(
                    ExtractedFact(
                        fact_type="compatibility_statement",
                        subject=activegate_version,
                        predicate="SUPPORTED_BY",
                        object_val=object_value,
                        confidence=0.45,
                        source_url=extraction_result.source_url,
                        source_text=os_entry.get("raw", object_value),
                        subject_type="activegate",
                        object_type="os",
                    )
                )

        return facts

    @staticmethod
    def _map_statement_to_predicate(statement_type: str, object_type: str) -> str:
        mapping = {
            "compatible": {
                "managed_cluster": "REQUIRES",
                "extension": "COMPATIBLE_WITH",
                "os": "SUPPORTED_BY",
                "activegate": "COMPATIBLE_WITH",
            },
            "incompatible": {
                "extension": "INCOMPATIBLE_WITH",
                "managed_cluster": "INCOMPATIBLE_WITH",
                "os": "INCOMPATIBLE_WITH",
                "activegate": "INCOMPATIBLE_WITH",
            },
            "deprecated": {
                "extension": "DEPRECATED_IN",
                "managed_cluster": "DEPRECATED_IN",
                "activegate": "DEPRECATED_IN",
            },
            "requires_upgrade": {
                "extension": "REQUIRES_UPGRADE",
                "managed_cluster": "REQUIRES_UPGRADE",
                "activegate": "REQUIRES_UPGRADE",
            },
            "end_of_support": {
                "managed_cluster": "END_OF_SUPPORT",
                "activegate": "END_OF_SUPPORT",
                "extension": "END_OF_SUPPORT",
                "os": "END_OF_SUPPORT",
            },
        }
        return mapping.get(statement_type, {}).get(object_type, statement_type.upper())
