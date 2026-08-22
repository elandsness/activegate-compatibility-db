import logging
import re
from typing import Any, Dict, List, Optional

from src.nlp.nlp_pipeline import ExtractedFact
from src.storage.connection_manager import get_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphPopulator:
    """Populates Neo4j graph with extracted compatibility facts."""

    def __init__(self, graph_conn=None):  # type: ignore[assignment]
        """Initialize graph populator (accepts any connection-like object)."""
        self.graph_conn = graph_conn or get_manager()
        if not self.graph_conn.is_connected:
            logger.error(
                "GraphPopulator could not connect to Neo4j during initialization"
            )

    def populate_from_facts(self, facts: List[ExtractedFact]) -> int:
        """
        Populate graph from a list of extracted facts.

        Args:
            facts: List of ExtractedFact objects to insert

        Returns:
            Count of facts inserted
        """
        if not self.graph_conn.driver:
            if not self.graph_conn.connect():
                logger.error("Failed to connect to Neo4j: cannot insert facts")
                return 0

        inserted = 0
        for fact in facts:
            try:
                if self.insert_fact(fact):
                    inserted += 1
            except Exception as e:
                logger.error(f"Error inserting fact: {e}")

        logger.info(f"Inserted {inserted} facts into graph")
        return inserted

    def ensure_activegate_release_node(
        self, version: str, title: str, source_url: str
    ) -> bool:
        """Ensure an ActiveGate release node exists in Neo4j."""
        if not self.graph_conn.driver:
            if not self.graph_conn.connect():
                logger.error("Failed to connect to Neo4j: cannot ensure release node")
                return False

        query = """
        MERGE (ag:ActiveGateVersion {version: $version})
        SET ag.title = $title,
            ag.source_url = $source_url,
            ag.is_release = true,
            ag.last_seen = datetime()
        RETURN ag
        """
        try:
            result = self.graph_conn.execute(
                query, {"version": version, "title": title, "source_url": source_url}
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error ensuring ActiveGate release node: {e}")
            return False

    def ensure_managed_release_node(
        self,
        version: str,
        title: str,
        source_url: str,
        rollout_start: Optional[str] = None,
        updated_on: Optional[str] = None,
    ) -> bool:
        """Ensure a ManagedClusterVersion release node exists in Neo4j."""
        if not self.graph_conn.driver:
            if not self.graph_conn.connect():
                logger.error(
                    "Failed to connect to Neo4j: cannot ensure managed release node"
                )
                return False

        query = """
        MERGE (mc:ManagedClusterVersion {version: $version})
        SET mc.title = $title,
            mc.source_url = $source_url,
            mc.is_release = true,
            mc.rollout_start = coalesce($rollout_start, mc.rollout_start),
            mc.updated_on = coalesce($updated_on, mc.updated_on),
            mc.last_seen = datetime()
        RETURN mc
        """
        try:
            result = self.graph_conn.execute(
                query,
                {
                    "version": version,
                    "title": title,
                    "source_url": source_url,
                    "rollout_start": rollout_start,
                    "updated_on": updated_on,
                },
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error ensuring Managed release node: {e}")
            return False

    def insert_fact(self, fact: ExtractedFact) -> bool:
        """Insert a single fact into the graph."""
        try:
            if fact.fact_type == "compatibility_statement":
                return self._insert_compatibility_statement(fact)
            elif fact.fact_type == "upgrade_path":
                return self._insert_upgrade_path(fact)
            else:
                logger.warning(f"Unknown fact type: {fact.fact_type}")
                return False
        except Exception as e:
            logger.error(f"Error inserting fact: {e}")
            return False

    def _insert_compatibility_statement(self, fact: ExtractedFact) -> bool:
        """Insert a compatibility statement fact."""
        relationship_type = fact.predicate

        subject_label, subject_key = self._label_and_key_for_type(
            fact.subject_type,
            sample_value=fact.subject,
            is_subject=True,
            predicate=fact.predicate,
            context_text=fact.source_text,
        )
        object_label, object_key = self._label_and_key_for_type(
            fact.object_type,
            sample_value=fact.object,
            is_subject=False,
            predicate=fact.predicate,
            context_text=fact.source_text,
        )

        if subject_label is None:
            logger.warning(f"Unknown subject type for fact: {fact.subject_type}")
            return False

        # Ensure subject node exists
        if not self._ensure_node(subject_label, subject_key, fact.subject):
            return False

        # If there is no object value or relationship, nothing else to insert
        if not fact.object or object_label is None:
            return True

        # Ensure and create the relationship
        return self._insert_typed_relationship(
            subject_label,
            subject_key,
            fact.subject,
            object_label,
            object_key,
            fact.object,
            relationship_type,
            fact,
        )

    def _label_and_key_for_type(
        self,
        entity_type: str,
        sample_value: Optional[str] = None,
        is_subject: bool = True,
        predicate: Optional[str] = None,
        context_text: Optional[str] = None,
    ):
        # Backwards-compatible wrapper that accepts optional inference parameters
        return self._label_and_key_for_type_with_sample(
            entity_type, sample_value, is_subject, predicate, context_text
        )

    def _label_and_key_for_type_with_sample(
        self,
        entity_type: str,
        sample_value: Optional[str],
        is_subject: bool,
        predicate: Optional[str],
        context_text: Optional[str],
    ):
        """Resolve a node label and key for a given entity type, with fallback inference.

        Args:
            entity_type: declared type (may be 'unknown')
            sample_value: a sample value (e.g., '1.335' or 'custom-log-source') to help infer
            is_subject: whether this is the subject side
            predicate: relationship predicate to help inference
        Returns: tuple(label, key) or (None, None) if unknown
        """
        if entity_type == "activegate":
            return "ActiveGateVersion", "version"
        if entity_type == "managed_cluster":
            return "ManagedClusterVersion", "version"
        if entity_type == "extension":
            return "Extension", "id"
        if entity_type == "os":
            return "OSVersion", None

        # Normalize context
        ctx = (context_text or "").lower()

        # Infer from sample value
        if sample_value:
            sv = str(sample_value).strip()
            # version-like -> choose ActiveGate for subjects, ManagedCluster for objects
            # Conservative numeric version handling:
            # - ActiveGate versions follow the 1.xxx pattern; prefer ActiveGate only for values starting with '1.'
            # - Other numeric patterns (e.g., '20.04', '16.04') are likely OS/distro versions; prefer OSVersion when context suggests OS
            version_match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?$", sv)
            if version_match:
                major = int(version_match.group(1))
                # ActiveGate versions use major == 1
                if sv.startswith("1."):
                    if is_subject:
                        return "ActiveGateVersion", "version"
                    else:
                        if ("managed" in ctx) or (
                            predicate
                            and predicate
                            in {
                                "REQUIRES",
                                "INCOMPATIBLE_WITH",
                                "DEPRECATED_IN",
                                "END_OF_SUPPORT",
                            }
                        ):
                            return "ManagedClusterVersion", "version"
                        return "ActiveGateVersion", "version"

                # Common distro/version patterns (Ubuntu 16.04/18.04/20.04/etc.)
                if major in {14, 16, 18, 20, 22, 24} or any(
                    tok in ctx
                    for tok in ["ubuntu", "centos", "rhel", "linux", "windows"]
                ):
                    return "OSVersion", None

                # Otherwise do not assume ActiveGate; leave unknown to avoid noisy nodes
                return None, None

            # OS-like
            if any(
                tok in sv.lower()
                for tok in [
                    "linux",
                    "ubuntu",
                    "centos",
                    "rhel",
                    "windows",
                    "kubernetes",
                ]
            ):
                return "OSVersion", None

        # Infer from context when sample_value is absent or ambiguous
        if not sample_value and ctx:
            if "activegate" in ctx or "active gate" in ctx or "ag " in ctx:
                return "ActiveGateVersion", "version"
            if (
                "dynatrace managed" in ctx
                or "managed cluster" in ctx
                or "managed version" in ctx
            ):
                return "ManagedClusterVersion", "version"
            if "extension" in ctx or "plugin" in ctx or "module" in ctx:
                return "Extension", "id"
            if any(
                tok in ctx
                for tok in [
                    "windows server",
                    "windows",
                    "linux",
                    "ubuntu",
                    "centos",
                    "rhel",
                    "kubernetes",
                ]
            ):
                return "OSVersion", None

            # Otherwise treat as extension id/name
            if sample_value and re.search(r"[a-zA-Z]", sv):
                return "Extension", "id"
            if not sample_value and re.search(r"[a-zA-Z]", ctx):
                return "Extension", "id"

        return None, None

    def _ensure_node(self, label: str, key: Optional[str], value: str) -> bool:
        try:
            if label == "ActiveGateVersion" and not re.match(
                r"^1\.\d+(?:\.\d+)?$", str(value).strip()
            ):
                return False

            if label == "OSVersion":
                os_properties = self._parse_os_properties(value)
                if os_properties is None:
                    return False
                query = (
                    "MERGE (os:OSVersion {os_name: $os_name, version: $version}) "
                    "SET os.last_seen = datetime()"
                )
                params = {
                    "os_name": os_properties["os_name"],
                    "version": os_properties["version"],
                }
            else:
                query = (
                    f"MERGE (n:{label} {{{key}: $value}}) SET n.last_seen = datetime()"
                )
                params = {"value": value}

            self.graph_conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"Error ensuring node {label}: {e}")
            return False

    def _parse_os_properties(self, value: str) -> Optional[Dict[str, str]]:
        if not value:
            return {"os_name": "unknown", "version": "unknown"}

        text = value.strip()
        patterns = [
            (r"(Windows Server)\s*(\d+(?:\.\d+)*)", "Windows Server"),
            (r"(Windows)\s*(\d+(?:\.\d+)*)", "Windows"),
            (
                r"(Red Hat Enterprise Linux CoreOS|RHCOS)\s*(\d+(?:\.\d+)*)",
                "Red Hat Enterprise Linux CoreOS",
            ),
            (
                r"(Red Hat Enterprise Linux|RHEL|Red Hat)\s*(\d+(?:\.\d+)*)",
                "Red Hat Enterprise Linux",
            ),
            (
                r"(SUSE Linux Enterprise Server|SLES)\s*(\d+(?:\.\d+)*)",
                "SUSE Linux Enterprise Server",
            ),
            (r"(CentOS Stream)\s*(\d+(?:\.\d+)*)", "CentOS Stream"),
            (r"(AlmaLinux)\s*(\d+(?:\.\d+)*)", "AlmaLinux"),
            (r"(Alpine Linux)\s*(\d+(?:\.\d+)*)", "Alpine Linux"),
            (r"(Amazon Linux)\s*(\d+(?:\.\d+)*)", "Amazon Linux"),
            (r"(Azure Linux)\s*(\d+(?:\.\d+)*)", "Azure Linux"),
            (r"(Bottlerocket)\s*(\d+(?:\.\d+)*)", "Bottlerocket"),
            (r"(Debian)\s*(\d+(?:\.\d+)*)", "Debian"),
            (r"(Fedora)\s*(\d+(?:\.\d+)*)", "Fedora"),
            (r"(Oracle Linux)\s*(\d+(?:\.\d+)*)", "Oracle Linux"),
            (r"(Rocky Linux)\s*(\d+(?:\.\d+)*)", "Rocky Linux"),
            (r"(Ubuntu)\s*(\d+(?:\.\d+)*)", "Ubuntu"),
            (r"(openSUSE)\s*(\d+(?:\.\d+)*)", "openSUSE"),
            (r"(CentOS)\s*(\d+(?:\.\d+)*)", "CentOS"),
            (r"(Linux)\s*(\d+(?:\.\d+)*)", "Linux"),
            (r"(Kubernetes)\s*(\d+\.\d+(?:\.\d+)*)", "Kubernetes"),
        ]

        for pattern, name in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return {"os_name": name, "version": match.group(2)}

        # Fallback: split into words and use first token as os_name
        tokens = text.split()
        if len(tokens) >= 2 and re.match(r"\d+(?:\.\d+)*", tokens[-1]):
            return {"os_name": " ".join(tokens[:-1]), "version": tokens[-1]}

        return {"os_name": text, "version": "unknown"}

    def _insert_typed_relationship(
        self,
        subject_label: str,
        subject_key: str,
        subject_value: str,
        object_label: str,
        object_key: Optional[str],
        object_value: str,
        relationship_type: str,
        fact: ExtractedFact,
    ) -> bool:
        try:
            if object_label == "OSVersion":
                os_properties = self._parse_os_properties(object_value)
                if os_properties is None:
                    return False
                object_clause = (
                    "(obj:OSVersion {os_name: $os_name, version: $os_version})"
                )
                params = {
                    "subject_value": subject_value,
                    "os_name": os_properties["os_name"],
                    "os_version": os_properties["version"],
                    "source_url": fact.source_url,
                    "confidence": fact.confidence,
                    "raw_text": fact.source_text,
                }
            elif object_key:
                object_clause = f"(obj:{object_label} {{{object_key}: $object_value}})"
                params = {
                    "subject_value": subject_value,
                    "object_value": object_value,
                    "source_url": fact.source_url,
                    "confidence": fact.confidence,
                    "raw_text": fact.source_text,
                }
            else:
                return False

            query = (
                f"MERGE (sub:{subject_label} {{{subject_key}: $subject_value}}) MERGE {object_clause} "
                f"MERGE (sub)-[r:{relationship_type}]->(obj) "
                "SET r.source_url = $source_url, r.confidence = $confidence, r.raw_text = $raw_text, r.updated_at = datetime() "
                "RETURN r"
            )
            self.graph_conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"Error inserting relationship {relationship_type}: {e}")
            return False

    def _insert_activegate_compatibility(
        self, fact: ExtractedFact, relationship_type: str
    ) -> bool:
        """Insert ActiveGate node and, when an object version exists, a typed relationship to it."""
        try:
            # Always ensure the subject ActiveGate node exists
            self.graph_conn.execute(
                "MERGE (ag:ActiveGateVersion {version: $version}) SET ag.last_seen = datetime()",
                {"version": fact.subject},
            )

            # If we have an object (related version), create the typed relationship
            if fact.object and fact.object != "activegate":
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (mc:ManagedClusterVersion {{version: $mc_version}})
                MERGE (ag)-[r:{relationship_type}]->(mc)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.raw_text    = $raw_text,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(
                    query,
                    {
                        "ag_version": fact.subject,
                        "mc_version": fact.object,
                        "source_url": fact.source_url,
                        "confidence": fact.confidence,
                        "raw_text": fact.source_text,
                    },
                )
            return True
        except Exception as e:
            logger.error(f"Error inserting ActiveGate compatibility: {e}")
            return False

    def _insert_os_compatibility(
        self, fact: ExtractedFact, relationship_type: str
    ) -> bool:
        """Insert OS node and link it to the ActiveGate version via SUPPORTED_BY."""
        try:
            os_properties = self._parse_os_properties(fact.subject or "")
            os_name = (os_properties or {}).get("os_name", "Unknown")
            os_ver = (os_properties or {}).get("version", "unknown")

            self.graph_conn.execute(
                "MERGE (os:OSVersion {os_name: $os_name, version: $version}) SET os.last_seen = datetime()",
                {"os_name": os_name, "version": os_ver},
            )

            if fact.object:
                query = """
                MERGE (ag:ActiveGateVersion {version: $ag_version})
                MERGE (os:OSVersion {os_name: $os_name, version: $os_version})
                MERGE (ag)-[r:SUPPORTED_BY]->(os)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(
                    query,
                    {
                        "ag_version": fact.object,
                        "os_name": os_name,
                        "os_version": os_ver,
                        "source_url": fact.source_url,
                        "confidence": fact.confidence,
                    },
                )
            return True
        except Exception as e:
            logger.error(f"Error inserting OS compatibility: {e}")
            return False

    def _insert_extension_compatibility(
        self, fact: ExtractedFact, relationship_type: str
    ) -> bool:
        """Insert Extension node and link to ActiveGate via the appropriate relationship."""
        try:
            ext_id = fact.subject or "unknown"
            ag_version = fact.object

            self.graph_conn.execute(
                "MERGE (ext:Extension {id: $ext_id}) SET ext.last_seen = datetime()",
                {"ext_id": ext_id},
            )

            if ag_version:
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (ext:Extension {{id: $ext_id}})
                MERGE (ag)-[r:{relationship_type}]->(ext)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(
                    query,
                    {
                        "ag_version": ag_version,
                        "ext_id": ext_id,
                        "source_url": fact.source_url,
                        "confidence": fact.confidence,
                    },
                )
            return True
        except Exception as e:
            logger.error(f"Error inserting extension compatibility: {e}")
            return False

    def _insert_managed_cluster_compatibility(
        self, fact: ExtractedFact, relationship_type: str
    ) -> bool:
        """Insert ManagedClusterVersion node and link to ActiveGate via the appropriate relationship."""
        try:
            self.graph_conn.execute(
                "MERGE (mc:ManagedClusterVersion {version: $version}) SET mc.last_seen = datetime()",
                {"version": fact.subject},
            )

            if fact.object:
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (mc:ManagedClusterVersion {{version: $mc_version}})
                MERGE (ag)-[r:{relationship_type}]->(mc)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(
                    query,
                    {
                        "ag_version": fact.object,
                        "mc_version": fact.subject,
                        "source_url": fact.source_url,
                        "confidence": fact.confidence,
                    },
                )
            return True
        except Exception as e:
            logger.error(f"Error inserting Managed cluster compatibility: {e}")
            return False

    def _insert_upgrade_path(self, fact: ExtractedFact) -> bool:
        """Insert an upgrade path (from version X to version Y)."""
        query = """
        MERGE (from_ag:ActiveGateVersion {version: $from_version})
        MERGE (to_ag:ActiveGateVersion {version: $to_version})
        MERGE (from_ag)-[r:UPGRADEABLE_TO {confidence: $confidence}]->(to_ag)
        SET r.source_url = $source_url, r.raw_text = $raw_text, r.created_at = datetime()
        RETURN from_ag, to_ag, r
        """

        try:
            result = self.graph_conn.execute(
                query,
                {
                    "from_version": fact.subject,
                    "to_version": fact.object,
                    "confidence": fact.confidence,
                    "source_url": fact.source_url,
                    "raw_text": fact.source_text,
                },
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting upgrade path: {e}")
            return False

    def create_compatibility_relationship(
        self,
        from_version: str,
        to_version: str,
        relationship_type: str,
        confidence: float,
        source_url: str,
    ) -> bool:
        """
        Create a compatibility relationship between two versions.

        Args:
            from_version: Source version (e.g., ActiveGate 1.335)
            to_version: Target version (e.g., Managed 1.335)
            relationship_type: Type of relationship (COMPATIBLE_WITH, REQUIRES, etc.)
            confidence: Confidence score (0.0-1.0)
            source_url: Source URL for provenance
        """
        query = f"""
        MATCH (from:ActiveGateVersion {{version: $from_version}})
        MATCH (to:ManagedClusterVersion {{version: $to_version}})
        MERGE (from)-[r:{relationship_type} {{confidence: $confidence}}]->(to)
        SET r.source_url = $source_url, r.created_at = datetime()
        RETURN r
        """

        try:
            result = self.graph_conn.execute(
                query,
                {
                    "from_version": from_version,
                    "to_version": to_version,
                    "confidence": confidence,
                    "source_url": source_url,
                },
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error creating compatibility relationship: {e}")
            return False

    def ingest_hub_catalog(
        self,
        items: List[Dict[str, Any]],
        min_verified_confidence: float = 0.7,
    ) -> Dict[str, int]:
        """Persist managed Hub items, releases, and extracted version constraints."""
        if not self.graph_conn.driver and not self.graph_conn.connect():
            raise RuntimeError("Failed to connect to Neo4j for Hub ingestion")

        summary = {
            "items_total": len(items),
            "items_upserted": 0,
            "releases_upserted": 0,
            "constraints_upserted": 0,
            "releases_skipped_incremental": 0,
            "inactive_marked": 0,
        }

        existing_items = self._count_hub_items()
        full_bootstrap = existing_items == 0
        active_hub_ids = set()

        for item in items:
            hub_id = item.get("hub_id") or item.get("slug")
            if not hub_id:
                continue

            active_hub_ids.add(hub_id)
            self._upsert_hub_item(item)
            summary["items_upserted"] += 1

            latest_seen_epoch = self._get_latest_release_epoch(hub_id)
            releases = item.get("releases") or []

            for release in releases:
                rel_epoch = release.get("published_at_epoch") or 0
                if (
                    not full_bootstrap
                    and latest_seen_epoch
                    and rel_epoch <= latest_seen_epoch
                ):
                    summary["releases_skipped_incremental"] += 1
                    continue

                self._upsert_hub_release(hub_id, item, release)
                summary["releases_upserted"] += 1

                for constraint in release.get("constraints", []):
                    self._upsert_release_constraint(
                        hub_id,
                        release,
                        constraint,
                        min_verified_confidence=min_verified_confidence,
                    )
                    summary["constraints_upserted"] += 1

        summary["inactive_marked"] = self._mark_missing_hub_items_inactive(
            active_hub_ids
        )
        self._upsert_hub_ingestion_meta(
            expected_count=len(items),
            active_count=len(active_hub_ids),
            min_verified_confidence=min_verified_confidence,
        )
        return summary

    def get_hub_coverage_summary(self) -> Dict[str, Any]:
        """Return Hub ingestion coverage and health metadata for UI/API display."""
        query = """
        OPTIONAL MATCH (meta:HubIngestionMeta {name: 'managed'})
        OPTIONAL MATCH (item:HubItem)
        WITH meta,
             count(item) AS total_items,
             count(CASE WHEN coalesce(item.active, true) THEN 1 END) AS active_items,
             count(CASE WHEN item.extension_type = 'extension-2' THEN 1 END) AS extension2_items
        RETURN
            total_items,
            active_items,
            extension2_items,
            meta.expected_count AS expected_count,
            meta.last_ingested_at AS last_ingested_at,
            meta.min_verified_confidence AS min_verified_confidence,
            meta.status AS status
        """
        result = self.graph_conn.execute(query)
        if not result:
            return {
                "total_items": 0,
                "active_items": 0,
                "extension2_items": 0,
                "expected_count": 0,
                "last_ingested_at": None,
                "min_verified_confidence": None,
                "status": "NO_DATA",
                "count_mismatch": 0,
            }

        row = result[0]
        expected = row.get("expected_count") or 0
        active = row.get("active_items") or 0
        return {
            "total_items": row.get("total_items") or 0,
            "active_items": active,
            "extension2_items": row.get("extension2_items") or 0,
            "expected_count": expected,
            "last_ingested_at": (
                str(row.get("last_ingested_at"))
                if row.get("last_ingested_at")
                else None
            ),
            "min_verified_confidence": row.get("min_verified_confidence"),
            "status": row.get("status") or "UNKNOWN",
            "count_mismatch": abs(expected - active),
        }

    def _count_hub_items(self) -> int:
        query = "MATCH (item:HubItem) RETURN count(item) AS c"
        result = self.graph_conn.execute(query)
        return int(result[0]["c"]) if result else 0

    def _upsert_hub_item(self, item: Dict[str, Any]) -> None:
        query = """
        MERGE (item:HubItem {id: $id})
        SET item.slug = $slug,
            item.title = $title,
            item.description = $description,
            item.extension_type = $extension_type,
            item.managed = $managed,
            item.supported_by_dt = $supported_by_dt,
            item.details_url = $details_url,
            item.feed_url = $feed_url,
            item.feed_status = $feed_status,
            item.release_latest_version = $release_latest_version,
            item.active = true,
            item.last_seen = datetime(),
            item.updated_at = datetime()
        """
        self.graph_conn.execute(
            query,
            {
                "id": item.get("hub_id") or item.get("slug"),
                "slug": item.get("slug"),
                "title": item.get("title") or item.get("slug"),
                "description": item.get("description") or "",
                "extension_type": item.get("extension_type") or "unknown",
                "managed": bool(item.get("managed", True)),
                "supported_by_dt": bool(item.get("supported_by_dt", False)),
                "details_url": item.get("details_url") or "",
                "feed_url": item.get("feed_url") or "",
                "feed_status": item.get("feed_status") or "missing",
                "release_latest_version": item.get("release_latest_version"),
            },
        )

    def _get_latest_release_epoch(self, hub_id: str) -> int:
        query = """
        MATCH (item:HubItem {id: $id})-[:HAS_RELEASE]->(release:HubItemRelease)
        RETURN coalesce(max(release.published_at_epoch), 0) AS latest_epoch
        """
        result = self.graph_conn.execute(query, {"id": hub_id})
        if not result:
            return 0
        return int(result[0].get("latest_epoch") or 0)

    def _upsert_hub_release(
        self, hub_id: str, item: Dict[str, Any], release: Dict[str, Any]
    ) -> None:
        release_version = release.get("version") or release.get("title") or "unknown"
        query = """
        MERGE (item:HubItem {id: $item_id})
        MERGE (release:HubItemRelease {item_id: $item_id, version: $version})
        SET release.title = $title,
            release.source_url = $source_url,
            release.raw_description = $raw_description,
            release.published_at = $published_at,
            release.published_at_epoch = $published_at_epoch,
            release.last_seen = datetime(),
            release.updated_at = datetime()
        MERGE (item)-[:HAS_RELEASE]->(release)
        """
        self.graph_conn.execute(
            query,
            {
                "item_id": hub_id,
                "version": release_version,
                "title": release.get("title") or release_version,
                "source_url": release.get("source_url") or item.get("details_url", ""),
                "raw_description": release.get("raw_description") or "",
                "published_at": release.get("published_at"),
                "published_at_epoch": release.get("published_at_epoch"),
            },
        )

    def _upsert_release_constraint(
        self,
        hub_id: str,
        release: Dict[str, Any],
        constraint: Dict[str, Any],
        min_verified_confidence: float,
    ) -> None:
        component = constraint.get("component")
        min_version = constraint.get("min_version")
        if not component or not min_version:
            return

        relationship_type = (
            "REQUIRES_ACTIVEGATE"
            if component == "activegate"
            else "REQUIRES_MANAGED" if component == "managed_cluster" else None
        )
        target_label = (
            "ActiveGateVersion"
            if component == "activegate"
            else "ManagedClusterVersion" if component == "managed_cluster" else None
        )
        if not relationship_type or not target_label:
            return

        release_version = release.get("version") or release.get("title") or "unknown"
        confidence = float(constraint.get("confidence") or 0.0)
        verified = confidence >= min_verified_confidence

        query = f"""
        MERGE (release:HubItemRelease {{item_id: $item_id, version: $release_version}})
        MERGE (target:{target_label} {{version: $min_version}})
        MERGE (release)-[r:{relationship_type} {{operator: $operator, min_version: $min_version}}]->(target)
        SET r.confidence = $confidence,
            r.verified = $verified,
            r.threshold = $threshold,
            r.source_url = $source_url,
            r.raw_text = $raw_text,
            r.updated_at = datetime()
        """

        self.graph_conn.execute(
            query,
            {
                "item_id": hub_id,
                "release_version": release_version,
                "min_version": min_version,
                "operator": constraint.get("operator") or ">=",
                "confidence": confidence,
                "verified": verified,
                "threshold": min_verified_confidence,
                "source_url": constraint.get("source_url")
                or release.get("source_url", ""),
                "raw_text": constraint.get("raw_text") or "",
            },
        )

    def _mark_missing_hub_items_inactive(self, active_hub_ids: set) -> int:
        if not active_hub_ids:
            return 0
        query = """
        MATCH (item:HubItem)
        WHERE NOT item.id IN $active_ids
        SET item.active = false,
            item.updated_at = datetime()
        RETURN count(item) AS c
        """
        result = self.graph_conn.execute(query, {"active_ids": list(active_hub_ids)})
        return int(result[0]["c"]) if result else 0

    def _upsert_hub_ingestion_meta(
        self,
        expected_count: int,
        active_count: int,
        min_verified_confidence: float,
    ) -> None:
        status = "HEALTHY" if expected_count == active_count else "DEGRADED"
        query = """
        MERGE (meta:HubIngestionMeta {name: 'managed'})
        SET meta.expected_count = $expected_count,
            meta.active_count = $active_count,
            meta.status = $status,
            meta.min_verified_confidence = $min_verified_confidence,
            meta.last_ingested_at = datetime()
        """
        self.graph_conn.execute(
            query,
            {
                "expected_count": expected_count,
                "active_count": active_count,
                "status": status,
                "min_verified_confidence": min_verified_confidence,
            },
        )
