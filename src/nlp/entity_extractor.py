import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class Version:
    major: int
    minor: int
    patch: int
    raw: str

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __lt__(self, other):
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        return self.patch < other.patch
    
    def __eq__(self, other):
        return self.major == other.major and self.minor == other.minor and self.patch == other.patch


class VersionParser:
    """Parse and normalize version numbers."""

    # Matches 2-part (1.330) and 3-part (1.330.0) versions.
    # Dynatrace uses 2-part versioning (e.g. 1.335), so the patch segment is optional.
    VERSION_PATTERN = r'(\d+)\.(\d+)(?:\.(\d+))?'

    @staticmethod
    def parse(version_str: str) -> Optional[Version]:
        """Parse a version string and return a Version object."""
        match = re.search(VersionParser.VERSION_PATTERN, version_str)
        if match:
            major, minor, patch = match.groups()
            return Version(int(major), int(minor), int(patch) if patch is not None else 0, version_str)
        return None

    @staticmethod
    def find_all_versions(text: str) -> List[Tuple[Version, str]]:
        """Find all version numbers in text and their context."""
        versions = []
        for match in re.finditer(VersionParser.VERSION_PATTERN, text):
            version = VersionParser.parse(match.group(0))
            if version:
                # Get surrounding context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                versions.append((version, context))
        return versions


class OSParser:
    """Parse operating system versions and families."""
    
    OS_PATTERNS = {
        'windows': r'(?:Windows|Win)[\s\-]?(?:Server\s)?(\d+(?:\.\d+)*)',
        'linux': r'(?:Linux|RHEL|CentOS|Ubuntu)[\s\-]?(\d+(?:\.\d+)*)',
        'macos': r'(?:macOS|OS\s?X)[\s\-]?(\d+(?:\.\d+)*)',
        'kubernetes': r'Kubernetes[\s\-]?(?:v)?(\d+\.\d+(?:\.\d+)*)',
    }
    
    @staticmethod
    def find_os_versions(text: str) -> List[Dict]:
        """Find OS version mentions in text."""
        os_versions = []

        # Detect Kubernetes version ranges like 'Kubernetes 1.22 to 1.28'
        for range_match in re.finditer(r'(Kubernetes)\s*(?:v)?(\d+\.\d+)\s*(?:to|-)\s*(\d+\.\d+)', text, re.IGNORECASE):
            os_versions.append({
                'family': 'kubernetes',
                'version': f"{range_match.group(2)}-{range_match.group(3)}",
                'raw': range_match.group(0),
                'position': range_match.start()
            })

        # Targeted distro parsing to avoid broad matches that pull unrelated numbers
        distro_patterns = [
            (r'(Windows Server|Windows)\s*[:\-]?\s*([^\n]{0,120})', 'windows'),
            (r'(CentOS|RHEL|Red Hat Enterprise Linux|Red Hat|Ubuntu)\s*[:\-]?\s*([^\n]{0,120})', 'linux'),
        ]

        for pat, family in distro_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                tail = (m.group(2) or '').strip()
                # skip if the tail looks like an extension header or unrelated phrase
                if 'extension' in tail.lower() or 'plugin' in tail.lower():
                    continue

                if family == 'windows':
                    # Windows typically uses years like '2019', '2022'
                    for vr in re.finditer(r'\b(\d{4})\b', tail):
                        os_versions.append({'family': family, 'version': vr.group(1), 'raw': m.group(0).strip(), 'position': m.start()})
                else:
                    # capture ranges like '1.22 to 1.28' or dotted versions like '20.04'
                    for vr in re.finditer(r'(\d+\.\d+(?:\.\d+)?)(?:\s*(?:to|-)\s*(\d+\.\d+(?:\.\d+)?))?', tail):
                        v1 = vr.group(1)
                        v2 = vr.group(2)
                        if v2:
                            ver = f"{v1}-{v2}"
                        else:
                            ver = v1
                        os_versions.append({'family': family, 'version': ver, 'raw': m.group(0).strip(), 'position': m.start()})

        # Fallback: generic pattern scan using OS_PATTERNS (captures remaining cases)
        for os_family, pattern in OSParser.OS_PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                os_versions.append({
                    'family': os_family,
                    'version': match.group(1) if len(match.groups()) > 0 else 'unknown',
                    'raw': match.group(0),
                    'position': match.start()
                })

        # Deduplicate by (family, version, position)
        seen = set()
        deduped = []
        for o in os_versions:
            key = (o['family'], str(o['version']), o['position'])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(o)

        return deduped


class ExtensionParser:
    """Parse extension names and versions."""
    
    EXTENSION_PATTERNS = [
        # Matches phrases like "Custom Log Source extension requires version 2.1.0"
        r'([A-Z][A-Za-z0-9 &\-/]+?)\s+(?:extension|plugin|module)\b(?:[^\n\r]{0,80}?version\s*(?:[:]?\s*)?(\d+\.\d+(?:\.\d+)*))?',
        # Matches header lines like "Custom Application Monitoring Extension - Version 2.1.0"
        r'^(?:[-\s]*)?([A-Z][A-Za-z0-9 &\-/]+?\s*(?:Extension|extension|Plugin|plugin|Module|module))\s*(?:-|:)?\s*Version\s*(\d+\.\d+(?:\.\d+)*)',
    ]
    
    @staticmethod
    def find_extensions(text: str) -> List[Dict]:
        """Find extension mentions in text."""
        extensions = []
        seen = set()
        for pattern in ExtensionParser.EXTENSION_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                ext_name = None
                ext_version = None
                try:
                    ext_name = match.group(1).strip()
                except IndexError:
                    ext_name = None
                try:
                    ext_version = match.group(2)
                except IndexError:
                    ext_version = None

                if not ext_name:
                    continue

                # Clean common suffixes
                cleaned_name = re.sub(r"\b(extension|plugin|module)\b", "", ext_name, flags=re.IGNORECASE).strip()
                # Normalize whitespace and capitalization
                normalized = re.sub(r"\s+", " ", cleaned_name)
                signature = (normalized.lower(), ext_version)
                if signature in seen:
                    continue

                # Filter obvious non-extension phrases
                stopwords = {'you', 'must', 'upgrade', 'latest', 'improved', 'performance', 'processing', 'deploy', 'to', 'the', 'for', 'version', 'requires'}
                tokens = set(re.sub(r'[^a-z0-9 ]', ' ', normalized.lower()).split())
                if tokens & stopwords:
                    continue

                seen.add(signature)

                extensions.append({
                    'name': normalized,
                    'version': ext_version,
                    'raw': match.group(0),
                    'position': match.start()
                })
        return extensions


class EntityExtractor:
    """Main class for extracting entities from text."""
    
    def __init__(self):
        self.version_parser = VersionParser()
        self.os_parser = OSParser()
        self.extension_parser = ExtensionParser()
    
    def extract_all_entities(self, text: str) -> Dict:
        """Extract all entity types from text."""
        return {
            'versions': self.version_parser.find_all_versions(text),
            'os_versions': self.os_parser.find_os_versions(text),
            'extensions': self.extension_parser.find_extensions(text),
        }
    
    def extract_versions(self, text: str) -> List[Tuple[Version, str]]:
        """Extract version numbers and their context."""
        return self.version_parser.find_all_versions(text)
    
    def extract_os_versions(self, text: str) -> List[Dict]:
        """Extract OS versions and families."""
        return self.os_parser.find_os_versions(text)
    
    def extract_extensions(self, text: str) -> List[Dict]:
        """Extract extension mentions."""
        return self.extension_parser.find_extensions(text)
