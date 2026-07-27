from src.ingestion.hub_scraper import HubExtensionsScraper
from src.reasoning.compatibility_reasoner import (
    CompatibilityReasoner,
    CompatibilityStatus,
)


class _GraphQueryWithUnknownExtensions:
    def check_activegate_compatibility(
        self,
        activegate_version,
        managed_version,
        os_family=None,
        extensions=None,
    ):
        return {
            "issues": [],
            "warnings": [],
            "unknown_extensions": [
                "Extension Akamai has no verified ActiveGate constraint data"
            ],
        }


def test_extract_constraints_from_feed_text():
    scraper = HubExtensionsScraper()
    text = (
        "This version requires a minimum Dynatrace version of 1.338.0 "
        "and a minimum EEC version (ActiveGate version) of 1.318.0."
    )

    constraints = scraper._extract_constraints(
        text, "https://www.dynatrace.com/hub/detail/akamai/"
    )

    assert any(
        c["component"] == "managed_cluster" and c["min_version"] == "1.338.0"
        for c in constraints
    )
    assert any(
        c["component"] == "activegate" and c["min_version"] == "1.318.0"
        for c in constraints
    )


def test_candidate_feed_paths_for_extension_types():
    scraper = HubExtensionsScraper()

    ext2_paths = scraper._candidate_feed_paths(
        {"slug": "akamai", "extension_type": "extension-2"}
    )
    app_paths = scraper._candidate_feed_paths(
        {"slug": "kubernetes-1", "extension_type": "app"}
    )

    assert ext2_paths[0] == "extensions/akamai"
    assert app_paths[0] == "apps/kubernetes-1"


def test_reasoner_returns_unknown_for_unresolved_extension_constraints():
    reasoner = CompatibilityReasoner(graph_query=_GraphQueryWithUnknownExtensions())

    result = reasoner.check_upgrade_compatibility(
        current_version="1.330",
        target_version="1.335",
        managed_cluster_version="1.335",
        extensions=[{"id": "akamai", "version": "2.0.0"}],
        use_graph=True,
    )

    assert result.status == CompatibilityStatus.UNKNOWN
    assert any(w.category == "extension_unknown" for w in result.warnings)
