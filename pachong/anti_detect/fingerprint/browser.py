"""Browser navigator/screen/language/plugins fingerprint.

Generates the JavaScript-level fingerprint that sites read via:
- navigator.userAgent, platform, language, languages
- navigator.hardwareConcurrency, deviceMemory
- navigator.plugins, mimeTypes
- screen.width, height, colorDepth, pixelDepth
- Intl.DateTimeFormat().resolvedOptions().timeZone
"""

from __future__ import annotations

import random

from pachong.core.models import BrowserIdentity


def generate_plugins(platform: str) -> list[dict[str, str]]:
    """Generate a realistic plugin list for the given platform.

    Real browsers have 3-7 plugins: PDF Viewer, Chrome PDF Viewer,
    Chrome PDF Plugin, Native Client (sometimes).
    """
    plugins = [
        {"name": "Chrome PDF Plugin", "filename": "internal-pdf-viewer", "description": "Portable Document Format"},
        {"name": "Chrome PDF Viewer", "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai", "description": ""},
        {"name": "Native Client", "filename": "internal-nacl-plugin", "description": ""},
    ]
    return plugins


def generate_mime_types() -> list[dict[str, str]]:
    """MIME types registered by the browser."""
    return [
        {"type": "application/pdf", "suffixes": "pdf"},
        {"type": "text/pdf", "suffixes": "pdf"},
    ]


def get_accept_language_header(locale: str, languages: list[str]) -> str:
    """Build the Accept-Language header matching the identity.

    Chrome format: "en-US,en;q=0.9,fr;q=0.8"
    """
    parts = [locale]
    quality = 0.9
    for lang in languages:
        if lang != locale:
            parts.append(f"{lang};q={quality}")
            quality -= 0.1
            if quality < 0.5:
                break
    return ",".join(parts)


def get_sec_ch_ua_headers(identity: BrowserIdentity) -> dict[str, str]:
    """Build Sec-Ch-UA headers (User-Agent Client Hints).

    Chrome 100+ sends these headers on every request.
    """
    brand = identity.browser_name
    version = identity.browser_version.split(".")[0]

    return {
        "Sec-Ch-Ua": f'"Chromium";v="{version}", "Not;A=Brand";v="99", "{brand}";v="{version}"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": f'"{_platform_string(identity.platform)}"',
        "Sec-Ch-Ua-Arch": '"x86"',
        "Sec-Ch-Ua-Bitness": '"64"',
        "Sec-Ch-Ua-Full-Version-List": f'"Chromium";v="{identity.browser_version}", "Not;A=Brand";v="99.0.0.0", "{brand}";v="{identity.browser_version}"',
    }


def _platform_string(platform: str) -> str:
    """Convert internal platform to Sec-CH-UA-Platform value."""
    mapping = {
        "Win32": "Windows",
        "MacIntel": "macOS",
        "Linux x86_64": "Linux",
    }
    return mapping.get(platform, "Windows")


def generate_webgl_parameters(identity: BrowserIdentity) -> dict:
    """Generate WebGL context parameters matching the GPU.

    These are the GL parameters that sites read via getParameter().
    Each GPU/driver combination produces a unique set of values.
    """
    gpu_family = _detect_gpu_family(identity.webgl_renderer)

    params = {
        "MAX_TEXTURE_SIZE": _pick(gpu_family, "max_texture_size", [8192, 16384, 32768]),
        "MAX_VIEWPORT_DIMS": _pick(gpu_family, "max_viewport_dims", [16384, 32768]),
        "MAX_RENDERBUFFER_SIZE": _pick(gpu_family, "max_renderbuffer_size", [8192, 16384]),
        "MAX_VERTEX_TEXTURE_IMAGE_UNITS": _pick(gpu_family, "max_vertex_tex_units", [16, 32]),
        "MAX_TEXTURE_IMAGE_UNITS": _pick(gpu_family, "max_tex_units", [16, 32]),
        "MAX_COMBINED_TEXTURE_IMAGE_UNITS": _pick(gpu_family, "max_combined_tex", [80, 96, 192]),
        "MAX_VERTEX_ATTRIBS": _pick(gpu_family, "vertex_attribs", [16, 32]),
        "MAX_VARYING_VECTORS": _pick(gpu_family, "varying_vectors", [30, 31, 32]),
        "MAX_FRAGMENT_UNIFORM_VECTORS": _pick(gpu_family, "fragment_uniform", [1024, 2048]),
        "ALIASED_POINT_SIZE_RANGE": [1, _pick(gpu_family, "point_size", [256, 1024])],
        "ALIASED_LINE_WIDTH_RANGE": [1, _pick(gpu_family, "line_width", [8, 16, 32])],
    }
    return params


def _detect_gpu_family(renderer: str) -> str:
    if "Intel" in renderer:
        return "intel"
    elif "NVIDIA" in renderer:
        return "nvidia"
    elif "AMD" in renderer or "Radeon" in renderer:
        return "amd"
    elif "Apple" in renderer:
        return "apple"
    return "generic"


def _pick(gpu_family: str, param: str, options: list[int]) -> int:
    """Deterministic-ish pick based on GPU family + param."""
    seed = hash(f"{gpu_family}:{param}") % len(options)
    return options[abs(seed)]
