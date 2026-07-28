#!/usr/bin/env python3
"""
Test script for NLP extraction engine.
Tests entity extraction and compatibility statement extraction on sample data.
"""

from src.nlp.compatibility_extractor import CompatibilityExtractor
from src.nlp.entity_extractor import EntityExtractor
from src.nlp.nlp_pipeline import FactConverter, NLPPipeline

# Sample release note text
SAMPLE_ACTIVEGATE_RELEASE = """
What's new in Dynatrace ActiveGate 1.335

New features and improvements

Release date: April 13, 2026

ActiveGate 1.335 is now available.

Supported versions

ActiveGate 1.335 supports the following environments:

- Windows Server 2019 and 2022
- Linux: CentOS 8.x, RHEL 8.x and 9.x, Ubuntu 20.04 and 22.04
- Kubernetes 1.22 to 1.28

Compatibility

ActiveGate 1.335 is compatible with Dynatrace Managed 1.335 and later.

ActiveGate 1.335 is incompatible with Managed cluster versions prior to 1.330.

Deprecations

Support for Dynatrace Managed versions 1.320 and earlier has been deprecated and will reach end of life in Q3 2026.

ActiveGate 1.325 is no longer supported.

Required upgrades

To deploy extensions, you must upgrade to the latest extension version.
The Custom Log Source extension requires version 2.1.0 or later.

End of Support

ActiveGate 1.300 and earlier reach end of support on June 1, 2026.
Dynatrace Managed 1.310 and earlier reach end of support on August 1, 2026.

Bug fixes and performance improvements

- Fixed issue with Windows Server 2022 compatibility
- Improved performance for extension processing
"""


SAMPLE_EXTENSION_RELEASE = """
Custom Application Monitoring Extension - Version 2.1.0

Release Date: April 20, 2026

New in Version 2.1.0

- ActiveGate deployment support
- Compatible with Dynatrace Managed 1.330 and later
- Works on Windows Server 2019, 2022, and Linux systems

Compatibility

This extension is compatible with:
- ActiveGate versions 1.330 to 1.335
- Dynatrace Managed cluster 1.330 and later
- Operating systems: Windows Server 2019, 2022, RHEL 8.x, 9.x, Ubuntu 20.04, 22.04

Known Issues

Version 2.1.0 is incompatible with Dynatrace Managed versions prior to 1.325.

Migration from older versions

Upgrade from version 2.0.x to version 2.1.0 is supported and recommended for all users.
"""


def test_entity_extraction():
    """Test entity extraction on sample data."""
    print("=" * 60)
    print("Testing Entity Extraction")
    print("=" * 60)

    extractor = EntityExtractor()

    # Test on ActiveGate release notes
    print("\n--- ActiveGate Release Notes ---")
    entities = extractor.extract_all_entities(SAMPLE_ACTIVEGATE_RELEASE)

    print(f"Found {len(entities['versions'])} versions:")
    for version, context in entities["versions"][:3]:
        print(f"  - {version} (raw: {version.raw})")
        print(f"    Context: ...{context[-50:]}...")

    print(f"\nFound {len(entities['os_versions'])} OS versions:")
    for os_info in entities["os_versions"][:3]:
        print(f"  - {os_info['family']} {os_info['version']}")

    print(f"\nFound {len(entities['extensions'])} extensions:")
    for ext in entities["extensions"]:
        print(
            f"  - {ext['name']} (v{ext['version']})"
            if ext["version"]
            else f"  - {ext['name']}"
        )

    # Test on extension release notes
    print("\n--- Extension Release Notes ---")
    entities = extractor.extract_all_entities(SAMPLE_EXTENSION_RELEASE)

    print(f"Found {len(entities['versions'])} versions:")
    for version, context in entities["versions"]:
        print(f"  - {version}")

    print(f"Found {len(entities['os_versions'])} OS versions:")
    for os_info in entities["os_versions"]:
        print(f"  - {os_info['family']} {os_info['version']}")


def test_compatibility_extraction():
    """Test compatibility statement extraction."""
    print("\n" + "=" * 60)
    print("Testing Compatibility Extraction")
    print("=" * 60)

    extractor = CompatibilityExtractor()

    # Test on ActiveGate release notes
    print("\n--- ActiveGate Release Notes ---")
    statements = extractor.extract_statements(SAMPLE_ACTIVEGATE_RELEASE)

    print(f"Found {len(statements)} compatibility statements:")
    for stmt in statements[:5]:
        print(f"  - [{stmt.statement_type}] {stmt.raw_text[:60]}...")
        print(f"    Component: {stmt.component}, Confidence: {stmt.confidence:.2f}")

    # Summarize
    summary = extractor.summarize_statements(statements)
    print("\nSummary by type:")
    for stmt_type, counts in summary.items():
        if counts["count"] > 0:
            print(
                f"  - {stmt_type}: {counts['count']} (high conf: {counts['high_confidence']}, low conf: {counts['low_confidence']})"
            )

    # Test on extension notes
    print("\n--- Extension Release Notes ---")
    statements = extractor.extract_statements(SAMPLE_EXTENSION_RELEASE)
    summary = extractor.summarize_statements(statements)

    print(f"Found {len(statements)} compatibility statements")
    print("Summary by type:")
    for stmt_type, counts in summary.items():
        if counts["count"] > 0:
            print(f"  - {stmt_type}: {counts['count']}")


def test_nlp_pipeline():
    """Test the full NLP pipeline."""
    print("\n" + "=" * 60)
    print("Testing NLP Pipeline")
    print("=" * 60)

    pipeline = NLPPipeline()

    # Process ActiveGate release notes
    print("\n--- Processing ActiveGate Release Notes ---")
    result = pipeline.process_document(
        text=SAMPLE_ACTIVEGATE_RELEASE,
        source_url="https://docs.dynatrace.com/managed/whats-new/managed/sprint-335",
        source_title="What's new in Dynatrace ActiveGate 1.335",
    )

    print(f"Source: {result.source_title}")
    print("Extracted entities:")
    print(f"  - Versions: {len(result.entities['versions'])}")
    print(f"  - OS versions: {len(result.entities['os_versions'])}")
    print(f"  - Extensions: {len(result.entities['extensions'])}")
    print(f"  - Compatibility statements: {len(result.compatibility_statements)}")
    print(f"  - Version pairs: {len(result.version_pairs)}")
    print(f"\nConfidence scores: {result.confidence_scores}")

    # Convert to facts
    print("\nConverting to facts...")
    facts = FactConverter.convert_to_facts(result)
    print(f"Generated {len(facts)} facts:")
    for fact in facts[:3]:
        print(f"  - {fact.subject} --[{fact.predicate}]--> {fact.object}")
        print(f"    Confidence: {fact.confidence}, Source: {fact.source_url}")


def test_batch_processing():
    """Test batch processing."""
    print("\n" + "=" * 60)
    print("Testing Batch Processing")
    print("=" * 60)

    pipeline = NLPPipeline()

    documents = [
        {
            "title": "ActiveGate 1.335 Release",
            "url": "https://docs.example.com/ag135",
            "content": SAMPLE_ACTIVEGATE_RELEASE,
        },
        {
            "title": "Extension Release 2.1.0",
            "url": "https://docs.example.com/ext210",
            "content": SAMPLE_EXTENSION_RELEASE,
        },
    ]

    results = pipeline.process_batch(documents)
    print(f"Processed {len(results)} documents")

    for result in results:
        print(f"\n  {result.source_title}")
        print(f"    - {len(result.entities['versions'])} versions")
        print(f"    - {len(result.compatibility_statements)} statements")
        print(
            f"    - Avg confidence: {sum(result.confidence_scores.values()) / len(result.confidence_scores):.2f}"
        )


def test_linux_distro_os_facts_are_not_collapsed_to_generic_linux():
    """Ensure distro-specific OS facts are preserved (e.g., RHEL 8, Debian 13)."""
    pipeline = NLPPipeline()
    text = """
    What's new in Dynatrace ActiveGate 1.335
    Supported OS: Red Hat Enterprise Linux 8, Debian 13, Ubuntu 24.04 LTS
    """

    result = pipeline.process_document(
        text=text,
        source_url="https://docs.example.com/managed/sprint-335",
        source_title="What's new in Dynatrace ActiveGate 1.335",
    )

    facts = FactConverter.convert_to_facts(result)
    supported_targets = {
        fact.object
        for fact in facts
        if fact.predicate == "SUPPORTED_BY" and fact.subject == "1.335"
    }

    assert "Red Hat Enterprise Linux 8" in supported_targets
    assert "Debian 13" in supported_targets
    assert "Ubuntu 24.04" in supported_targets


if __name__ == "__main__":
    test_entity_extraction()
    test_compatibility_extraction()
    test_nlp_pipeline()
    test_batch_processing()

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
