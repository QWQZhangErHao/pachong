"""Canvas fingerprint generation.

Canvas fingerprinting works by rendering text + emoji to a hidden canvas
and hashing the pixel data. Different OS/GPU/driver combos produce different
results. We generate a consistent hash for each identity and provide the
JavaScript to reproduce it.

Key insight: we don't need to ACTUALLY render the canvas. We just need to
produce a hash that LOOKS like a real canvas fingerprint. Sites compare
hashes, not pixel data.
"""

from __future__ import annotations

import hashlib
import uuid

from pachong.core.models import BrowserIdentity


def generate_canvas_hash(identity: BrowserIdentity) -> str:
    """Generate a deterministic canvas fingerprint hash.

    The hash depends on:
    - GPU vendor + renderer (different AA on different GPUs)
    - OS platform (different font rendering)
    - Browser version (different text rendering engine)
    """
    seed = (
        f"{identity.platform}:"
        f"{identity.webgl_vendor}:"
        f"{identity.webgl_renderer}:"
        f"{identity.browser_version}:"
        f"{identity.canvas_image_data_url_seed}"
    )
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def generate_canvas_inject_script(identity: BrowserIdentity) -> str:
    """Generate JavaScript that overrides canvas toDataURL() to return
    the expected fingerprint hash.

    This intercepts the canvas API and returns a consistent fingerprint
    without actually needing to render anything.
    """
    expected_hash = identity.canvas_hash or generate_canvas_hash(identity)

    return f"""
(function() {{
    const EXPECTED_HASH = '{expected_hash}';
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    let fingerprinted = false;

    HTMLCanvasElement.prototype.toDataURL = function() {{
        if (!fingerprinted && this.width > 100 && this.height > 20) {{
            // This looks like a fingerprinting attempt
            fingerprinted = true;
            // Return a data URL with the expected hash embedded
            return 'data:image/png;base64,' + btoa(EXPECTED_HASH);
        }}
        return originalToDataURL.apply(this, arguments);
    }};

    // Also patch getImageData for extra consistency
    CanvasRenderingContext2D.prototype.getImageData = function() {{
        const result = originalGetImageData.apply(this, arguments);
        if (!fingerprinted && this.canvas.width > 100 && this.canvas.height > 20) {{
            fingerprinted = true;
            // Subtly modify pixel data to match expected hash
            const data = result.data;
            for (let i = 0; i < Math.min(64, data.length); i++) {{
                data[i] = EXPECTED_HASH.charCodeAt(i % 32) ^ (i & 0xFF);
            }}
        }}
        return result;
    }};
}})();
"""


def validate_canvas_hash(identity: BrowserIdentity) -> bool:
    """Verify that the stored canvas_hash matches the identity's other fields."""
    expected = generate_canvas_hash(identity)
    if not identity.canvas_hash:
        return True  # Will be set on first use
    return identity.canvas_hash == expected
