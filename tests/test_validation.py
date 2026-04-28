#!/usr/bin/env python3
"""
Test script for validating against known compatibility cases.
Tests the system against real-world scenarios from Dynatrace documentation.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.reasoning.compatibility_reasoner import CompatibilityReasoner, CompatibilityStatus


# Known compatibility test cases from Dynatrace documentation
KNOWN_CASES = [
    {
        'name': 'Current version deprecated',
        'current': '1.300',
        'target': '1.335',
        'expected_status': ['NO_GO', 'GO_WITH_CAUTION'],
        'reason': '1.300 is deprecated, should warn or block'
    },
    {
        'name': 'End of support version',
        'current': '1.280',
        'target': '1.335',
        'expected_status': ['NO_GO'],
        'reason': '1.280 reached end of support'
    },
    {
        'name': 'Standard upgrade path',
        'current': '1.330',
        'target': '1.335',
        'expected_status': ['GO', 'GO_WITH_CAUTION'],
        'reason': 'Standard upgrade within supported range'
    },
    {
        'name': 'Multiple version jump',
        'current': '1.320',
        'target': '1.335',
        'expected_status': ['GO', 'GO_WITH_CAUTION'],
        'reason': 'Upgrading multiple versions, may need caution'
    },
    {
        'name': 'Same version',
        'current': '1.335',
        'target': '1.335',
        'expected_status': ['GO'],
        'reason': 'Same version is always compatible'
    },
    {
        'name': 'Downgrade attempt',
        'current': '1.335',
        'target': '1.330',
        'expected_status': ['GO', 'GO_WITH_CAUTION', 'NO_GO'],
        'reason': 'Downgrade - may not be supported'
    },
    {
        'name': 'Very old version',
        'current': '1.250',
        'target': '1.335',
        'expected_status': ['NO_GO'],
        'reason': 'Very old version likely incompatible'
    },
    {
        'name': 'Future version',
        'current': '1.335',
        'target': '1.400',
        'expected_status': ['UNKNOWN'],
        'reason': 'Future version not in knowledge base'
    }
]


def test_known_compatibility_cases():
    """Test the reasoner against known compatibility cases."""
    print("\n=== Testing Known Compatibility Cases ===")
    
    reasoner = CompatibilityReasoner()
    passed = 0
    failed = 0
    
    for case in KNOWN_CASES:
        print(f"\nTesting: {case['name']}")
        print(f"  Upgrade: {case['current']} -> {case['target']}")
        
        result = reasoner.check_upgrade_compatibility(
            current_version=case['current'],
            target_version=case['target']
        )
        
        # Check if result status is in expected list
        status_match = result.status.value in case['expected_status']
        
        if status_match:
            print(f"  ✓ Status: {result.status.value} (expected: {case['expected_status']})")
            passed += 1
        else:
            print(f"  ✗ Status: {result.status.value} (expected: {case['expected_status']})")
            print(f"    Reason: {case['reason']}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Compatibility Case Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


def test_extension_compatibility():
    """Test extension compatibility checking."""
    print("\n=== Testing Extension Compatibility ===")
    
    reasoner = CompatibilityReasoner()
    
    # Test with extension list
    extensions = [
        {'id': 'custom-logging', 'version': '2.0'},
        {'id': 'custom-metrics', 'version': '1.5'}
    ]
    
    result = reasoner.check_upgrade_compatibility(
        current_version='1.330',
        target_version='1.335',
        extensions=extensions
    )
    
    print(f"  Status: {result.status.value}")
    print(f"  Extensions checked: {len(extensions)}")
    print("✓ Extension compatibility test passed")
    
    return True


def test_os_compatibility():
    """Test OS compatibility checking."""
    print("\n=== Testing OS Compatibility ===")
    
    reasoner = CompatibilityReasoner()
    
    # Test with OS parameters
    result = reasoner.check_upgrade_compatibility(
        current_version='1.330',
        target_version='1.335',
        os_family='linux',
        os_version='8'
    )
    
    print(f"  Status: {result.status.value}")
    print(f"  OS: Linux 8")
    print("✓ OS compatibility test passed")
    
    return True


def test_managed_cluster_compatibility():
    """Test Managed cluster compatibility checking."""
    print("\n=== Testing Managed Cluster Compatibility ===")
    
    reasoner = CompatibilityReasoner()
    
    # Test with Managed cluster version
    result = reasoner.check_upgrade_compatibility(
        current_version='1.330',
        target_version='1.335',
        managed_cluster_version='1.335'
    )
    
    print(f"  Status: {result.status.value}")
    print(f"  Managed Cluster: 1.335")
    print("✓ Managed cluster compatibility test passed")
    
    return True


def test_full_pipeline():
    """Test full compatibility check with all parameters."""
    print("\n=== Testing Full Pipeline ===")
    
    reasoner = CompatibilityReasoner()
    
    result = reasoner.check_upgrade_compatibility(
        current_version='1.330',
        target_version='1.335',
        os_family='linux',
        os_version='8',
        managed_cluster_version='1.335',
        extensions=[
            {'id': 'custom-logging', 'version': '2.0'},
            {'id': 'custom-metrics', 'version': '1.5'}
        ]
    )
    
    print(f"  Status: {result.status.value}")
    print(f"  Confidence: {result.confidence:.0%}")
    print(f"  Issues: {len(result.issues)}")
    print(f"  Warnings: {len(result.warnings)}")
    print(f"  Recommendations: {len(result.recommendations)}")
    print("✓ Full pipeline test passed")
    
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Running Known Compatibility Cases Tests")
    print("=" * 60)
    
    tests = [
        test_known_compatibility_cases,
        test_extension_compatibility,
        test_os_compatibility,
        test_managed_cluster_compatibility,
        test_full_pipeline
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)