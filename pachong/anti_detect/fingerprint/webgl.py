"""WebGL fingerprint generation.

WebGL exposes GPU vendor, renderer, and dozens of parameter values.
The combination is highly identifying. We must ensure the WebGL fingerprint
is consistent with the declared GPU and platform.
"""

from __future__ import annotations

import hashlib

from pachong.core.models import BrowserIdentity


def generate_webgl_config(identity: BrowserIdentity) -> dict:
    """Generate full WebGL configuration matching the identity's GPU.

    Returns a dict that can be serialized to JSON and injected as an
    init script in Playwright/Nodriver.
    """
    gpu_family = _gpu_family(identity.webgl_renderer)

    config = {
        "vendor": identity.webgl_vendor,
        "renderer": identity.webgl_renderer,
        "unmaskedVendor": identity.webgl_unmasked_vendor,
        "unmaskedRenderer": identity.webgl_unmasked_renderer,
        "version": _get_webgl_version(gpu_family),
        "shadingLanguageVersion": _get_shading_lang_version(gpu_family),
        "extensions": _get_extensions(gpu_family, identity.platform),
        "parameters": _get_parameters(gpu_family, identity.platform),
    }
    return config


def generate_webgl_hash(identity: BrowserIdentity) -> str:
    """Generate a WebGL fingerprint hash from the identity's GPU info."""
    seed = f"{identity.webgl_vendor}:{identity.webgl_renderer}:{identity.platform}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def generate_webgl_inject_script(identity: BrowserIdentity) -> str:
    """Generate JavaScript that overrides WebGL getParameter and getExtension
    to return values consistent with the declared identity.
    """
    config = generate_webgl_config(identity)

    param_overrides = ",".join(
        f"{k}: {v}" if not isinstance(v, str) else f"{k}: '{v}'"
        for k, v in config["parameters"].items()
    )

    ext_list = str(config["extensions"])

    return f"""
(function() {{
    const PARAMS = {{{param_overrides}}};
    const EXTS = {ext_list};

    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    const origGetExt = WebGLRenderingContext.prototype.getExtension;
    const origGetSupportedExt = WebGLRenderingContext.prototype.getSupportedExtensions;

    WebGLRenderingContext.prototype.getParameter = function(p) {{
        if (p === 37445) return '{config["unmaskedVendor"]}';
        if (p === 37446) return '{config["unmaskedRenderer"]}';
        if (p === 7936) return '{config["vendor"]}';
        if (p === 7937) return '{config["renderer"]}';
        if (p === 7938) return '{config["version"]}';
        if (p === 35724) return '{config["shadingLanguageVersion"]}';

        if (PARAMS[p] !== undefined) return PARAMS[p];
        return origGetParam.call(this, p);
    }};

    WebGLRenderingContext.prototype.getSupportedExtensions = function() {{
        return EXTS;
    }};

    WebGLRenderingContext.prototype.getExtension = function(name) {{
        if (EXTS.indexOf(name) >= 0) return origGetExt.call(this, name);
        return null;
    }};
}})();
"""


def _gpu_family(renderer: str) -> str:
    r = renderer.lower()
    if "intel" in r:
        return "intel"
    if "nvidia" in r:
        return "nvidia"
    if "amd" in r or "radeon" in r:
        return "amd"
    if "apple" in r:
        return "apple"
    return "generic"


def _get_webgl_version(gpu: str) -> str:
    versions = {
        "intel": "WebGL 2.0 (OpenGL ES 3.0 Intel)",
        "nvidia": "WebGL 2.0 (OpenGL ES 3.0 NVIDIA)",
        "amd": "WebGL 2.0 (OpenGL ES 3.0 AMD)",
        "apple": "WebGL 2.0 (OpenGL ES 3.0 Apple)",
    }
    return versions.get(gpu, "WebGL 2.0 (OpenGL ES 3.0)")


def _get_shading_lang_version(gpu: str) -> str:
    versions = {
        "intel": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Intel)",
        "nvidia": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 NVIDIA)",
        "amd": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 AMD)",
        "apple": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Apple)",
    }
    return versions.get(gpu, "WebGL GLSL ES 3.00")


def _get_extensions(gpu: str, platform: str) -> list[str]:
    """Return realistic WebGL extensions for the GPU+platform combo."""
    base = [
        "ANGLE_instanced_arrays",
        "EXT_blend_minmax",
        "EXT_color_buffer_half_float",
        "EXT_disjoint_timer_query",
        "EXT_float_blend",
        "EXT_frag_depth",
        "EXT_shader_texture_lod",
        "EXT_texture_compression_bptc",
        "EXT_texture_compression_rgtc",
        "EXT_texture_filter_anisotropic",
        "EXT_sRGB",
        "OES_element_index_uint",
        "OES_fbo_render_mipmap",
        "OES_standard_derivatives",
        "OES_texture_float",
        "OES_texture_float_linear",
        "OES_texture_half_float",
        "OES_texture_half_float_linear",
        "OES_vertex_array_object",
        "WEBGL_color_buffer_float",
        "WEBGL_compressed_texture_s3tc",
        "WEBGL_compressed_texture_s3tc_srgb",
        "WEBGL_debug_renderer_info",
        "WEBGL_debug_shaders",
        "WEBGL_depth_texture",
        "WEBGL_draw_buffers",
        "WEBGL_lose_context",
        "WEBGL_multi_draw",
    ]

    # Platform-specific extensions
    if platform == "Win32":
        base.extend(["WEBGL_compressed_texture_astc", "EXT_color_buffer_float"])
    elif platform == "MacIntel":
        base.append("WEBGL_compressed_texture_astc")
    elif platform == "Linux x86_64":
        base.extend(["EXT_texture_norm16", "EXT_clip_cull_distance"])

    # GPU-specific
    if gpu == "nvidia":
        base.extend(["NV_shader_noperspective_interpolation", "EXT_polygon_offset_clamp"])
    elif gpu == "intel":
        base.append("INTEL_performance_query")
    elif gpu == "amd":
        base.append("EXT_shader_framebuffer_fetch")

    return sorted(base)


def _get_parameters(gpu: str, platform: str) -> dict[str, int]:
    """Return GPU/Platform-specific WebGL parameter values."""
    base = {
        3379: 32768,  # MAX_TEXTURE_SIZE
        3386: 16384,  # MAX_VIEWPORT_DIMS[0]
        3387: 16384,  # MAX_VIEWPORT_DIMS[1]
        3401: 16384,  # MAX_RENDERBUFFER_SIZE
        34930: 16,    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        34931: 16,    # MAX_TEXTURE_IMAGE_UNITS
        35661: 32,    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        34921: 16,    # MAX_VERTEX_ATTRIBS
        35978: 32,    # MAX_VARYING_VECTORS
        36349: 2048,  # MAX_FRAGMENT_UNIFORM_VECTORS
        3382: 1024,   # ALIASED_POINT_SIZE_RANGE[1]
        33902: 16,    # ALIASED_LINE_WIDTH_RANGE[1]
        34047: 32,    # MAX_SAMPLES
    }

    if gpu == "nvidia":
        base[3379] = 32768
        base[35661] = 192
    elif gpu == "intel" or gpu == "apple":
        base[3379] = 16384
        base[35661] = 96
    elif gpu == "amd":
        base[3379] = 32768
        base[35661] = 192

    return base
