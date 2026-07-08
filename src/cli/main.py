#!/usr/bin/env python3
"""
ActiveGate Compatibility Intelligence CLI
Command-line interface for checking ActiveGate upgrade compatibility.
"""

import json
import os
from pathlib import Path

import click
import yaml

from src.reasoning.citation_generator import QueryProcessor
from src.reasoning.compatibility_reasoner import CompatibilityReasoner
from src.storage.graph_connection import GraphConnection
from src.storage.graph_query import GraphQuery
from src.storage.graph_visualizer import GraphVisualizer


def _make_graph_connection() -> GraphConnection:
    return GraphConnection(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )


def _initialize_components():
    graph_conn = _make_graph_connection()
    connected = graph_conn.connect()
    if connected:
        graph_query = GraphQuery(graph_conn)
    else:
        graph_query = None

    reasoner = CompatibilityReasoner(graph_query=graph_query)
    query_processor = QueryProcessor(reasoner)

    return graph_conn, graph_query, reasoner, query_processor


# Initialize components
graph_conn, graph_query, reasoner, query_processor = _initialize_components()
connected = graph_query is not None


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """ActiveGate Compatibility Intelligence CLI.

    Check if your ActiveGate upgrade path is compatible with your environment.
    """
    pass


@cli.command()
@click.option(
    "--current", "-c", required=True, help="Current ActiveGate version (e.g., 1.330)"
)
@click.option(
    "--target", "-t", required=True, help="Target ActiveGate version (e.g., 1.335)"
)
@click.option(
    "--os-family", "-o", default=None, help="Operating system family (windows, linux)"
)
@click.option(
    "--os-version", default=None, help="Operating system version (e.g., 2022, 8)"
)
@click.option("--managed", "-m", default=None, help="Dynatrace Managed cluster version")
@click.option(
    "--extensions",
    "-e",
    multiple=True,
    help="Extensions to check (format: ext-id:version)",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def check(current, target, os_family, os_version, managed, extensions, json_output):
    """Check ActiveGate upgrade compatibility.

    Examples:
        agi check -c 1.330 -t 1.335
        agi check -c 1.330 -t 1.335 -o linux -8
        agi check -c 1.330 -t 1.335 -m 1.335 -e custom-ext:2.0
    """
    # Parse extensions
    ext_list = []
    for ext in extensions:
        if ":" in ext:
            ext_id, ext_ver = ext.split(":", 1)
            ext_list.append({"id": ext_id, "version": ext_ver})

    # Run compatibility check
    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed,
        extensions=ext_list if ext_list else None,
    )

    # Output results
    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        output = query_processor.format_result_for_display(result)
        click.echo(output)


@cli.command()
@click.argument("query")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def ask(query, json_output):
    """Ask a natural language question about compatibility.

    Examples:
        agi ask "Can I upgrade from 1.330 to 1.335?"
        agi ask "Is extension custom-logging compatible with AG 1.335?"
    """
    # Process the query
    parsed = query_processor.process_query(query)

    # Extract version from query
    versions = parsed.get("versions_found", [])

    if len(versions) >= 2:
        current = versions[0]
        target = versions[1]
    elif len(versions) == 1:
        current = "1.330"  # Default
        target = versions[0]
    else:
        click.echo(
            "Could not detect version in query. Please use format: 'Can I upgrade from X to Y?'"
        )
        return

    # Run compatibility check
    result = reasoner.check_upgrade_compatibility(
        current_version=current, target_version=target
    )

    # Output results
    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"\nQuery: {query}")
        click.echo(f"Detected versions: {current} -> {target}\n")
        output = query_processor.format_result_for_display(result)
        click.echo(output)


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def check_file(file_path, json_output):
    """Check compatibility using a configuration file.

    The file should be in YAML or JSON format with the following structure:

    Example YAML:
        current_activegate_version: 1.330
        target_activegate_version: 1.335
        os_family: linux
        os_version: "8"
        managed_cluster_version: 1.335
        extensions:
          - id: custom-logging
            version: "2.0"
          - id: custom-metrics
            version: "1.5"
    """
    # Load configuration file
    file_path = Path(file_path)

    try:
        with open(file_path, "r") as f:
            if file_path.suffix in [".yaml", ".yml"]:
                config = yaml.safe_load(f)
            elif file_path.suffix == ".json":
                config = json.load(f)
            else:
                click.echo("Error: File must be YAML or JSON format")
                return
    except Exception as e:
        click.echo(f"Error reading file: {e}")
        return

    # Parse structured input
    params = query_processor.parse_structured_input(config)

    # Run compatibility check
    result = reasoner.check_upgrade_compatibility(
        current_version=params["current_version"],
        target_version=params["target_version"],
        os_family=params.get("os_family"),
        os_version=params.get("os_version"),
        managed_cluster_version=params.get("managed_cluster_version"),
        extensions=params.get("extensions"),
    )

    # Output results
    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"\nConfiguration file: {file_path}\n")
        output = query_processor.format_result_for_display(result)
        click.echo(output)


@cli.command()
def version():
    """Show version information."""
    click.echo("ActiveGate Compatibility Intelligence CLI v1.0.0")
    click.echo("Part of ActiveGate Compatibility Intelligence System")


@cli.command()
def status():
    """Show system status and available data."""
    click.echo("=== ActiveGate Compatibility Intelligence ===")
    click.echo("")
    if connected:
        click.echo("Neo4j Status: Connected")
        try:
            stats = graph_conn.get_stats()
            click.echo(
                f"ActiveGate versions: {stats.get('ActiveGateVersion_count', 0)}"
            )
            click.echo(
                f"Managed cluster versions: {stats.get('ManagedClusterVersion_count', 0)}"
            )
            click.echo(f"OS versions: {stats.get('OSVersion_count', 0)}")
            click.echo(f"Extensions: {stats.get('Extension_count', 0)}")
            click.echo(f"Total relationships: {stats.get('relationships_count', 0)}")
        except Exception as e:
            click.echo(f"Failed to query Neo4j stats: {e}")
    else:
        click.echo("Neo4j Status: Disconnected")
        click.echo(
            "  Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE and ensure Neo4j is running."
        )

    click.echo("")
    click.echo("Known deprecated versions:")
    click.echo("  - 1.300, 1.310, 1.320, 1.325")
    click.echo("")
    click.echo("Known end-of-support versions:")
    click.echo("  - 1.280, 1.290, 1.300")
    click.echo("")
    click.echo("Supported OS families:")
    click.echo("  - Windows (2016, 2019, 2022)")
    click.echo("  - Linux (RHEL 7.x, 8.x, 9.x, CentOS 7.x, 8.x, Ubuntu 20.04, 22.04)")


@cli.command()
@click.option(
    "--versions",
    "-v",
    default=None,
    help='Comma-separated list of ActiveGate versions to visualize (e.g., "1.330,1.335")',
)
@click.option(
    "--format",
    "-f",
    "output_format",
    default="mermaid",
    type=click.Choice(["mermaid", "flowchart", "text"]),
    help="Output format",
)
@click.option("--limit", "-l", default=50, help="Maximum number of versions to include")
def visualize(versions, output_format, limit):
    """Visualize the ActiveGate compatibility graph.

    This command queries the Neo4j graph database and generates a visualization
    showing the relationships between ActiveGate versions, Managed clusters,
    OS versions, and extensions.

    Examples:
        agi visualize
        agi visualize --format text
        agi visualize -v 1.330,1.335 -f mermaid
    """
    # Parse versions if provided
    version_list = None
    if versions:
        version_list = [v.strip() for v in versions.split(",")]

    try:
        visualizer = GraphVisualizer()
        data = visualizer.get_graph_data(activegate_versions=version_list, limit=limit)

        if output_format == "mermaid":
            output = visualizer.to_mermaid(data)
        elif output_format == "flowchart":
            output = visualizer.to_mermaid_flowchart(data)
        elif output_format == "text":
            output = visualizer.to_text_diagram(data)

        click.echo(output)

    except Exception as e:
        click.echo(f"Error generating visualization: {e}")
        click.echo("")
        click.echo("Make sure Neo4j is running and environment variables are set:")
        click.echo("  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE")


# Create a template config file
@cli.command()
@click.argument("output_path", type=click.Path())
def init_config(output_path):
    """Create a template configuration file."""
    template = {
        "current_activegate_version": "1.330",
        "target_activegate_version": "1.335",
        "os_family": "linux",
        "os_version": "8",
        "managed_cluster_version": "1.335",
        "extensions": [
            {"id": "custom-logging", "version": "2.0"},
            {"id": "custom-metrics", "version": "1.5"},
        ],
    }

    output_path = Path(output_path)

    try:
        with open(output_path, "w") as f:
            yaml.dump(template, f, default_flow_style=False)
        click.echo(f"Template configuration created at: {output_path}")
    except Exception as e:
        click.echo(f"Error creating file: {e}")


if __name__ == "__main__":
    cli()
