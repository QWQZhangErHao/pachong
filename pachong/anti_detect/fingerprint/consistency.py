"""Cross-layer fingerprint consistency validator.

Ensures all fingerprint layers are internally coherent. A MacIntel platform
cannot have Windows-only fonts. A Japanese timezone must have Japanese locale.
The GPU must exist for the declared platform.

This validator runs at identity generation time and on each reuse to catch
configuration drift before the identity is deployed.
"""

from __future__ import annotations

from pachong.core.models import BrowserIdentity

# Platform-specific validation rules
PLATFORM_FONTS = {
    "Win32": {"Segoe UI", "Calibri", "Cambria", "Tahoma"},
    "MacIntel": {"Helvetica", "Helvetica Neue", "SF Pro Display", "Menlo", "Monaco"},
    "Linux x86_64": {"Liberation Sans", "Ubuntu", "Noto Sans", "Cantarell"},
}

# GPU must exist on the platform
PLATFORM_GPU_PREFIXES = {
    "Win32": {"Intel", "NVIDIA", "AMD", "Google"},
    "MacIntel": {"Apple", "Intel", "AMD"},
    "Linux x86_64": {"Intel", "NVIDIA", "AMD", "Mesa"},
}

# Platform must have a matching UA prefix
UA_PLATFORM_MAP = {
    "Windows NT": "Win32",
    "Macintosh": "MacIntel",
    "X11; Linux": "Linux x86_64",
}


class ConsistencyReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def __str__(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"Errors ({len(self.errors)}): " + "; ".join(self.errors))
        if self.warnings:
            parts.append(f"Warnings ({len(self.warnings)}): " + "; ".join(self.warnings))
        return "\n".join(parts) if parts else "OK (fully consistent)"


def validate_identity(identity: BrowserIdentity) -> ConsistencyReport:
    """Run all consistency checks on a browser identity.

    Returns a ConsistencyReport with any issues found.
    """
    report = ConsistencyReport()

    _check_platform_ua_match(identity, report)
    _check_platform_fonts(identity, report)
    _check_platform_gpu(identity, report)
    _check_screen_gpu_match(identity, report)
    _check_timezone_locale_match(identity, report)
    _check_hardware_values(identity, report)
    _check_canvas_consistency(identity, report)
    _check_tls_consistency(identity, report)

    return report


def _check_platform_ua_match(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """User-Agent must declare the correct platform."""
    ua = identity.user_agent.lower()
    platform = identity.platform

    if platform == "Win32" and "windows nt" not in ua and "win64" not in ua:
        report.add_error(f"Win32 platform but UA doesn't mention Windows: {identity.user_agent[:80]}")
    elif platform == "MacIntel" and "macintosh" not in ua and "mac os x" not in ua:
        report.add_error(f"MacIntel platform but UA doesn't mention Mac: {identity.user_agent[:80]}")
    elif platform == "Linux x86_64" and "linux" not in ua and "x11" not in ua:
        report.add_error(f"Linux platform but UA doesn't mention Linux: {identity.user_agent[:80]}")


def _check_platform_fonts(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """Platform-specific fonts must be present."""
    platform_fonts = PLATFORM_FONTS.get(identity.platform, set())
    if not platform_fonts:
        return

    installed = set(identity.installed_fonts) if identity.installed_fonts else set()
    if not installed:
        report.add_warning("No fonts configured — sites may fingerprint this")
        return

    missing = [f for f in platform_fonts if f not in installed]
    if len(missing) > len(platform_fonts) * 0.6:
        report.add_error(f"Too many platform-signature fonts missing: {missing}")


def _check_platform_gpu(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """GPU must exist on this platform."""
    valid_prefixes = PLATFORM_GPU_PREFIXES.get(identity.platform, set())
    renderer = identity.webgl_renderer or ""

    if not any(renderer.startswith(p) or p in renderer for p in valid_prefixes):
        report.add_warning(f"GPU '{renderer}' unusual for platform {identity.platform}")


def _check_screen_gpu_match(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """4K screens are unusual with integrated graphics."""
    if identity.screen_width >= 3840 and "UHD" in (identity.webgl_renderer or ""):
        report.add_warning("4K screen with integrated GPU — unusual but not impossible")


def _check_timezone_locale_match(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """Timezone must have a matching locale. Asia/Tokyo → ja-JP, etc."""
    tz_locale_map = {
        "Asia/Tokyo": "ja",
        "Asia/Shanghai": "zh",
        "Asia/Seoul": "ko",
        "Europe/Paris": "fr",
        "Europe/Berlin": "de",
        "Europe/Madrid": "es",
        "Europe/Rome": "it",
    }

    for tz_prefix, lang_prefix in tz_locale_map.items():
        if identity.timezone.startswith(tz_prefix.split("/")[0]):
            if tz_prefix in identity.timezone and not identity.locale.startswith(lang_prefix):
                report.add_warning(f"Timezone {identity.timezone} but locale is {identity.locale}")


def _check_hardware_values(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """Hardware values must be in realistic ranges."""
    if identity.hardware_concurrency < 2 or identity.hardware_concurrency > 128:
        report.add_error(f"Hardware concurrency {identity.hardware_concurrency} out of realistic range")

    if identity.device_memory not in (0, 2, 4, 8, 16, 32):
        report.add_warning(f"Device memory {identity.device_memory}GB unusual")

    if identity.screen_width < 320 or identity.screen_width > 7680:
        report.add_error(f"Screen width {identity.screen_width} unrealistic")


def _check_canvas_consistency(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """Canvas hash should be computable from other fields."""
    if identity.canvas_hash and identity.canvas_image_data_url_seed:
        from pachong.anti_detect.fingerprint.canvas import generate_canvas_hash

        expected = generate_canvas_hash(identity)
        if identity.canvas_hash != expected:
            report.add_warning("Canvas hash doesn't match identity fields — will be regenerated")


def _check_tls_consistency(identity: BrowserIdentity, report: ConsistencyReport) -> None:
    """TLS cipher suites should be non-empty and realistic."""
    if not identity.tls_cipher_suites:
        report.add_warning("No TLS cipher suites configured")
    elif len(identity.tls_cipher_suites) < 4:
        report.add_warning(f"Too few cipher suites: {len(identity.tls_cipher_suites)}")


def auto_correct(identity: BrowserIdentity) -> BrowserIdentity:
    """Auto-correct inconsistent identity fields based on platform/UA.
    Regenerates fonts, WebGL renderer, screen resolution to match declared platform.
    Returns a corrected COPY of the identity."""
    import copy
    corrected = copy.deepcopy(identity)
    platform = corrected.platform

    # Fix fonts
    if platform in PLATFORM_FONTS:
        corrected.installed_fonts = sorted(PLATFORM_FONTS[platform])

    # Fix GPU/WebGL
    if platform in PLATFORM_GPU_PREFIXES:
        prefixes = PLATFORM_GPU_PREFIXES[platform]
        if corrected.webgl_renderer:
            found = any(corrected.webgl_renderer.startswith(p) or p in corrected.webgl_renderer for p in prefixes)
            if not found:
                corrected.webgl_renderer = sorted(prefixes)[0] + " Graphics"
                corrected.webgl_vendor = sorted(prefixes)[0]

    # Fix screen resolution for platform
    if platform == "Win32" and corrected.screen_width < 1366:
        corrected.screen_width, corrected.screen_height = 1920, 1080
    elif platform == "MacIntel" and corrected.screen_width < 1440:
        corrected.screen_width, corrected.screen_height = 2560, 1440

    # Fix timezone-locale mismatch
    tz_map = {"Asia/Tokyo": "ja-JP", "Asia/Shanghai": "zh-CN", "Asia/Seoul": "ko-KR",
              "Europe/Paris": "fr-FR", "Europe/Berlin": "de-DE", "America/New_York": "en-US"}
    for tz_prefix, locale in tz_map.items():
        if corrected.timezone.startswith(tz_prefix.split("/")[0]):
            if not corrected.locale.startswith(locale[:2]):
                corrected.locale = locale
                corrected.languages = [locale, locale[:2], "en"]
            break

    return corrected


async def validate_and_correct(identity: BrowserIdentity) -> tuple[BrowserIdentity, ConsistencyReport]:
    """Validate identity and auto-correct if inconsistent (errors OR warnings). Returns (corrected, report)."""
    report = validate_identity(identity)
    if not report.is_valid or report.warnings:
        identity = auto_correct(identity)
        report = validate_identity(identity)
    return identity, report
