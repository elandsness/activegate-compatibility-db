import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Provides semantic search capabilities for fuzzy matching of compatibility queries.
    Uses simple text-based similarity when embeddings are not available.
    """
    
    def __init__(self):
        self.index = {}
        self.documents = []
    
    def add_document(self, doc_id: str, content: str, metadata: Dict = None):
        """
        Add a document to the search index.
        
        Args:
            doc_id: Unique identifier for the document
            content: Text content to index
            metadata: Optional metadata about the document
        """
        self.documents.append({
            'id': doc_id,
            'content': content,
            'metadata': metadata or {}
        })
        
        # Simple token-based indexing
        tokens = self._tokenize(content)
        for token in tokens:
            if token not in self.index:
                self.index[token] = []
            self.index[token].append(doc_id)
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search for documents matching a query.
        
        Args:
            query: Search query string
            top_k: Number of results to return
        
        Returns:
            List of matching documents with scores
        """
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        # Calculate scores for each document
        scores = {}
        for doc in self.documents:
            doc_tokens = self._tokenize(doc['content'])
            
            # Simple Jaccard-like similarity
            common = set(query_tokens) & set(doc_tokens)
            total = set(query_tokens) | set(doc_tokens)
            
            if total:
                score = len(common) / len(total)
                scores[doc['id']] = score
        
        # Sort by score and return top k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_id, score in sorted_results[:top_k]:
            if score > 0:
                doc = next(d for d in self.documents if d['id'] == doc_id)
                results.append({
                    'id': doc_id,
                    'score': score,
                    'content': doc['content'][:200] + '...',
                    'metadata': doc['metadata']
                })
        
        return results
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r'\b\w+\b', text.lower())
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        return [t for t in tokens if t not in stop_words and len(t) > 2]
    
    def find_similar_versions(self, version: str, all_versions: List[str]) -> List[Tuple[str, float]]:
        """
        Find similar versions using fuzzy matching.
        
        Args:
            version: Version to match
            all_versions: List of all available versions
        
        Returns:
            List of (version, similarity_score) tuples
        """
        version_parts = version.split('.')
        
        matches = []
        for av in all_versions:
            av_parts = av.split('.')
            
            # Calculate similarity based on version parts
            score = 0.0
            
            # Major version match
            if len(version_parts) > 0 and len(av_parts) > 0:
                if version_parts[0] == av_parts[0]:
                    score += 0.5
            
            # Minor version match (within 2 versions)
            if len(version_parts) > 1 and len(av_parts) > 1:
                try:
                    v_minor = int(version_parts[1])
                    av_minor = int(av_parts[1])
                    diff = abs(v_minor - av_minor)
                    if diff == 0:
                        score += 0.3
                    elif diff == 1:
                        score += 0.15
                except:
                    pass
            
            # Patch version match
            if len(version_parts) > 2 and len(av_parts) > 2:
                if version_parts[2] == av_parts[2]:
                    score += 0.2
            
            if score > 0:
                matches.append((av, score))
        
        # Sort by score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches


class HistoricalQuery:
    """
    Handles historical compatibility queries for past versions.
    Useful for enterprises running older software.
    """
    
    def __init__(self):
        self.version_history = {}
        self.compatibility_history = {}
    
    def add_version_history(self, version: str, release_date: str, eos_date: str = None):
        """
        Add version to history.
        
        Args:
            version: Version string (e.g., '1.330')
            release_date: Release date in ISO format
            eos_date: End of support date (optional)
        """
        self.version_history[version] = {
            'release_date': release_date,
            'eos_date': eos_date,
            'status': 'active' if not eos_date else 'deprecated'
        }
    
    def add_compatibility_history(self, ag_version: str, managed_version: str, 
                                   compatible: bool, source: str, date: str):
        """
        Add compatibility record to history.
        
        Args:
            ag_version: ActiveGate version
            managed_version: Managed cluster version
            compatible: Whether compatible
            source: Source of this information
            date: Date when this was recorded
        """
        key = f"{ag_version}|{managed_version}"
        
        if key not in self.compatibility_history:
            self.compatibility_history[key] = []
        
        self.compatibility_history[key].append({
            'compatible': compatible,
            'source': source,
            'date': date,
            'recorded_at': datetime.now().isoformat()
        })
    
    def is_version_supported(self, version: str, check_date: str = None) -> Dict:
        """
        Check if a version was/is supported at a given time.
        
        Args:
            version: Version to check
            check_date: Date to check (default: now)
        
        Returns:
            Dict with support status and details
        """
        if version not in self.version_history:
            return {
                'supported': False,
                'reason': 'Version not in history'
            }
        
        version_info = self.version_history[version]
        
        if check_date is None:
            check_date = datetime.now().isoformat()
        
        # Check if past EOL
        if version_info.get('eos_date'):
            eos_date = version_info['eos_date']
            if check_date > eos_date:
                return {
                    'supported': False,
                    'reason': f'Version reached end of support on {eos_date}',
                    'eos_date': eos_date
                }
        
        return {
            'supported': True,
            'release_date': version_info.get('release_date'),
            'eos_date': version_info.get('eos_date'),
            'status': version_info.get('status')
        }
    
    def get_compatibility_at_time(self, ag_version: str, managed_version: str, 
                                   check_date: str = None) -> Optional[bool]:
        """
        Get compatibility status at a specific point in time.
        
        Args:
            ag_version: ActiveGate version
            managed_version: Managed cluster version
            check_date: Date to check (default: most recent)
        
        Returns:
            Boolean or None if no data
        """
        key = f"{ag_version}|{managed_version}"
        
        if key not in self.compatibility_history:
            return None
        
        history = self.compatibility_history[key]
        
        if not history:
            return None
        
        if check_date is None:
            # Return most recent
            return history[-1].get('compatible')
        
        # Find record at or before check_date
        for record in reversed(history):
            if record['date'] <= check_date:
                return record.get('compatible')
        
        return None
    
    def get_upgrade_timeline(self, from_version: str, to_version: str) -> Dict:
        """
        Get timeline information for an upgrade path.
        
        Args:
            from_version: Starting version
            to_version: Target version
        
        Returns:
            Dict with timeline details
        """
        from_info = self.version_history.get(from_version, {})
        to_info = self.version_history.get(to_version, {})
        
        timeline = {
            'from_version': from_version,
            'to_version': to_version,
            'from_release': from_info.get('release_date'),
            'to_release': to_info.get('release_date'),
            'from_eos': from_info.get('eos_date'),
            'to_eos': to_info.get('eos_date'),
            'from_status': from_info.get('status', 'unknown'),
            'to_status': to_info.get('status', 'unknown')
        }
        
        # Calculate upgrade window
        if from_info.get('release_date') and to_info.get('release_date'):
            try:
                from_date = datetime.fromisoformat(from_info['release_date'])
                to_date = datetime.fromisoformat(to_info['release_date'])
                delta = to_date - from_date
                timeline['upgrade_window_days'] = delta.days
            except:
                pass
        
        return timeline
    
    def find_supported_alternatives(self, version: str) -> List[Dict]:
        """
        Find supported alternatives to an unsupported version.
        
        Args:
            version: Unsupported version
        
        Returns:
            List of alternative versions with details
        """
        alternatives = []
        
        for v, info in self.version_history.items():
            if v == version:
                continue
            
            # Skip older unsupported versions
            if info.get('eos_date'):
                continue
            
            # Add as alternative
            alternatives.append({
                'version': v,
                'release_date': info.get('release_date'),
                'status': info.get('status'),
                'reason': f'Supported alternative to {version}'
            })
        
        # Sort by version (newest first)
        alternatives.sort(key=lambda x: x['version'], reverse=True)
        
        return alternatives