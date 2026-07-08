#!/usr/bin/env python3
"""
Test script for reasoning engine.
Tests compatibility checking, semantic search, and citation generation.
"""

from src.reasoning.citation_generator import CitationGenerator, QueryProcessor
from src.reasoning.compatibility_reasoner import CompatibilityReasoner
from src.reasoning.semantic_search import HistoricalQuery, SemanticSearch


def test_compatibility_reasoner():
    """Test the core compatibility reasoner."""
    print("=" * 60)
    print("Testing Compatibility Reasoner")
    print("=" * 60)

    reasoner = CompatibilityReasoner()

    # Test 1: Valid upgrade path
    print("\n--- Test 1: Valid upgrade (1.330 -> 1.335) ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        os_family="linux",
        os_version="8",
        managed_cluster_version="1.335",
    )

    print(f"Status: {result.status.value}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Issues: {len(result.issues)}, Warnings: {len(result.warnings)}")
    print(f"Recommendations: {result.recommendations}")

    # Test 2: Invalid upgrade (older version)
    print("\n--- Test 2: Invalid upgrade (1.335 -> 1.330) ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.335", target_version="1.330"
    )

    print(f"Status: {result.status.value}")
    print(f"Issues: {[i.message for i in result.issues]}")

    # Test 3: Deprecated version
    print("\n--- Test 3: Deprecated version (1.325) ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.320", target_version="1.325"
    )

    print(f"Status: {result.status.value}")
    print(f"Warnings: {[w.message for w in result.warnings]}")

    # Test 4: End of support version
    print("\n--- Test 4: End of support version (1.300) ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.295", target_version="1.300"
    )

    print(f"Status: {result.status.value}")
    print(f"Issues: {[i.message for i in result.issues]}")

    # Test 5: With extensions
    print("\n--- Test 5: With extension compatibility ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        extensions=[
            {"id": "custom-logging", "version": "2.0.0"},
            {"id": "custom-metrics", "version": "3.0.0"},
        ],
    )

    print(f"Status: {result.status.value}")
    print(f"Warnings: {[w.message for w in result.warnings]}")

    # Test 6: Full result output
    print("\n--- Test 6: Full result dict ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        os_family="linux",
        os_version="8",
        managed_cluster_version="1.335",
    )

    result_dict = result.to_dict()
    print(f"Result keys: {list(result_dict.keys())}")
    print(f"Status value: {result_dict['status']}")
    print(f"Checked factors: {result_dict['checked_factors']}")


def test_semantic_search():
    """Test semantic search capabilities."""
    print("\n" + "=" * 60)
    print("Testing Semantic Search")
    print("=" * 60)

    search = SemanticSearch()

    # Add sample documents
    search.add_document(
        "ag-1-335",
        "ActiveGate 1.335 supports Windows Server 2019, 2022, Linux RHEL 8.x, 9.x, CentOS 8.x, Ubuntu 20.04, 22.04. Compatible with Managed cluster 1.335 and later.",
        {"version": "1.335", "type": "release_notes"},
    )

    search.add_document(
        "ag-1-330",
        "ActiveGate 1.330 supports Windows Server 2016, 2019, Linux RHEL 7.x, 8.x, CentOS 7.x, 8.x. Compatible with Managed cluster 1.330.",
        {"version": "1.330", "type": "release_notes"},
    )

    search.add_document(
        "eos-notice",
        "End of support for ActiveGate 1.300 and earlier versions. Please upgrade to 1.310 or later.",
        {"version": "1.300", "type": "end_of_support"},
    )

    # Test search
    print("\n--- Search: AG with Linux support ---")
    results = search.search("ActiveGate Linux support")
    for r in results:
        print(f"  - {r['id']}: score={r['score']:.2f}")

    # Test version similarity
    print("\n--- Similar versions to 1.332 ---")
    similar = search.find_similar_versions(
        "1.332", ["1.330", "1.331", "1.332", "1.333", "1.334", "1.335"]
    )
    for version, score in similar:
        print(f"  - {version}: {score:.2f}")


def test_historical_queries():
    """Test historical compatibility queries."""
    print("\n" + "=" * 60)
    print("Testing Historical Queries")
    print("=" * 60)

    hist = HistoricalQuery()

    # Add version history
    hist.add_version_history("1.330", "2024-01-15", "2025-07-01")
    hist.add_version_history("1.335", "2024-04-15")
    hist.add_version_history("1.300", "2023-07-01", "2024-06-01")

    # Add compatibility history
    hist.add_compatibility_history(
        "1.330", "1.330", True, "Release Notes", "2024-01-15"
    )
    hist.add_compatibility_history(
        "1.330", "1.325", True, "Release Notes", "2024-01-15"
    )
    hist.add_compatibility_history("1.300", "1.320", False, "Support KB", "2023-09-01")

    # Test version support
    print("\n--- Is 1.330 supported? ---")
    result = hist.is_version_supported("1.330")
    print(f"  Supported: {result['supported']}")
    print(f"  Status: {result.get('status')}")

    print("\n--- Is 1.300 supported? ---")
    result = hist.is_version_supported("1.300")
    print(f"  Supported: {result['supported']}")
    print(f"  Reason: {result.get('reason')}")

    # Test compatibility at time
    print("\n--- Was 1.330 compatible with 1.325? ---")
    compat = hist.get_compatibility_at_time("1.330", "1.325")
    print(f"  Compatible: {compat}")

    # Test upgrade timeline
    print("\n--- Upgrade timeline 1.330 -> 1.335 ---")
    timeline = hist.get_upgrade_timeline("1.330", "1.335")
    print(f"  From release: {timeline.get('from_release')}")
    print(f"  To release: {timeline.get('to_release')}")
    print(f"  To status: {timeline.get('to_status')}")

    # Test alternatives
    print("\n--- Supported alternatives to 1.300 ---")
    alts = hist.find_supported_alternatives("1.300")
    for alt in alts:
        print(f"  - {alt['version']} ({alt['status']})")


def test_citation_generator():
    """Test citation generation."""
    print("\n" + "=" * 60)
    print("Testing Citation Generator")
    print("=" * 60)

    gen = CitationGenerator()

    # Register sources
    gen.register_source(
        "https://docs.dynatrace.com/managed/whats-new/managed/sprint-335",
        "What's new in Dynatrace Managed 1.335",
        "release_notes",
    )

    gen.register_source(
        "https://docs.dynatrace.com/managed/whats-new/technology/end-of-support-news",
        "End of Support Announcements",
        "end_of_support",
    )

    # Generate citation
    print("\n--- Generate citation ---")
    citation = gen.generate_citation(
        "https://docs.dynatrace.com/managed/whats-new/managed/sprint-335",
        "ActiveGate 1.335 is compatible with Managed cluster 1.335",
        confidence=0.9,
    )

    if citation:
        print(f"  Title: {citation.source_title}")
        print(f"  URL: {citation.source_url}")
        print(f"  Type: {citation.source_type}")
        print(f"  Confidence: {citation.confidence:.0%}")

    # Format citation
    print("\n--- Formatted citation ---")
    text = gen.format_citation_text(citation)
    print(text)


def test_query_processor():
    """Test query processing."""
    print("\n" + "=" * 60)
    print("Testing Query Processor")
    print("=" * 60)

    reasoner = CompatibilityReasoner()
    processor = QueryProcessor(reasoner)

    # Test natural language query parsing
    print("\n--- Parse: Can I run extension X on AG 1.335? ---")
    parsed = processor.process_query(
        "Can I run extension custom-logging on ActiveGate 1.335?"
    )
    print(f"  Query type: {parsed['query_type']}")
    print(f"  Versions found: {parsed['versions_found']}")

    # Test structured input parsing
    print("\n--- Parse structured input ---")
    input_data = {
        "current_activegate_version": "1.330",
        "target_activegate_version": "1.335",
        "os_family": "linux",
        "os_version": "8",
        "managed_cluster_version": "1.335",
        "extensions": [{"id": "custom-ext", "version": "2.0"}],
    }
    params = processor.parse_structured_input(input_data)
    print(f"  Current: {params['current_version']}")
    print(f"  Target: {params['target_version']}")
    print(f"  OS: {params['os_family']} {params['os_version']}")
    print(f"  Extensions: {len(params['extensions'])}")

    # Test result formatting
    print("\n--- Format result for display ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        os_family="linux",
        os_version="8",
        managed_cluster_version="1.335",
    )

    output = processor.format_result_for_display(result)
    print(output)


def test_integration():
    """Test full integration."""
    print("\n" + "=" * 60)
    print("Testing Full Integration")
    print("=" * 60)

    # Full pipeline: query -> reasoner -> result with citations
    reasoner = CompatibilityReasoner()
    citation_gen = CitationGenerator()
    query_processor = QueryProcessor(reasoner, citation_generator=citation_gen)

    # Register sources
    citation_gen.register_source(
        "https://docs.dynatrace.com/managed/whats-new/managed/sprint-335",
        "ActiveGate 1.335 Release",
        "release_notes",
    )

    # Process a query
    print("\n--- Full query: Upgrade to 1.335 with Linux ---")
    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        os_family="linux",
        os_version="8",
        managed_cluster_version="1.335",
    )

    # Format output
    output = query_processor.format_result_for_display(result)
    print(output)


if __name__ == "__main__":
    test_compatibility_reasoner()
    test_semantic_search()
    test_historical_queries()
    test_citation_generator()
    test_query_processor()
    test_integration()

    print("\n" + "=" * 60)
    print("All reasoning engine tests completed successfully!")
    print("=" * 60)
