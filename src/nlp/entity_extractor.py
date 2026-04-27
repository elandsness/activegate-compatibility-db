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
    
    VERSION_PATTERN = r'(\d+)\.(\d+)\.(\d+)'
    
    @staticmethod
    def parse(version_str: str) -> Optional[Version]:
        """Parse a version string and return a Version object."""
        match = re.search(VersionParser.VERSION_PATTERN, version_str)
        if match:
            major, minor, patch = match.groups()
            return Version(int(major), int(minor), int(patch), version_str)
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
        for os_family, pattern in OSParser.OS_PATTERNS.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                os_versions.append({
                    'family': os_family,
                    'version': match.group(1) if len(match.groups()) > 0 else 'unknown',
                    'raw': match.group(0),
                    'position': match.start()
                })
        return os_versions


class ExtensionParser:
    """Parse extension names and versions."""
    
    EXTENSION_PATTERNS = [
        r'(?:extension|plugin)\s+(?:named\s+)?["\']?(\w+(?:\s\w+)*)["\']?(?:\s+(?:version|v)\s+(\d+\.\d+(?:\.\d+)*))?',
        r'(\w+)\s+extension(?:\s+v(?:ersion)?\s+(\d+\.\d+(?:\.\d+)*))?',
    ]
    
    @staticmethod
    def find_extensions(text: str) -> List[Dict]:
        """Find extension mentions in text."""
        extensions = []
        for pattern in ExtensionParser.EXTENSION_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                ext_name = match.group(1).strip() if len(match.groups()) > 0 else None
                ext_version = match.group(2) if len(match.groups()) > 1 else None
                if ext_name:
                    extensions.append({
                        'name': ext_name,
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
