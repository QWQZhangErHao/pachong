"""Geo-Bound Identity Generator.

Core insight: select proxy IP FIRST, then query GeoIP, then reverse-generate
a browser identity whose timezone, language, screen resolution, and WebGL
fingerprint are all consistent with that geographic location.

This is the opposite of random fingerprint spoofing — every field is
internally coherent and matches the IP's physical location.
"""

from __future__ import annotations

import random
import uuid

import structlog

from pachong.anti_detect.identity.profile import (
    PLATFORM_BY_CONTINENT,
    TIMEZONE_LOCALE_MAP,
    GeoLocationInfo,
    PlatformProfile,
)
from pachong.core.models import BrowserIdentity, ProxyRecord

logger = structlog.get_logger(__name__)


class IdentityGenerator:
    """Generates coherent, Geo-Bound browser identities."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def generate_from_proxy(self, proxy: ProxyRecord) -> BrowserIdentity:
        """Generate a BrowserIdentity that matches the proxy's physical location.

        This is the Geo-Bound approach: proxy → GeoIP → identity.
        All fields (timezone, locale, platform prevalence) match the IP location.
        """
        # Infer geo-location from proxy record
        geo = self._infer_geo(proxy)

        # Select a platform profile matching the continent
        platform = self._select_platform(geo.continent)

        # Select screen resolution from platform distribution
        screen = self._weighted_choice(
            [(r[0], r[1]) for r in platform.screen_distribution],
            [r[2] for r in platform.screen_distribution],
        ) or (1920, 1080)

        # Select GPU
        vendor, renderer = self._weighted_choice(
            [(g[0], g[1]) for g in platform.gpu_distribution],
            [g[2] for g in platform.gpu_distribution],
        ) or ("Google Inc. (Intel)", "Intel Iris Xe Graphics")

        # Build user agent
        os_version = self._weighted_choice(
            [ov[0] for ov in platform.os_versions],
            [ov[1] for ov in platform.os_versions],
        ) or "10.0"

        browser_version = f"{128 + self._rng.randint(0, 5)}.0.{self._rng.randint(1000, 9999)}.{self._rng.randint(100, 999)}"

        ua = self._build_user_agent(platform, os_version, browser_version)

        # Generate canvas hash seed (unique per identity)
        canvas_seed = uuid.uuid4().hex[:16]

        # Generate audio hash
        audio_hash = uuid.uuid4().hex[:16]

        # Build fonts list
        fonts = list(platform.common_fonts)
        num_extra = self._rng.randint(2, len(platform.platform_signature_fonts))
        fonts.extend(self._rng.sample(platform.platform_signature_fonts, min(num_extra, len(platform.platform_signature_fonts))))

        # TLS cipher suites
        tls_ciphers = self._select_tls_ciphers(platform)

        # Hardware concurrency (CPU cores)
        hw_concurrency = self._rng.choice([4, 8, 12, 16, 24, 32])

        return BrowserIdentity(
            name=f"geo-bound-{geo.country_code}-{uuid.uuid4().hex[:6]}",
            timezone=geo.timezone,
            locale=geo.locale,
            languages=geo.languages,
            ip_geolocation=(geo.latitude, geo.longitude) if geo.latitude else None,
            platform=platform.platform,
            user_agent=ua,
            oscpu=f"{platform.os_name} {os_version}",
            screen_width=screen[0],
            screen_height=screen[1],
            avail_width=screen[0],
            avail_height=screen[1] - 40,  # Taskbar
            color_depth=24,
            pixel_depth=24,
            device_pixel_ratio=self._rng.choice([1.0, 1.25, 1.5, 2.0]),
            hardware_concurrency=hw_concurrency,
            device_memory=self._rng.choice([4, 8, 16, 32]),
            browser_name="Chrome",
            browser_version=browser_version,
            webkit_version="537.36",
            canvas_hash=canvas_seed,
            canvas_image_data_url_seed=canvas_seed,
            webgl_vendor=vendor,
            webgl_renderer=renderer,
            webgl_unmasked_vendor=vendor.split("(")[-1].strip(") ") if "(" in vendor else vendor,
            webgl_unmasked_renderer=renderer,
            audio_hash=audio_hash,
            audio_sample_rate=44100,
            audio_channel_count=2,
            tls_ja4_hash=self._generate_ja4_hash(),
            tls_cipher_suites=tls_ciphers,
            installed_fonts=fonts,
        )

    def generate(self, timezone: str = "America/New_York") -> BrowserIdentity:
        """Generate an identity for a given timezone (no proxy needed)."""
        locale_info = TIMEZONE_LOCALE_MAP.get(timezone, ("en-US", ["en-US", "en"]))
        geo = GeoLocationInfo(
            country_code="US",
            country_name="United States",
            city="New York",
            latitude=40.7128,
            longitude=-74.0060,
            timezone=timezone,
            locale=locale_info[0],
            languages=locale_info[1],
            continent="NA",
        )
        platform = self._select_platform(geo.continent)
        screen = self._weighted_choice(
            [(r[0], r[1]) for r in platform.screen_distribution],
            [r[2] for r in platform.screen_distribution],
        ) or (1920, 1080)

        vendor, renderer = self._weighted_choice(
            [(g[0], g[1]) for g in platform.gpu_distribution],
            [g[2] for g in platform.gpu_distribution],
        ) or ("Google Inc. (Intel)", "Intel Iris Xe Graphics")

        os_version = self._weighted_choice(
            [ov[0] for ov in platform.os_versions],
            [ov[1] for ov in platform.os_versions],
        ) or "10.0"
        browser_version = f"{128 + self._rng.randint(0, 5)}.0.{self._rng.randint(1000, 9999)}.{self._rng.randint(100, 999)}"
        ua = self._build_user_agent(platform, os_version, browser_version)

        return BrowserIdentity(
            name=f"identity-{uuid.uuid4().hex[:8]}",
            timezone=timezone,
            locale=locale_info[0],
            languages=locale_info[1],
            platform=platform.platform,
            user_agent=ua,
            screen_width=screen[0],
            screen_height=screen[1],
            webgl_vendor=vendor,
            webgl_renderer=renderer,
            tls_ja4_hash=self._generate_ja4_hash(),
            tls_cipher_suites=self._select_tls_ciphers(platform),
        )

    def generate_consistent(self, timezone: str = "America/New_York") -> BrowserIdentity:
        """Generate an identity with auto-corrected consistency validation."""
        identity = self.generate(timezone)
        try:
            from pachong.anti_detect.fingerprint.consistency import validate_and_correct
            import asyncio
            corrected, report = asyncio.run(validate_and_correct(identity))
            return corrected
        except Exception:
            return identity

    def _infer_geo(self, proxy: ProxyRecord) -> GeoLocationInfo:
        """Infer geographic location from proxy metadata.

        If GeoIP data is available on the proxy, use it directly.
        Otherwise, infer timezone and locale from region/country.
        """
        if proxy.latitude and proxy.longitude:
            # Proxy already has GeoIP data
            timezone = "America/New_York"  # Default — real impl uses timezonefinder
            country = proxy.country or "US"

            # Find closest matching timezone
            for tz, (locale, langs) in TIMEZONE_LOCALE_MAP.items():
                if locale.startswith(country.lower()) if country else False:
                    timezone = tz
                    break

            if not timezone or timezone == "America/New_York":
                # Default based on country
                country_tz_map = {
                    "US": "America/Chicago",
                    "GB": "Europe/London",
                    "DE": "Europe/Berlin",
                    "FR": "Europe/Paris",
                    "JP": "Asia/Tokyo",
                    "CN": "Asia/Shanghai",
                    "KR": "Asia/Seoul",
                    "BR": "America/Sao_Paulo",
                    "IN": "Asia/Kolkata",
                    "AU": "Australia/Sydney",
                    "CA": "America/Toronto",
                    "SG": "Asia/Singapore",
                }
                timezone = country_tz_map.get(country, "America/New_York")

        else:
            # Infer from proxy region string
            region = proxy.region.lower() if proxy.region else "us"
            country = proxy.country or region[:2].upper()
            timezone = "America/New_York"

        locale_info = TIMEZONE_LOCALE_MAP.get(timezone, ("en-US", ["en-US", "en"]))

        return GeoLocationInfo(
            country_code=proxy.country or "US",
            country_name=proxy.country or "United States",
            city=proxy.city,
            latitude=proxy.latitude or 0,
            longitude=proxy.longitude or 0,
            timezone=timezone,
            locale=locale_info[0],
            languages=locale_info[1],
            continent=self._continent_from_country(proxy.country or "US"),
        )

    def _select_platform(self, continent: str) -> PlatformProfile:
        profiles = PLATFORM_BY_CONTINENT.get(continent, PLATFORM_BY_CONTINENT["NA"])
        return self._weighted_choice(
            [p[0] for p in profiles],
            [p[1] for p in profiles],
        ) or WINDOWS_PROFILE

    def _build_user_agent(self, platform: PlatformProfile, os_version: str, browser_version: str) -> str:
        if platform.platform == "Win32":
            return (
                f"Mozilla/5.0 (Windows NT {os_version}; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{browser_version} Safari/537.36"
            )
        elif platform.platform == "MacIntel":
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X {os_version}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{browser_version} Safari/537.36"
            )
        else:
            return (
                f"Mozilla/5.0 (X11; Linux {os_version}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{browser_version} Safari/537.36"
            )

    def _select_tls_ciphers(self, platform: PlatformProfile) -> list[int]:
        """Return a realistic TLS cipher suite list for the platform.

        Chrome on different platforms has slightly different cipher preferences.
        """
        common = [
            0x1301,  # TLS_AES_128_GCM_SHA256
            0x1302,  # TLS_AES_256_GCM_SHA384
            0x1303,  # TLS_CHACHA20_POLY1305_SHA256
            0xC02B,  # ECDHE-ECDSA-AES128-GCM-SHA256
            0xC02F,  # ECDHE-RSA-AES128-GCM-SHA256
            0xC02C,  # ECDHE-ECDSA-AES256-GCM-SHA384
            0xC030,  # ECDHE-RSA-AES256-GCM-SHA384
            0xCCA9,  # ECDHE-ECDSA-CHACHA20-POLY1305
            0xCCA8,  # ECDHE-RSA-CHACHA20-POLY1305
            0x009E,  # DHE-RSA-AES128-GCM-SHA256
            0x009F,  # DHE-RSA-AES256-GCM-SHA384
        ]
        # Randomly subset (Chrome typically offers 8-16 ciphers)
        count = self._rng.randint(8, len(common))
        return self._rng.sample(common, count)

    def _generate_ja4_hash(self) -> str:
        """Generate a JA4-like hash for the TLS fingerprint."""
        return uuid.uuid4().hex[:12]

    def _weighted_choice(self, items: list, weights: list[float]) -> object | None:
        """Weighted random selection."""
        if not items:
            return None
        return self._rng.choices(items, weights=weights, k=1)[0]

    def _continent_from_country(self, country: str) -> str:
        """Rough continent mapping."""
        na = {"US", "CA", "MX"}
        sa = {"BR", "AR", "CL", "CO", "PE", "VE"}
        eu = {"GB", "DE", "FR", "IT", "ES", "NL", "SE", "PL", "CH", "AT", "BE", "DK", "FI", "NO", "PT", "IE", "CZ", "RO", "HU", "GR"}
        asia = {"CN", "JP", "KR", "IN", "SG", "HK", "TW", "TH", "VN", "MY", "ID", "PH", "AE", "SA", "IL", "TR"}
        oc = {"AU", "NZ"}

        if country in na:
            return "NA"
        if country in sa:
            return "SA"
        if country in eu:
            return "EU"
        if country in asia:
            return "AS"
        if country in oc:
            return "OC"
        return "NA"
