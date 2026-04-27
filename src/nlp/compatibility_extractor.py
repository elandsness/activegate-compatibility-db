import re
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class CompatibilityStatement:
    statement_type: str  # 'compatible', 'incompatible', 'deprecated', 'requires_upgrade', 'end_of_support'
    subject_version: Optional[str]  # Version that is being discussed
    related_version: Optional[str]  # Version it relates to
    component: str  # 'activegate', 'os', 'extension', 'managed_cluster'
    confidence: float  # 0.0 to 1.0
    raw_text: str
    context_start: int
    context_end: int


class CompatibilityExtractor:
    """Extract compatibility statements from release notes and documentation."""
    
    # Patterns for different compatibility statements
    COMPATIBILITY_PATTERNS = {
        'compatible': [
            r'(?:supports?|compatible\s+with|works\s+with|runs\s+on)\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(?:compatible|support)\s+for\s+(?:versions?\s+)?(\d+\.\d+(?:\.\d+)*)\s+(?:and\s+(?:higher|above|later))?',
        ],
        'incompatible': [
            r'(?:incompatible|not\s+compatible|does\s+not\s+work|cannot\s+run)\s+(?:with\s+|on\s+)?(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(?:not\s+)?(?:supportive|supported)\s+(?:version|release).*?(\d+\.\d+(?:\.\d+)*)',
        ],
        'deprecated': [
            r'(?:deprecat[ed]?|end\s+of\s+life|EOL).*?(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(?:version\s+)?(\d+\.\d+(?:\.\d+)*)\s+(?:is\s+)?(?:deprecat[ed]?|no\s+longer\s+supported)',
        ],
        'requires_upgrade': [
            r'(?:requires|requires\s+upgrade\s+to|upgrade\s+to)(?: version)?\s+(\d+\.\d+(?:\.\d+)*)',
            r'(?:upgrade\s+from|from\s+version\s+)?(?:\d+\.\d+(?:\.\d+)*)\s+to\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
        'end_of_support': [
            r'(?:end(?:\s+of\s+)?(?:\s+support)?|EOL|no\s+longer\s+supported).*?(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
    }
    
    # Patterns to identify component types
    COMPONENT_PATTERNS = {
        'activegate': r'(?:ActiveGate|active\s*gate|AG)',
        'os': r'(?:operating\s+system|OS|Windows|Linux|CentOS|RHEL|Ubuntu)',
        'extension': r'(?:extension|plugin|module)',
        'managed_cluster': r'(?:Managed\s+cluster|managed\s+environment|cluster)',
    }
    
    def __init__(self):
        self.compatibility_patterns = self.COMPATIBILITY_PATTERNS
        self.component_patterns = self.COMPONENT_PATTERNS
    
    def extract_statements(self, text: str, full_context: bool = True) -> List[CompatibilityStatement]:
        """Extract compatibility statements from text."""
        statements = []
        
        for stmt_type, patterns in self.compatibility_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Determine component type
                    component = self._identify_component(text, match.start())
                    
                    # Extract version
                    version = match.group(1) if len(match.groups()) > 0 else None
                    
                    # Get context
                    context_start = max(0, match.start() - 100)
                    context_end = min(len(text), match.end() + 100)
                    context_text = text[context_start:context_end]
                    
                    # Calculate confidence based on pattern match quality
                    confidence = self._calc_confidence(match, text, stmt_type)
                    
                    statement = CompatibilityStatement(
                        statement_type=stmt_type,
                        subject_version=version,
                        related_version=None,
                        component=component,
                        confidence=confidence,
                        raw_text=match.group(0),
                        context_start=context_start,
                        context_end=context_end
                    )
                    statements.append(statement)
        
        return statements
    
    def _identify_component(self, text: str, position: int) -> str:
        """Identify the component type near the given position."""
        # Look at surrounding text (200 chars before position)
        start = max(0, position - 200)
        surrounding = text[start:position]
        
        for component, pattern in self.component_patterns.items():
            if re.search(pattern, surrounding, re.IGNORECASE):
                return component
        
        return 'unknown'
    
    def _calc_confidence(self, match, text: str, stmt_type: str) -> float:
        """Calculate confidence score for extracted statement."""
        confidence = 0.5  # Base confidence
        
        # Increase confidence if statement is explicit
        if match.group(0).lower() in ['compatible', 'incompatible', 'deprecated', 'requires upgrade']:
            confidence += 0.3
        
        # Check if surrounded by context keywords
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 50)
        context = text[context_start:context_end]
        
        # More context keywords = higher confidence
        context_keywords = ['version', 'support', 'release', 'update', 'cluster']
        keyword_count = sum(1 for kw in context_keywords if kw.lower() in context.lower())
        confidence += min(0.2, keyword_count * 0.05)
        
        return min(1.0, confidence)
    
    def extract_version_pairs(self, text: str) -> List[Dict]:
        """Extract version compatibility pairs (from version X to version Y)."""
        pairs = []
        
        # Pattern: "from version X to version Y" or "upgrade from X to Y"
        pattern = r'(?:from|upgrade\s+from)\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)\s+(?:to|upgrade\s+to)\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)'
        
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            pairs.append({
                'from_version': match.group(1),
                'to_version': match.group(2),
                'raw_text': match.group(0),
                'position': match.start()
            })
        
        return pairs
    
    def summarize_statements(self, statements: List[CompatibilityStatement]) -> Dict:
        """Summarize extracted statements by type."""
        summary = {}
        for stmt_type in ['compatible', 'incompatible', 'deprecated', 'requires_upgrade', 'end_of_support']:
            filtered = [s for s in statements if s.statement_type == stmt_type]
            summary[stmt_type] = {
                'count': len(filtered),
                'high_confidence': len([s for s in filtered if s.confidence > 0.7]),
                'low_confidence': len([s for s in filtered if s.confidence < 0.5]),
            }
        return summary
