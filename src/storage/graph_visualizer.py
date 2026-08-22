"""
Graph Visualization Module

Provides tools to visualize the Neo4j graph showing ActiveGate compatibility relationships.
Can output as Mermaid diagram format for rendering in various tools.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from neo4j import Session

from src.storage.connection_manager import get_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GraphVisualizationData:
    """Container for graph visualization data."""

    nodes: Dict[str, List[str]]  # node_type -> list of node values
    relationships: List[Dict]  # list of relationship dicts


class GraphVisualizer:
    """
    Generates visualizations of the ActiveGate compatibility graph.
    """

    def __init__(self, mgr: Optional["object"] = None):
        self._mgr = mgr or get_manager()

    def _get_connection(self) -> "object":
        if not self._mgr.is_connected:
            self._mgr.connect()
        return self._mgr

    # -- keep the old alias for compatibility ---------------------------------
    @property
    def graph_conn(self):  # type: ignore[no-redef]
        """Backwards-compat property so existing code still works."""
        return self._get_connection()

    @graph_conn.setter
    def graph_conn(self, val):  # type: ignore[no-redef]
        self._mgr = val

    def get_graph_data(
        self, activegate_versions: Optional[List[str]] = None, limit: int = 50
    ) -> GraphVisualizationData:
        """
        Fetch graph data from Neo4j for visualization.

        Args:
            activegate_versions: Optional list of specific ActiveGate versions to query.
                                 If None, fetches all versions.
            limit: Maximum number of relationships to fetch.

        Returns:
            GraphVisualizationData object containing nodes and relationships.
        """
        conn = self._get_connection()

        nodes = {
            "ActiveGateVersion": [],
            "ManagedClusterVersion": [],
            "OSVersion": [],
            "Extension": [],
            "Module": [],
            "Setting": [],
        }
        relationships = []

        # Fetch ActiveGate versions
        if activegate_versions:
            for version in activegate_versions:
                query = "MATCH (ag:ActiveGateVersion {version: $version}) RETURN ag"
                result = conn.execute(query, {"version": version})
                for record in result:
                    nodes["ActiveGateVersion"].append(record["ag"]["version"])
        else:
            # Fetch all ActiveGate versions
            query = "MATCH (ag:ActiveGateVersion) RETURN ag ORDER BY ag.version LIMIT $limit"
            result = conn.execute(query, {"limit": limit})
            for record in result:
                nodes["ActiveGateVersion"].append(record["ag"]["version"])

        # Fetch relationships for the ActiveGate versions
        if nodes["ActiveGateVersion"]:
            versions_str = ", ".join([f"'{v}'" for v in nodes["ActiveGateVersion"]])

            # Fetch REQUIRES relationships (to ManagedClusterVersion)
            requires_query = f"""
            MATCH (ag:ActiveGateVersion)-[r:REQUIRES]->(mc:ManagedClusterVersion)
            WHERE ag.version IN [{versions_str}]
            RETURN ag.version as source, mc.version as target, type(r) as rel_type
            """
            result = conn.execute(requires_query, {})
            for record in result:
                relationships.append(
                    {
                        "source": record["source"],
                        "source_type": "ActiveGateVersion",
                        "target": record["target"],
                        "target_type": "ManagedClusterVersion",
                        "relationship": record["rel_type"],
                    }
                )
                if record["target"] not in nodes["ManagedClusterVersion"]:
                    nodes["ManagedClusterVersion"].append(record["target"])

            # Fetch COMPATIBLE_WITH relationships (to Extension)
            compat_query = f"""
            MATCH (ag:ActiveGateVersion)-[r:COMPATIBLE_WITH]->(ext:Extension)
            WHERE ag.version IN [{versions_str}]
            RETURN ag.version as source, ext.id as target, type(r) as rel_type
            LIMIT 100
            """
            result = conn.execute(compat_query, {})
            for record in result:
                relationships.append(
                    {
                        "source": record["source"],
                        "source_type": "ActiveGateVersion",
                        "target": record["target"],
                        "target_type": "Extension",
                        "relationship": record["rel_type"],
                    }
                )
                if record["target"] not in nodes["Extension"]:
                    nodes["Extension"].append(record["target"])

            # Fetch SUPPORTED_BY relationships (to OSVersion)
            os_query = f"""
            MATCH (ag:ActiveGateVersion)-[r:SUPPORTED_BY]->(os:OSVersion)
            WHERE ag.version IN [{versions_str}]
            RETURN ag.version as source, os.os_name + ' ' + os.version as target, type(r) as rel_type
            """
            result = conn.execute(os_query, {})
            for record in result:
                relationships.append(
                    {
                        "source": record["source"],
                        "source_type": "ActiveGateVersion",
                        "target": record["target"],
                        "target_type": "OSVersion",
                        "relationship": record["rel_type"],
                    }
                )
                if record["target"] not in nodes["OSVersion"]:
                    nodes["OSVersion"].append(record["target"])

            # Fetch DEPRECATED_IN relationships
            deprec_query = f"""
            MATCH (ag:ActiveGateVersion)-[r:DEPRECATED_IN]->(mc:ManagedClusterVersion)
            WHERE ag.version IN [{versions_str}]
            RETURN ag.version as source, mc.version as target, type(r) as rel_type
            """
            result = conn.execute(deprec_query, {})
            for record in result:
                relationships.append(
                    {
                        "source": record["source"],
                        "source_type": "ActiveGateVersion",
                        "target": record["target"],
                        "target_type": "ManagedClusterVersion",
                        "relationship": record["rel_type"],
                    }
                )

            # Fetch END_OF_SUPPORT relationships
            eos_query = f"""
            MATCH (ag:ActiveGateVersion)-[r:END_OF_SUPPORT]->(mc:ManagedClusterVersion)
            WHERE ag.version IN [{versions_str}]
            RETURN ag.version as source, mc.version as target, type(r) as rel_type
            """
            result = conn.execute(eos_query, {})
            for record in result:
                relationships.append(
                    {
                        "source": record["source"],
                        "source_type": "ActiveGateVersion",
                        "target": record["target"],
                        "target_type": "ManagedClusterVersion",
                        "relationship": record["rel_type"],
                    }
                )

        return GraphVisualizationData(nodes=nodes, relationships=relationships)

    def to_mermaid(self, data: GraphVisualizationData) -> str:
        """
        Convert graph data to Mermaid diagram syntax.

        Args:
            data: GraphVisualizationData to convert

        Returns:
            Mermaid diagram as string
        """
        lines = ["graph TD"]

        # Add nodes with styling based on type
        for node_type, values in data.nodes.items():
            for value in values:
                # Create a safe node ID
                node_id = self._sanitize_id(f"{node_type}_{value}")
                node_label = value

                # Determine shape based on node type
                if node_type == "ActiveGateVersion":
                    lines.append(f'    {node_id}["{node_label}"]')
                elif node_type == "ManagedClusterVersion":
                    lines.append(f'    {node_id}["{node_label}"]')
                elif node_type == "Extension":
                    lines.append(f'    {node_id}["{node_label}"]')
                elif node_type == "OSVersion":
                    lines.append(f"    {node_id}[{node_label}]")
                elif node_type == "Module":
                    lines.append(f"    {node_id}[{node_label}]")
                elif node_type == "Setting":
                    lines.append(f"    {node_id}[{node_label}]")

        lines.append("")

        # Add relationships
        for rel in data.relationships:
            source_id = self._sanitize_id(f"{rel['source_type']}_{rel['source']}")
            target_id = self._sanitize_id(f"{rel['target_type']}_{rel['target']}")

            # Add relationship label
            rel_label = rel["relationship"]
            lines.append(f"    {source_id} -->|{rel_label}| {target_id}")

        lines.append("")

        # Add styling
        lines.append("    %% Styling")
        lines.append("    classDef ag fill:#f9f,stroke:#333,stroke-width:2px")
        lines.append("    classDef mc fill:#bbf,stroke:#333,stroke-width:2px")
        lines.append("    classDef ext fill:#bfb,stroke:#333,stroke-width:2px")
        lines.append("    classDef os fill:#ffb,stroke:#333,stroke-width:2px")

        # Apply classes
        for version in data.nodes.get("ActiveGateVersion", []):
            node_id = self._sanitize_id(f"ActiveGateVersion_{version}")
            lines.append(f"    class {node_id} ag")

        for version in data.nodes.get("ManagedClusterVersion", []):
            node_id = self._sanitize_id(f"ManagedClusterVersion_{version}")
            lines.append(f"    class {node_id} mc")

        for ext in data.nodes.get("Extension", []):
            node_id = self._sanitize_id(f"Extension_{ext}")
            lines.append(f"    class {node_id} ext")

        for os in data.nodes.get("OSVersion", []):
            node_id = self._sanitize_id(f"OSVersion_{os}")
            lines.append(f"    class {node_id} os")

        return "\n".join(lines)

    def to_mermaid_flowchart(self, data: GraphVisualizationData) -> str:
        """
        Convert graph data to a more compact Mermaid flowchart showing upgrade paths.

        Args:
            data: GraphVisualizationData to convert

        Returns:
            Mermaid flowchart diagram as string
        """
        lines = ["flowchart LR"]
        lines.append("    %% Upgrade path visualization")

        # Group ActiveGate versions by their relationships
        ag_versions = data.nodes.get("ActiveGateVersion", [])
        mc_versions = data.nodes.get("ManagedClusterVersion", [])

        # Create subgraph for ActiveGate versions
        lines.append("    subgraph ActiveGates")
        for version in ag_versions:
            lines.append(f'        AG_{version.replace(".", "_")}["{version}"]')
        lines.append("    end")

        # Create subgraph for Managed Cluster versions
        lines.append("    subgraph ManagedClusters")
        for version in mc_versions:
            lines.append(f'        MC_{version.replace(".", "_")}["{version}"]')
        lines.append("    end")

        lines.append("")

        # Add relationships
        for rel in data.relationships:
            if rel["relationship"] == "REQUIRES":
                source = rel["source"].replace(".", "_")
                target = rel["target"].replace(".", "_")
                lines.append(f"    AG_{source} --> MC_{target}")
            elif rel["relationship"] == "COMPATIBLE_WITH":
                source = rel["source"].replace(".", "_")
                target = rel["target"].replace(".", "_")
                lines.append(f"    AG_{source} -.->|compatible| Ext_{target}")

        return "\n".join(lines)

    def _sanitize_id(self, raw_id: str) -> str:
        """Convert a raw ID to a safe Mermaid node ID."""
        # Replace special characters with underscores
        safe = (
            raw_id.replace(".", "_")
            .replace("-", "_")
            .replace(":", "_")
            .replace(" ", "_")
        )
        return safe

    def to_text_diagram(self, data: GraphVisualizationData) -> str:
        """
        Generate a simple text-based diagram of the graph.

        Args:
            data: GraphVisualizationData to convert

        Returns:
            Text diagram as string
        """
        lines = []
        lines.append("=" * 60)
        lines.append("ActiveGate Compatibility Graph")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        total_nodes = sum(len(v) for v in data.nodes.values())
        lines.append(f"Total nodes: {total_nodes}")
        lines.append(f"Total relationships: {len(data.relationships)}")
        lines.append("")

        # Nodes by type
        lines.append("NODES:")
        lines.append("-" * 40)
        for node_type, values in data.nodes.items():
            if values:
                lines.append(f"\n  {node_type} ({len(values)}):")
                for value in values[:10]:  # Limit to 10 per type
                    lines.append(f"    - {value}")
                if len(values) > 10:
                    lines.append(f"    ... and {len(values) - 10} more")

        lines.append("")

        # Relationships
        lines.append("\nRELATIONSHIPS:")
        lines.append("-" * 40)

        rel_counts = {}
        for rel in data.relationships:
            key = rel["relationship"]
            rel_counts[key] = rel_counts.get(key, 0) + 1

        for rel_type, count in sorted(rel_counts.items()):
            lines.append(f"  {rel_type}: {count}")

        lines.append("")

        # Sample relationships
        lines.append("\nSample relationships:")
        for rel in data.relationships[:20]:
            lines.append(
                f"  {rel['source']} --[{rel['relationship']}]--> {rel['target']}"
            )

        if len(data.relationships) > 20:
            lines.append(f"  ... and {len(data.relationships) - 20} more")

        return "\n".join(lines)


def visualize_graph(
    activegate_versions: Optional[List[str]] = None,
    output_format: str = "mermaid",
    limit: int = 50,
) -> str:
    """
    Main function to visualize the ActiveGate compatibility graph.

    Args:
        activegate_versions: Optional list of specific ActiveGate versions to visualize.
        output_format: Output format - 'mermaid', 'flowchart', or 'text'
        limit: Maximum number of versions to include

    Returns:
        Visualization as string
    """
    visualizer = GraphVisualizer()
    data = visualizer.get_graph_data(
        activegate_versions=activegate_versions, limit=limit
    )

    if output_format == "mermaid":
        return visualizer.to_mermaid(data)
    elif output_format == "flowchart":
        return visualizer.to_mermaid_flowchart(data)
    elif output_format == "text":
        return visualizer.to_text_diagram(data)
    else:
        raise ValueError(f"Unknown output format: {output_format}")


if __name__ == "__main__":
    import sys

    # Simple CLI
    if len(sys.argv) > 1:
        versions = sys.argv[1].split(",") if sys.argv[1] else None
    else:
        versions = None

    output = visualize_graph(versions)
    print(output)
