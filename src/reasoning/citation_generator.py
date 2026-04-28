import logging
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Represents a source citation for a compatibility finding."""
    source_url: str
    source_title: str
    source_type: str  # 'release_notes', 'extension_docs', 'end_of_support', 'hub'
    relevant_text: str
    extracted_date: str
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'source_url': self.source_url,
            'source_title': self.source_title,
            'source_type': self.source_type,
            'relevant_text': self.relevant_text,
            'extracted_date': self.extracted_date,
            'confidence': self.confidence
        }


class CitationGenerator:
    """
    Generates citations for compatibility findings.
    Links back to source text/release notes for explainability.
    """
    
    def __init__(self):
        self.source_registry = {}
    
    def register_source(self, url: str, title: str, source_type: str):
        """Register a source document."""
        self.source_registry[url] = {
            'title': title,
            'type': source_type,
            'registered_at': datetime.now().isoformat()
        }
    
    def generate_citation(self, source_url: str, relevant_text: str, 
                         confidence: float = 0.8) -> Optional[Citation]:
        """
        Generate a citation for a source.
        
        Args:
            source_url: URL of the source document
            relevant_text: Text from the source that's relevant
            confidence: Confidence score for this citation
        
        Returns:
            Citation object or None if source not found
        """
        source_info = self.source_registry.get(source_url)
        
        if not source_info:
            logger.warning(f"Source not registered: {source_url}")
            return None
        
        return Citation(
            source_url=source_url,
            source_title=source_info['title'],
            source_type=source_info['type'],
            relevant_text=relevant_text[:500],  # Limit text length
            extracted_date=source_info['registered_at'],
            confidence=confidence
        )
    
    def generate_citations_from_issues(self, issues: List) -> List[Citation]:
        """Generate citations from a list of issues."""
        citations = []
        
        for issue in issues:
            if hasattr(issue, 'source_url') and issue.source_url:
                citation = self.generate_citation(
                    source_url=issue.source_url,
                    relevant_text=issue.source_text or issue.message,
                    confidence=getattr(issue, 'confidence', 0.5)
                )
                if citation:
                    citations.append(citation)
        
        return citations
    
    def format_citation_text(self, citation: Citation) -> str:
        """Format a citation for display."""
        lines = [
            f"Source: {citation.source_title}",
            f"URL: {citation.source_url}",
            f"Type: {citation.source_type}",
            f"Relevant: \"{citation.relevant_text[:200]}...\"",
            f"Confidence: {citation.confidence:.0%}",
            f"Extracted: {citation.extracted_date}"
        ]
        return '\n'.join(lines)
    
    def format_citations_for_output(self, citations: List[Citation]) -> str:
        """Format multiple citations for output."""
        if not citations:
            return "No sources cited."
        
        output = ["Sources:", "-" * 40]
        
        for i, citation in enumerate(citations, 1):
            output.append(f"\n[{i}] {citation.source_title}")
            output.append(f"    URL: {citation.source_url}")
            output.append(f"    Type: {citation.source_type}")
            output.append(f"    Confidence: {citation.confidence:.0%}")
        
        return '\n'.join(output)


class QueryProcessor:
    """
    Processes natural language queries and converts them to structured checks.
    """
    
    def __init__(self, reasoner, semantic_search=None, citation_generator=None):
        self.reasoner = reasoner
        self.semantic_search = semantic_search
        self.citation_generator = citation_generator
    
    def process_query(self, query: str) -> Dict:
        """
        Process a natural language query.
        
        Args:
            query: Natural language query (e.g., "Can I run extension X on AG 1.335?")
        
        Returns:
            Dict with parsed parameters and result
        """
        query = query.lower()
        
        # Extract version information
        import re
        version_pattern = r'(\d+\.\d+(?:\.\d+)*)'
        versions = re.findall(version_pattern, query)
        
        # Determine query type
        if 'extension' in query or 'ext' in query:
            query_type = 'extension_compatibility'
        elif 'os' in query or 'windows' in query or 'linux' in query:
            query_type = 'os_compatibility'
        elif 'managed' in query or 'cluster' in query:
            query_type = 'managed_compatibility'
        else:
            query_type = 'general_compatibility'
        
        return {
            'query_type': query_type,
            'versions_found': versions,
            'query': query
        }
    
    def parse_structured_input(self, input_data: Dict) -> Dict:
        """
        Parse structured input (from CLI/API) into compatibility check parameters.
        
        Args:
            input_data: Dict with current_state and target_state
        
        Returns:
            Parameters for compatibility check
        """
        params = {
            'current_version': input_data.get('current_activegate_version'),
            'target_version': input_data.get('target_activegate_version'),
            'os_family': input_data.get('os_family'),
            'os_version': input_data.get('os_version'),
            'managed_cluster_version': input_data.get('managed_cluster_version'),
            'extensions': input_data.get('extensions', [])
        }
        
        return params
    
    def format_result_for_display(self, result) -> str:
        """Format compatibility result for user display."""
        output = []
        
        # Status header
        status_emoji = {
            'GO': '✅',
            'GO_WITH_CAUTION': '⚠️',
            'NO_GO': '❌',
            'UNKNOWN': '❓'
        }
        
        emoji = status_emoji.get(result.status.value, '❓')
        output.append(f"\n{emoji} Status: {result.status.value}")
        output.append(f"ActiveGate Version: {result.activegate_version}")
        
        if result.target_version != 'N/A':
            output.append(f"Target: {result.target_version}")
        
        output.append(f"Confidence: {result.confidence:.0%}")
        
        # Issues
        if result.issues:
            output.append(f"\n🚫 Issues ({len(result.issues)}):")
            for issue in result.issues:
                output.append(f"  - [{issue.severity.upper()}] {issue.message}")
                if issue.recommendation:
                    output.append(f"    → {issue.recommendation}")
        
        # Warnings
        if result.warnings:
            output.append(f"\n⚠️ Warnings ({len(result.warnings)}):")
            for warning in result.warnings:
                output.append(f"  - {warning.message}")
                if warning.recommendation:
                    output.append(f"    → {warning.recommendation}")
        
        # Recommendations
        if result.recommendations:
            output.append(f"\n📋 Recommendations:")
            for rec in result.recommendations:
                output.append(f"  • {rec}")
        
        # Citations
        if result.citations:
            output.append(f"\n📚 Sources ({len(result.citations)}):")
            for cite in result.citations:
                output.append(f"  - {cite['source_title']}: {cite['source_url']}")
        
        return '\n'.join(output)