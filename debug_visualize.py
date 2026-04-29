#!/usr/bin/env python3
"""
Debug script to visualize the ActiveGate compatibility graph.

This script can work in two modes:
1. Connected mode: Connects to Neo4j and fetches real data
2. Demo mode: Uses sample data to demonstrate the visualization

Usage:
    python debug_visualize.py                    # Demo mode with sample data
    python debug_visualize.py --connected         # Connect to Neo4j
    python debug_visualize.py --versions 1.330   # Filter specific versions
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.graph_visualizer import GraphVisualizer, GraphVisualizationData


def get_demo_data() -> GraphVisualizationData:
    """
    Generate demo data to show the visualization capabilities
    when Neo4j is not available.
    """
    return GraphVisualizationData(
        nodes={
            'ActiveGateVersion': ['1.280', '1.290', '1.300', '1.310', '1.320', '1.325', '1.330', '1.335'],
            'ManagedClusterVersion': ['1.280', '1.290', '1.300', '1.310', '1.320', '1.330', '1.335'],
            'OSVersion': ['Windows 2019', 'Windows 2022', 'Linux RHEL 8', 'Linux RHEL 9', 'Ubuntu 22.04'],
            'Extension': ['custom-logging', 'custom-metrics', 'aws-monitoring', 'azure-monitoring'],
            'Module': ['aws-module', 'azure-module', 'gcp-module'],
            'Setting': ['proxy-settings', 'ssl-settings', 'monitoring-settings']
        },
        relationships=[
            {'source': '1.280', 'source_type': 'ActiveGateVersion', 'target': '1.280', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.290', 'source_type': 'ActiveGateVersion', 'target': '1.290', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.300', 'source_type': 'ActiveGateVersion', 'target': '1.300', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.310', 'source_type': 'ActiveGateVersion', 'target': '1.310', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.320', 'source_type': 'ActiveGateVersion', 'target': '1.320', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': '1.330', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': '1.335', 'target_type': 'ManagedClusterVersion', 'relationship': 'REQUIRES'},
            {'source': '1.300', 'source_type': 'ActiveGateVersion', 'target': '1.280', 'target_type': 'ManagedClusterVersion', 'relationship': 'DEPRECATED_IN'},
            {'source': '1.310', 'source_type': 'ActiveGateVersion', 'target': '1.290', 'target_type': 'ManagedClusterVersion', 'relationship': 'DEPRECATED_IN'},
            {'source': '1.320', 'source_type': 'ActiveGateVersion', 'target': '1.300', 'target_type': 'ManagedClusterVersion', 'relationship': 'DEPRECATED_IN'},
            {'source': '1.280', 'source_type': 'ActiveGateVersion', 'target': '1.280', 'target_type': 'ManagedClusterVersion', 'relationship': 'END_OF_SUPPORT'},
            {'source': '1.290', 'source_type': 'ActiveGateVersion', 'target': '1.290', 'target_type': 'ManagedClusterVersion', 'relationship': 'END_OF_SUPPORT'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': 'custom-logging', 'target_type': 'Extension', 'relationship': 'COMPATIBLE_WITH'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': 'custom-logging', 'target_type': 'Extension', 'relationship': 'COMPATIBLE_WITH'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': 'custom-metrics', 'target_type': 'Extension', 'relationship': 'COMPATIBLE_WITH'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': 'custom-metrics', 'target_type': 'Extension', 'relationship': 'COMPATIBLE_WITH'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': 'Windows 2019', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': 'Windows 2022', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
            {'source': '1.330', 'source_type': 'ActiveGateVersion', 'target': 'Linux RHEL 8', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': 'Windows 2022', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': 'Linux RHEL 9', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
            {'source': '1.335', 'source_type': 'ActiveGateVersion', 'target': 'Ubuntu 22.04', 'target_type': 'OSVersion', 'relationship': 'SUPPORTED_BY'},
        ]
    )


def main():
    parser = argparse.ArgumentParser(description='Visualize the ActiveGate compatibility graph')
    parser.add_argument('--connected', action='store_true', help='Connect to Neo4j (requires environment variables)')
    parser.add_argument('--versions', '-v', default=None, help='Comma-separated list of ActiveGate versions')
    parser.add_argument('--format', '-f', default='mermaid', choices=['mermaid', 'flowchart', 'text'], help='Output format')
    parser.add_argument('--limit', '-l', type=int, default=50, help='Maximum number of versions')
    
    args = parser.parse_args()
    
    visualizer = GraphVisualizer()
    
    # Parse versions
    version_list = None
    if args.versions:
        version_list = [v.strip() for v in args.versions.split(',')]
    
    # Get data
    if args.connected:
        try:
            print("Connecting to Neo4j...")
            data = visualizer.get_graph_data(activegate_versions=version_list, limit=args.limit)
        except Exception as e:
            print(f"Error connecting to Neo4j: {e}")
            print("Falling back to demo mode...")
            data = get_demo_data()
    else:
        print("Using demo data (no Neo4j connection)...")
        data = get_demo_data()
    
    # Generate output
    if args.format == 'mermaid':
        output = visualizer.to_mermaid(data)
    elif args.format == 'flowchart':
        output = visualizer.to_mermaid_flowchart(data)
    else:
        output = visualizer.to_text_diagram(data)
    
    print("\n" + "=" * 60)
    print("VISUALIZATION OUTPUT")
    print("=" * 60 + "\n")
    print(output)


if __name__ == '__main__':
    main()