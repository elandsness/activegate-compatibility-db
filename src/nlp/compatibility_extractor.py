import re
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class CompatibilityStatement:
    statement_type: str  # 'compatible', 'incompatible', 'deprecated', 'requires_upgrade', 'end_of_support'
    subject_version: Optional[str]  # Version that is being discussed
    related_version: Optional[str]  # Version it relates to
    component: str  # 'activegate', 'os', 'extension', 'managed_cluster'
    subject_component: str  # extracted subject component type
    object_component: str  # extracted object component type
    confidence: float  # 0.0 to 1.0
    raw_text: str
    context_start: int
    context_end: int


class CompatibilityExtractor:
    """Extract compatibility statements from release notes and documentation."""
    
    # Patterns for different compatibility statements
    COMPATIBILITY_PATTERNS = {
        'compatible': [
            r'(?:compatible\s+with|supports?|works\s+with|runs\s+on)(?:\s+[A-Za-z0-9]+){0,8}?\s*(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(\d+\.\d+(?:\.\d+)*)\s+(?:is\s+)?compatible\s+with(?:\s+[A-Za-z0-9]+){0,8}?\s*(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'ActiveGate\s*(\d+\.\d+(?:\.\d+)*)\s+supports\s+(?:Dynatrace\s+)?Managed\s+cluster(?:\s+versions?)?\s+(?:from|starting\s+at|at)\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
        'incompatible': [
            r'(?:incompatible|not\s+compatible|does\s+not\s+work|cannot\s+run)(?:\s+with\s+|on\s+)?(?:[A-Za-z0-9]+){0,8}?\s*(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(\d+\.\d+(?:\.\d+)*)\s+(?:is\s+)?incompatible\s+with(?:\s+[A-Za-z0-9]+){0,8}?\s*(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(?:prior\s+to|earlier\s+than|before)\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
        'deprecated': [
            r'(?:deprecat[ed]?|end\s+of\s+life|EOL).*?(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
            r'(?:version\s+)?(\d+\.\d+(?:\.\d+)*)\s+(?:is\s+)?(?:deprecat[ed]?|no\s+longer\s+supported)',
            r'Support\s+for(?:\s+Dynatrace)?\s+Managed\s+versions?\s+(\d+\.\d+(?:\.\d+)*)\s+and\s+earlier',
        ],
        'requires_upgrade': [
            r'(?:requires|requires\s+upgrade\s+to|upgrade\s+to)(?: version)?\s+(\d+\.\d+(?:\.\d+)*)',
            r'(?:upgrade\s+from|from\s+version\s+)?(\d+\.\d+(?:\.\d+)*)\s+to\s+(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
        'end_of_support': [
            r'(?:end(?:\s+of\s+)?(?:\s+support)?|EOL|no\s+longer\s+supported).*?(?:version\s+)?(\d+\.\d+(?:\.\d+)*)',
        ],
    }
    
    # Patterns to identify component types
    COMPONENT_PATTERNS = {
        'activegate': r'\b(?:ActiveGate|active\s*gate|AG)\b',
        'os': r'\b(?:operating\s+system|OS|Windows|Linux|CentOS|RHEL|Ubuntu|Kubernetes)\b',
        'extension': r'\b(?:extension|plugin|module)\b',
        'managed_cluster': r'\b(?:Dynatrace\s+Managed|Managed\s+cluster|managed\s+environment|cluster)\b',
    }
    
    def __init__(self):
        self.compatibility_patterns = self.COMPATIBILITY_PATTERNS
        self.component_patterns = self.COMPONENT_PATTERNS
    
    def extract_statements(self, text: str, full_context: bool = True) -> List[CompatibilityStatement]:
        """Extract compatibility statements from text."""
        statements = []
        seen_signatures = set()
        
        for stmt_type, patterns in self.compatibility_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    sentence, sentence_start = self._sentence_for_position(text, match.start())
                    relative_position = match.start() - sentence_start
                    subject_component = self._determine_subject_component(sentence, stmt_type, relative_position)
                    if subject_component == 'unknown':
                        subject_component = self._identify_component(text, match.start())

                    if self._should_skip_statement(stmt_type, sentence):
                        continue
                    
                    subject_version, related_version = self._extract_subject_and_related_versions(match, stmt_type, sentence, relative_position)
                    
                    object_component = self._identify_object_component(sentence, stmt_type, subject_component)
                    
                    confidence = self._calc_confidence(match, sentence, stmt_type)
                    
                    context_start = max(0, match.start() - 100)
                    context_end = min(len(text), match.end() + 100)

                    signature = (
                        stmt_type,
                        subject_version,
                        related_version,
                        subject_component,
                        object_component,
                    )
                    if signature in seen_signatures:
                        continue
                    seen_signatures.add(signature)

                    statement = CompatibilityStatement(
                        statement_type=stmt_type,
                        subject_version=subject_version,
                        related_version=related_version,
                        component=subject_component,
                        subject_component=subject_component,
                        object_component=object_component,
                        confidence=confidence,
                        raw_text=match.group(0),
                        context_start=context_start,
                        context_end=context_end
                    )
                    statements.append(statement)
        
        return statements
    
    def _identify_component(self, text: str, position: int) -> str:
        """Identify the component type nearest to the given position."""
        if position < 0:
            return 'unknown'

        best_component = 'unknown'
        best_distance = None

        for component, pattern in self.component_patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                distance = abs(position - match.start())
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_component = component

        return best_component

    def _sentence_for_position(self, text: str, position: int):
        """Extract the sentence fragment around a given position."""
        start = text.rfind('\n', 0, position)
        end = text.find('\n', position)
        if start == -1:
            start = 0
        else:
            start += 1
        if end == -1:
            end = len(text)
        return text[start:end], start

    def _determine_subject_component(self, sentence: str, stmt_type: str, relative_position: int) -> str:
        """Determine the most likely subject component for a statement."""
        if stmt_type in {'compatible', 'incompatible', 'deprecated', 'end_of_support'}:
            if 'activegate' in sentence.lower() or 'active gate' in sentence.lower() or 'ag ' in sentence.lower():
                return 'activegate'
            if 'dynatrace managed' in sentence.lower() or 'managed cluster' in sentence.lower() or 'managed version' in sentence.lower():
                return 'managed_cluster'
            if 'extension' in sentence.lower() or 'plugin' in sentence.lower() or 'custom log source' in sentence.lower():
                return 'extension'
            if 'windows server' in sentence.lower() or 'linux' in sentence.lower() or 'ubuntu' in sentence.lower() or 'centos' in sentence.lower() or 'rhel' in sentence.lower() or 'kubernetes' in sentence.lower():
                return 'os'
        if stmt_type == 'requires_upgrade':
            if 'extension' in sentence.lower():
                return 'extension'
            if 'activegate' in sentence.lower() or 'ag ' in sentence.lower():
                return 'activegate'
            if 'managed' in sentence.lower():
                return 'managed_cluster'
        return self._identify_component(sentence, relative_position)
    
    def _calc_confidence(self, match, text: str, stmt_type: str) -> float:
        """Calculate confidence score for extracted statement."""
        confidence = 0.4  # base

        # bump when explicit version tokens are present in the matched text or nearby
        matched_text = match.group(0) if match and hasattr(match, 'group') else ''
        version_count = len(list(re.finditer(r'(\d+\.\d+(?:\.\d+)*)', matched_text)))
        if version_count >= 1:
            confidence += 0.15
        if version_count >= 2:
            confidence += 0.1

        # Additional context boosts
        context_start = max(0, match.start() - 80)
        context_end = min(len(text), match.end() + 80)
        context = text[context_start:context_end].lower()
        if 'version' in context or 'supports' in context or 'compatible' in context:
            confidence += 0.1

        # Penalize ambiguous phrases
        if 'prior to' in context or 'earlier than' in context or 'before' in context:
            confidence = max(0.0, confidence - 0.1)
        if 'deprecated' in context or 'end of life' in context or 'no longer supported' in context:
            confidence = max(0.0, confidence - 0.05)

        # Statement type boosts
        if stmt_type == 'requires_upgrade' and version_count >= 1:
            confidence = min(1.0, confidence + 0.1)

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

    def _extract_subject_and_related_versions(self, match, stmt_type: str, sentence: str, relative_match_start: int):
        """Resolve subject and related versions from a sentence."""
        groups = match.groups()
        versions = [(m.group(1), m.start()) for m in re.finditer(r'(\d+\.\d+(?:\.\d+)*)', sentence)]

        if len(groups) >= 2 and groups[0] and groups[1]:
            return groups[0], groups[1]

        if not versions:
            return None, None

        if len(versions) == 1:
            return versions[0][0], None

        matched_value = groups[0] if groups and groups[0] else None
        matched_position = None
        if matched_value:
            for value, pos in versions:
                if value == matched_value:
                    matched_position = pos
                    break

        if matched_position is not None:
            before = [value for value, pos in versions if pos < matched_position]
            after = [value for value, pos in versions if pos > matched_position]
            if before and after:
                return before[-1], after[0]
            if before:
                return before[-1], matched_value
            if after:
                return matched_value, after[0]

        before = [value for value, pos in versions if pos < relative_match_start]
        after = [value for value, pos in versions if pos > relative_match_start]
        if before and after:
            return before[-1], after[0]

        return versions[0][0], versions[1][0]

    def _identify_object_component(self, context_text: str, statement_type: str, subject_component: str) -> str:
        """Identify the most likely object component from surrounding context."""
        lowered = context_text.lower()
        if 'managed cluster' in lowered or 'dynatrace managed' in lowered or 'managed version' in lowered or 'managed versions' in lowered:
            return 'managed_cluster'
        if 'extension' in lowered or 'plugin' in lowered or 'custom log source' in lowered:
            return 'extension'
        if 'windows server' in lowered or 'linux' in lowered or 'ubuntu' in lowered or 'centos' in lowered or 'rhel' in lowered or 'kubernetes' in lowered:
            return 'os'
        if subject_component == 'managed_cluster' and 'activegate' in lowered:
            return 'activegate'
        if statement_type == 'requires_upgrade':
            return subject_component
        return 'unknown'

    def _should_skip_statement(self, stmt_type: str, sentence: str) -> bool:
        lowered = sentence.lower()
        if stmt_type == 'compatible' and 'incompatible' in lowered:
            return True
        if stmt_type in {'compatible', 'incompatible'} and ('deprecated' in lowered or 'end of support' in lowered or 'no longer supported' in lowered):
            return True
        if stmt_type == 'compatible' and 'prior to' in lowered:
            return True
        return False
