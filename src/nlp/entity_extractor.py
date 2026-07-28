import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


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
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
        )


class VersionParser:
    """Parse and normalize version numbers."""

    # Matches 2-part (1.330) and 3-part (1.330.0) versions.
    # Dynatrace uses 2-part versioning (e.g. 1.335), so the patch segment is optional.
    VERSION_PATTERN = r"(\d+)\.(\d+)(?:\.(\d+))?"

    @staticmethod
    def parse(version_str: str) -> Optional[Version]:
        """Parse a version string and return a Version object."""
        match = re.search(VersionParser.VERSION_PATTERN, version_str)
        if match:
            major, minor, patch = match.groups()
            return Version(
                int(major),
                int(minor),
                int(patch) if patch is not None else 0,
                version_str,
            )
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

    # Canonical Linux distro names based on Dynatrace support matrix naming.
    LINUX_DISTRO_PATTERNS = [
        (
            "Red Hat Enterprise Linux CoreOS",
            r"(?:Red\s+Hat\s+Enterprise\s+Linux\s+CoreOS|RHCOS)",
        ),
        (
            "Red Hat Enterprise Linux",
            r"(?:Red\s+Hat\s+Enterprise\s+Linux|\bRHEL\b|\bRed\s+Hat\b)",
        ),
        (
            "SUSE Linux Enterprise Server",
            r"(?:SUSE\s+Linux\s+Enterprise\s+Server|\bSLES\b)",
        ),
        ("CentOS Stream", r"CentOS\s+Stream"),
        ("Alpine Linux", r"Alpine\s+Linux(?:\s*\([^)]*\))?"),
        ("Amazon Linux", r"Amazon\s+Linux"),
        ("Azure Linux", r"Azure\s+Linux"),
        ("Bottlerocket", r"Bottlerocket"),
        ("Debian", r"Debian"),
        ("Fedora", r"Fedora"),
        ("Oracle Linux", r"Oracle\s+Linux"),
        ("Rocky Linux", r"Rocky\s+Linux"),
        ("Ubuntu", r"Ubuntu"),
        ("openSUSE", r"openSUSE"),
        ("AlmaLinux", r"AlmaLinux"),
        ("CentOS", r"CentOS"),
    ]

    OS_PATTERNS = {
        "windows": r"(?:Windows|Win)[\s\-]?(?:Server\s)?(\d+(?:\.\d+)*)",
        "macos": r"(?:macOS|OS\s?X)[\s\-]?(\d+(?:\.\d+)*)",
        "kubernetes": r"Kubernetes[\s\-]?(?:v)?(\d+\.\d+(?:\.\d+)*)",
    }

    @staticmethod
    def _normalize_version_token(token: str) -> Optional[str]:
        if not token:
            return None
        cleaned = token.strip()
        cleaned = re.sub(r"\bLTS\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"(?<=\d)\s*[xX]\b", "", cleaned).strip()
        cleaned = re.sub(r"\.$", "", cleaned)
        return cleaned or None

    @staticmethod
    def _extract_versions_from_tail(tail: str) -> List[str]:
        versions: List[str] = []
        for vr in re.finditer(
            r"(\d+(?:\.\d+){0,2}(?:\s*[xX])?(?:\s*LTS)?)(?:\s*(?:to|-)\s*(\d+(?:\.\d+){0,2}(?:\s*[xX])?(?:\s*LTS)?))?",
            tail,
            re.IGNORECASE,
        ):
            v1 = OSParser._normalize_version_token(vr.group(1) or "")
            v2 = OSParser._normalize_version_token(vr.group(2) or "")
            if not v1:
                continue
            if v2:
                versions.append(f"{v1}-{v2}")
            else:
                versions.append(v1)
        return versions

    @staticmethod
    def find_os_versions(text: str) -> List[Dict]:
        """Find OS version mentions in text."""
        os_versions = []

        # Detect Kubernetes version ranges like 'Kubernetes 1.22 to 1.28'
        for range_match in re.finditer(
            r"(Kubernetes)\s*(?:v)?(\d+\.\d+)\s*(?:to|-)\s*(\d+\.\d+)",
            text,
            re.IGNORECASE,
        ):
            os_versions.append(
                {
                    "family": "kubernetes",
                    "name": "Kubernetes",
                    "version": f"{range_match.group(2)}-{range_match.group(3)}",
                    "raw": range_match.group(0),
                    "position": range_match.start(),
                }
            )

        # Targeted parsing to avoid broad matches that pull unrelated numbers.
        targeted_patterns = [
            (r"(Windows Server|Windows)\s*[:\-]?\s*([^\n]{0,120})", "windows", None)
        ]
        for canonical_name, distro_regex in OSParser.LINUX_DISTRO_PATTERNS:
            targeted_patterns.append(
                (
                    rf"({distro_regex})\s*[:\-]?\s*([^\n]{{0,120}})",
                    "linux",
                    canonical_name,
                )
            )

        for pat, family, canonical_name in targeted_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                tail = (m.group(2) or "").strip()
                # skip if the tail looks like an extension header or unrelated phrase
                if "extension" in tail.lower() or "plugin" in tail.lower():
                    continue

                if family == "windows":
                    # Windows typically uses years like '2019', '2022'
                    for vr in re.finditer(r"\b(\d{4})\b", tail):
                        os_versions.append(
                            {
                                "family": family,
                                "name": m.group(1).strip(),
                                "version": vr.group(1),
                                "raw": m.group(0).strip(),
                                "position": m.start(),
                            }
                        )
                else:
                    for ver in OSParser._extract_versions_from_tail(tail):
                        os_versions.append(
                            {
                                "family": family,
                                "name": canonical_name,
                                "version": ver,
                                "raw": m.group(0).strip(),
                                "position": m.start(),
                            }
                        )

        # Fallback: generic pattern scan using OS_PATTERNS (captures remaining cases)
        for os_family, pattern in OSParser.OS_PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = (
                    match.group(0).split()[0] if match.group(0) else os_family.title()
                )
                if os_family == "windows" and "server" in match.group(0).lower():
                    name = "Windows Server"
                if os_family == "kubernetes":
                    name = "Kubernetes"
                os_versions.append(
                    {
                        "family": os_family,
                        "name": name,
                        "version": (
                            match.group(1) if len(match.groups()) > 0 else "unknown"
                        ),
                        "raw": match.group(0),
                        "position": match.start(),
                    }
                )

        # Deduplicate by (family, version, position)
        seen = set()
        deduped = []
        for o in os_versions:
            key = (
                o.get("family"),
                o.get("name"),
                str(o.get("version")),
                o.get("position"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(o)

        return deduped


class ExtensionParser:
    """Parse extension names and versions."""

    EXTENSION_PATTERNS = [
        # Matches phrases like "Custom Log Source extension requires version 2.1.0"
        r"([A-Z][A-Za-z0-9 &\-/]+?)\s+(?:extension|plugin|module)\b(?:[^\n\r]{0,80}?version\s*(?:[:]?\s*)?(\d+\.\d+(?:\.\d+)*))?",
        # Matches header lines like "Custom Application Monitoring Extension - Version 2.1.0"
        r"^(?:[-\s]*)?([A-Z][A-Za-z0-9 &\-/]+?\s*(?:Extension|extension|Plugin|plugin|Module|module))\s*(?:-|:)?\s*Version\s*(\d+\.\d+(?:\.\d+)*)",
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
                cleaned_name = re.sub(
                    r"\b(extension|plugin|module)\b", "", ext_name, flags=re.IGNORECASE
                ).strip()
                # Normalize whitespace and capitalization
                normalized = re.sub(r"\s+", " ", cleaned_name)
                signature = (normalized.lower(), ext_version)
                if signature in seen:
                    continue

                # Filter obvious non-extension phrases
                stopwords = {
                    "you",
                    "must",
                    "upgrade",
                    "latest",
                    "improved",
                    "performance",
                    "processing",
                    "deploy",
                    "to",
                    "the",
                    "for",
                    "version",
                    "requires",
                }
                tokens = set(re.sub(r"[^a-z0-9 ]", " ", normalized.lower()).split())
                if tokens & stopwords:
                    continue

                seen.add(signature)

                extensions.append(
                    {
                        "name": normalized,
                        "version": ext_version,
                        "raw": match.group(0),
                        "position": match.start(),
                    }
                )
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
            "versions": self.version_parser.find_all_versions(text),
            "os_versions": self.os_parser.find_os_versions(text),
            "extensions": self.extension_parser.find_extensions(text),
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
