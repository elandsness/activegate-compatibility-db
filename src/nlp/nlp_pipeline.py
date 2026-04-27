import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json

from src.nlp.entity_extractor import EntityExtractor, Version
from src.nlp.compatibility_extractor import CompatibilityExtractor, CompatibilityStatement

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    source_url: str
    source_title: str
    entities: Dict
    compatibility_statements: List
    version_pairs: List
    summary: Dict
    confidence_scores: Dict
    extraction_timestamp: str


class NLPPipeline:
    """Main NLP pipeline for extracting compatibility information from release notes."""
    
    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.compatibility_extractor = CompatibilityExtractor()
    
    def process_document(self, text: str, source_url: str = "", source_title: str = "") -> ExtractionResult:
        """
        Process a document (release note, doc page, etc.) and extract all compatibility information.
        """
        logger.info(f"Processing document: {source_title}")
        
        # Extract entities
        entities = self.entity_extractor.extract_all_entities(text)
        logger.info(f"Extracted {len(entities['versions'])} versions, {len(entities['os_versions'])} OS versions, {len(entities['extensions'])} extensions")
        
        # Extract compatibility statements
        statements = self.compatibility_extractor.extract_statements(text)
        logger.info(f"Extracted {len(statements)} compatibility statements")
        
        # Extract version pairs
        version_pairs = self.compatibility_extractor.extract_version_pairs(text)
        logger.info(f"Extracted {len(version_pairs)} version upgrade pairs")
        
        # Summarize statements
        summary = self.compatibility_extractor.summarize_statements(statements)
        
        # Calculate confidence scores for each component
        confidence_scores = self._calculate_confidence_scores(entities, statements)
        
        # Create result object
        result = ExtractionResult(
            source_url=source_url,
            source_title=source_title,
            entities=self._serialize_entities(entities),
            compatibility_statements=self._serialize_statements(statements),
            version_pairs=version_pairs,
            summary=summary,
            confidence_scores=confidence_scores,
            extraction_timestamp=self._get_timestamp()
        )
        
        return result
    
    def process_batch(self, documents: List[Dict]) -> List[ExtractionResult]:
        """
        Process a batch of documents.
        
        Args:
            documents: List of dicts with 'text', 'url', and 'title' keys
        
        Returns:
            List of ExtractionResult objects
        """
        results = []
        for doc in documents:
            try:
                result = self.process_document(
                    text=doc.get('content', ''),
                    source_url=doc.get('url', ''),
                    source_title=doc.get('title', 'Unknown')
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing document {doc.get('title', 'Unknown')}: {e}")
        
        return results
    
    def _serialize_entities(self, entities: Dict) -> Dict:
        """Serialize entity extraction results for JSON storage."""
        serialized = {}
        
        # Serialize versions
        serialized['versions'] = []
        for version, context in entities['versions']:
            serialized['versions'].append({
                'version': str(version),
                'major': version.major,
                'minor': version.minor,
                'patch': version.patch,
                'raw': version.raw,
                'context': context[:100]  # Truncate context for storage
            })
        
        # Copy other entity types as-is
        serialized['os_versions'] = entities['os_versions']
        serialized['extensions'] = entities['extensions']
        
        return serialized
    
    def _serialize_statements(self, statements: List[CompatibilityStatement]) -> List[Dict]:
        """Serialize compatibility statements for JSON storage."""
        return [
            {
                'type': s.statement_type,
                'subject_version': s.subject_version,
                'related_version': s.related_version,
                'component': s.component,
                'confidence': s.confidence,
                'raw_text': s.raw_text,
            }
            for s in statements
        ]
    
    def _calculate_confidence_scores(self, entities: Dict, statements: List[CompatibilityStatement]) -> Dict:
        """Calculate overall confidence scores for each component."""
        scores = {
            'activegate': self._avg_confidence([s for s in statements if s.component == 'activegate']),
            'os': self._avg_confidence([s for s in statements if s.component == 'os']),
            'extension': self._avg_confidence([s for s in statements if s.component == 'extension']),
            'managed_cluster': self._avg_confidence([s for s in statements if s.component == 'managed_cluster']),
        }
        return scores
    
    @staticmethod
    def _avg_confidence(statements: List[CompatibilityStatement]) -> float:
        """Calculate average confidence for a list of statements."""
        if not statements:
            return 0.0
        return sum(s.confidence for s in statements) / len(statements)
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


class ExtractedFact:
    """Represents a single extracted fact ready for storage in the graph."""
    
    def __init__(self, fact_type: str, subject: str, predicate: str, object_val: str, 
                 confidence: float, source_url: str, source_text: str):
        self.fact_type = fact_type  # 'compatibility', 'version_relation', 'deprecation', etc.
        self.subject = subject
        self.predicate = predicate  # e.g., 'compatible_with', 'requires', 'deprecated_in'
        self.object = object_val
        self.confidence = confidence
        self.source_url = source_url
        self.source_text = source_text
    
    def to_dict(self) -> Dict:
        return {
            'fact_type': self.fact_type,
            'subject': self.subject,
            'predicate': self.predicate,
            'object': self.object,
            'confidence': self.confidence,
            'source_url': self.source_url,
            'source_text': self.source_text,
        }


class FactConverter:
    """Convert extraction results into graph-ready facts."""
    
    @staticmethod
    def convert_to_facts(extraction_result: ExtractionResult) -> List[ExtractedFact]:
        """Convert extraction result into a list of facts for graph storage."""
        facts = []
        
        # Convert compatibility statements to facts
        for stmt in extraction_result.compatibility_statements:
            fact_type = 'compatibility_statement'
            predicate = f"{stmt['component']}_{stmt['type']}"
            
            fact = ExtractedFact(
                fact_type=fact_type,
                subject=stmt['subject_version'] or 'unknown',
                predicate=predicate,
                object_val=stmt['component'],
                confidence=stmt['confidence'],
                source_url=extraction_result.source_url,
                source_text=stmt['raw_text']
            )
            facts.append(fact)
        
        # Convert version pairs to upgrade path facts
        for pair in extraction_result.version_pairs:
            fact = ExtractedFact(
                fact_type='upgrade_path',
                subject=pair['from_version'],
                predicate='upgradeable_to',
                object_val=pair['to_version'],
                confidence=0.8,
                source_url=extraction_result.source_url,
                source_text=pair['raw_text']
            )
            facts.append(fact)
        
        return facts
