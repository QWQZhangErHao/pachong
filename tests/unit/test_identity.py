"""Unit tests for identity generation and fingerprint consistency."""

from __future__ import annotations

from pachong.anti_detect.fingerprint.consistency import validate_identity
from pachong.anti_detect.identity.generator import IdentityGenerator


class TestIdentityGenerator:
    def setup_method(self):
        self.gen = IdentityGenerator(seed=42)

    def test_generate_tokyo_identity(self):
        identity = self.gen.generate("Asia/Tokyo")
        assert identity.timezone == "Asia/Tokyo"
        assert identity.locale == "ja-JP"
        assert "ja-JP" in identity.languages

    def test_generate_european_identity(self):
        identity = self.gen.generate("Europe/Berlin")
        assert identity.locale == "de-DE"

    def test_generated_identity_has_user_agent(self):
        identity = self.gen.generate("America/New_York")
        assert len(identity.user_agent) > 20
        assert "Chrome" in identity.user_agent or "Firefox" in identity.user_agent

    def test_generated_identity_has_webgl(self):
        identity = self.gen.generate("America/New_York")
        assert identity.webgl_vendor
        assert identity.webgl_renderer

    def test_deterministic_with_seed(self):
        gen1 = IdentityGenerator(seed=42)
        gen2 = IdentityGenerator(seed=42)
        id1 = gen1.generate("America/New_York")
        id2 = gen2.generate("America/New_York")
        assert id1.platform == id2.platform
        assert id1.webgl_renderer == id2.webgl_renderer

    def test_different_timezones_produce_different_locales(self):
        tokyo = self.gen.generate("Asia/Tokyo")
        paris = self.gen.generate("Europe/Paris")
        assert tokyo.locale != paris.locale


class TestConsistencyValidation:
    def test_valid_identity_passes(self):
        gen = IdentityGenerator(seed=1)
        identity = gen.generate("America/New_York")
        report = validate_identity(identity)
        assert report.is_valid

    def test_bad_ua_detected(self):
        gen = IdentityGenerator(seed=1)
        identity = gen.generate("America/New_York")
        identity.user_agent = "Linux user agent on Windows"
        report = validate_identity(identity)
        assert not report.is_valid or len(report.warnings) > 0

    def test_impossible_hardware_detected(self):
        gen = IdentityGenerator(seed=1)
        identity = gen.generate("America/New_York")
        identity.hardware_concurrency = 999
        report = validate_identity(identity)
        assert not report.is_valid
