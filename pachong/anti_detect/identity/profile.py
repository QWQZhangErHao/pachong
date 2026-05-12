"""Enriched BrowserIdentity profile with device-realistic distribution data.

Contains the knowledge base of real device distributions used by the
Geo-Bound generator to create coherent, realistic browser identities.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlatformProfile:
    """Realistic device profile for a given platform + region."""
    platform: str  # "Win32", "MacIntel", "Linux x86_64"
    os_name: str
    os_versions: list[tuple[str, float]]  # (version, prevalence_weight)

    # Screen resolution distribution (width, height, prevalence_weight)
    screen_distribution: list[tuple[int, int, float]]

    # GPU distribution
    gpu_distribution: list[tuple[str, str, float]]  # (vendor, renderer, weight)

    # Font stacks
    common_fonts: list[str]
    platform_signature_fonts: list[str]


# ── Platform Profiles ────────────────────────────────────────────────────────

WINDOWS_PROFILE = PlatformProfile(
    platform="Win32",
    os_name="Windows NT 10.0",
    os_versions=[("10.0", 0.85), ("11.0", 0.15)],
    screen_distribution=[
        (1920, 1080, 0.40),
        (1366, 768, 0.25),
        (2560, 1440, 0.12),
        (3840, 2160, 0.08),
        (1536, 864, 0.10),
        (1440, 900, 0.05),
    ],
    gpu_distribution=[
        ("Google Inc. (Intel)", "Intel Iris Xe Graphics", 0.25),
        ("Google Inc. (Intel)", "Intel UHD Graphics 620", 0.15),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce RTX 3060", 0.12),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce GTX 1650", 0.08),
        ("Google Inc. (AMD)", "AMD Radeon Graphics", 0.10),
        ("Google Inc. (Intel)", "Intel HD Graphics 630", 0.08),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce RTX 4060", 0.07),
        ("Google Inc. (AMD)", "AMD Radeon RX 580", 0.05),
        ("Google Inc. (Intel)", "Intel UHD Graphics 730", 0.05),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce RTX 4070", 0.05),
    ],
    common_fonts=[
        "Arial", "Times New Roman", "Courier New", "Verdana", "Georgia",
        "Comic Sans MS", "Trebuchet MS", "Arial Black", "Impact",
    ],
    platform_signature_fonts=[
        "Segoe UI", "Calibri", "Cambria", "Consolas", "Constantia",
        "Corbel", "Microsoft Sans Serif", "Tahoma",
    ],
)

MAC_PROFILE = PlatformProfile(
    platform="MacIntel",
    os_name="Mac OS X",
    os_versions=[("10_15_7", 0.30), ("14_0", 0.35), ("15_0", 0.25), ("13_6", 0.10)],
    screen_distribution=[
        (2560, 1440, 0.30),
        (2880, 1800, 0.25),
        (1920, 1080, 0.15),
        (3456, 2234, 0.10),
        (3024, 1964, 0.10),
        (3840, 2160, 0.10),
    ],
    gpu_distribution=[
        ("Apple Inc.", "Apple M1", 0.25),
        ("Apple Inc.", "Apple M2", 0.20),
        ("Apple Inc.", "Apple M3", 0.15),
        ("Apple Inc.", "Apple M1 Pro", 0.08),
        ("Apple Inc.", "Apple M2 Pro", 0.08),
        ("Apple Inc.", "Apple M3 Pro", 0.06),
        ("Apple Inc.", "Intel Iris Plus Graphics 645", 0.05),
        ("Apple Inc.", "AMD Radeon Pro 5500M", 0.05),
        ("Apple Inc.", "Apple M4", 0.04),
        ("Apple Inc.", "Apple M2 Max", 0.04),
    ],
    common_fonts=[
        "Arial", "Times New Roman", "Courier New", "Verdana", "Georgia",
        "Comic Sans MS", "Trebuchet MS", "Arial Black",
    ],
    platform_signature_fonts=[
        "Helvetica", "Helvetica Neue", "SF Pro Display", "SF Pro Text",
        "SF Mono", "Menlo", "Monaco", "Apple Color Emoji",
    ],
)

LINUX_PROFILE = PlatformProfile(
    platform="Linux x86_64",
    os_name="Linux",
    os_versions=[("x86_64", 0.60), ("i686", 0.20), ("aarch64", 0.20)],
    screen_distribution=[
        (1920, 1080, 0.45),
        (2560, 1440, 0.20),
        (1366, 768, 0.18),
        (3840, 2160, 0.10),
        (1680, 1050, 0.07),
    ],
    gpu_distribution=[
        ("Google Inc. (Intel)", "Intel Iris Xe Graphics", 0.20),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce RTX 3060", 0.10),
        ("Google Inc. (AMD)", "AMD Radeon RX 6700 XT", 0.08),
        ("Google Inc. (Intel)", "Intel UHD Graphics", 0.15),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce GTX 1660", 0.10),
        ("Google Inc. (AMD)", "AMD Radeon Graphics", 0.12),
        ("Google Inc. (Intel)", "Mesa Intel Xe Graphics", 0.10),
        ("Google Inc. (NVIDIA)", "NVIDIA GeForce RTX 4070", 0.05),
        ("Google Inc. (AMD)", "AMD Radeon RX 7800 XT", 0.05),
        ("Google Inc. (Intel)", "Intel Arc Graphics", 0.05),
    ],
    common_fonts=[
        "Arial", "Times New Roman", "Courier New", "Verdana",
        "DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
    ],
    platform_signature_fonts=[
        "Liberation Sans", "Liberation Serif", "Liberation Mono",
        "Ubuntu", "Noto Sans", "Cantarell",
    ],
)


@dataclass
class GeoLocationInfo:
    """Information derived from a GeoIP lookup."""
    country_code: str
    country_name: str
    city: str | None
    latitude: float
    longitude: float
    timezone: str
    locale: str
    languages: list[str]
    continent: str


# Timezone → locale mapping (realistic distributions)
TIMEZONE_LOCALE_MAP: dict[str, tuple[str, list[str]]] = {
    "America/New_York": ("en-US", ["en-US", "en"]),
    "America/Chicago": ("en-US", ["en-US", "en", "es"]),
    "America/Los_Angeles": ("en-US", ["en-US", "en", "es"]),
    "America/Toronto": ("en-CA", ["en-CA", "en", "fr"]),
    "America/Sao_Paulo": ("pt-BR", ["pt-BR", "pt", "en"]),
    "America/Mexico_City": ("es-MX", ["es-MX", "es", "en"]),
    "Europe/London": ("en-GB", ["en-GB", "en"]),
    "Europe/Paris": ("fr-FR", ["fr-FR", "fr", "en"]),
    "Europe/Berlin": ("de-DE", ["de-DE", "de", "en"]),
    "Europe/Madrid": ("es-ES", ["es-ES", "es", "en"]),
    "Europe/Rome": ("it-IT", ["it-IT", "it", "en"]),
    "Europe/Amsterdam": ("nl-NL", ["nl-NL", "nl", "en"]),
    "Europe/Stockholm": ("sv-SE", ["sv-SE", "sv", "en"]),
    "Europe/Warsaw": ("pl-PL", ["pl-PL", "pl", "en"]),
    "Asia/Tokyo": ("ja-JP", ["ja-JP", "ja", "en"]),
    "Asia/Shanghai": ("zh-CN", ["zh-CN", "zh", "en"]),
    "Asia/Seoul": ("ko-KR", ["ko-KR", "ko", "en"]),
    "Asia/Singapore": ("en-SG", ["en-SG", "en", "zh"]),
    "Asia/Kolkata": ("hi-IN", ["hi-IN", "hi", "en"]),
    "Asia/Dubai": ("ar-AE", ["ar-AE", "ar", "en"]),
    "Asia/Bangkok": ("th-TH", ["th-TH", "th", "en"]),
    "Asia/Hong_Kong": ("zh-HK", ["zh-HK", "zh", "en"]),
    "Australia/Sydney": ("en-AU", ["en-AU", "en"]),
    "Pacific/Auckland": ("en-NZ", ["en-NZ", "en"]),
    "Africa/Cairo": ("ar-EG", ["ar-EG", "ar", "en"]),
    "Africa/Johannesburg": ("en-ZA", ["en-ZA", "en", "af"]),
}


PLATFORM_BY_CONTINENT: dict[str, list[tuple[PlatformProfile, float]]] = {
    "NA": [(WINDOWS_PROFILE, 0.55), (MAC_PROFILE, 0.35), (LINUX_PROFILE, 0.10)],
    "SA": [(WINDOWS_PROFILE, 0.70), (LINUX_PROFILE, 0.15), (MAC_PROFILE, 0.15)],
    "EU": [(WINDOWS_PROFILE, 0.50), (MAC_PROFILE, 0.30), (LINUX_PROFILE, 0.20)],
    "AS": [(WINDOWS_PROFILE, 0.65), (MAC_PROFILE, 0.15), (LINUX_PROFILE, 0.20)],
    "OC": [(MAC_PROFILE, 0.45), (WINDOWS_PROFILE, 0.40), (LINUX_PROFILE, 0.15)],
    "AF": [(WINDOWS_PROFILE, 0.60), (LINUX_PROFILE, 0.25), (MAC_PROFILE, 0.15)],
}
