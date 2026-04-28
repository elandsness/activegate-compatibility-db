# Neo4j Graph Schema for ActiveGate Compatibility

## Nodes (Entities)
- **ActiveGateVersion**: Properties: version (string), release_date (date)
- **OSVersion**: Properties: os_name (string), version (string), family (string)
- **ManagedClusterVersion**: Properties: version (string), release_date (date)
- **Extension**: Properties: id (string), name (string), version (string), platform (string: 'Managed'), deployable_to (string: 'ActiveGate')
- **Module**: Properties: name (string), description (string)
- **Setting**: Properties: name (string), description (string)

## Relationships
- **SUPPORTED_BY** (ActiveGateVersion -> OSVersion): Indicates OS compatibility
- **REQUIRES** (ActiveGateVersion -> ManagedClusterVersion): Minimum Managed version required
- **COMPATIBLE_WITH** (ActiveGateVersion -> Extension): Extension can run on this ActiveGate version
- **DEPRECATED_IN** (Extension -> ActiveGateVersion): Extension deprecated starting this version
- **INCOMPATIBLE_WITH** (ActiveGateVersion -> Extension): Extension cannot run on this version
- **REQUIRES_UPGRADE** (Extension -> Extension): Must upgrade to this version for compatibility
- **END_OF_SUPPORT** (ActiveGateVersion -> ManagedClusterVersion): End of support for this combination
- **USES_MODULE** (ActiveGateVersion -> Module): ActiveGate version includes this module
- **HAS_SETTING** (ActiveGateVersion -> Setting): ActiveGate version has this setting

## Example Queries
- Find compatible extensions for a given ActiveGate version: MATCH (ag:ActiveGateVersion {version: '1.2.3'})-[:COMPATIBLE_WITH]->(ext:Extension) RETURN ext
- Check if upgrade is safe: MATCH (current:ActiveGateVersion {version: '1.2.3'})-[:REQUIRES]->(mc:ManagedClusterVersion), (target:ActiveGateVersion {version: '1.3.0'})-[:REQUIRES]->(mc) RETURN mc

## Notes
- All relationships include properties: source_url (string), confidence (float), extracted_at (datetime)
- Historical data preserved by not deleting old nodes/relationships
