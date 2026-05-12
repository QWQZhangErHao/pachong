"""AudioContext fingerprint generation.

Audio fingerprinting creates an oscillator, processes it through the
audio stack, and hashes the result. Different hardware (sound card,
audio drivers) produce slightly different output due to floating-point
precision and driver-specific processing.
"""

from __future__ import annotations

import hashlib

from pachong.core.models import BrowserIdentity


def generate_audio_fingerprint(identity: BrowserIdentity) -> dict:
    """Generate a realistic AudioContext fingerprint configuration.

    The audio fingerprint depends on:
    - Sample rate (hardware-specific)
    - Channel count
    - Platform audio stack (WASAPI on Windows, CoreAudio on Mac, ALSA/PulseAudio on Linux)
    """
    platform = identity.platform

    config = {
        "sampleRate": identity.audio_sample_rate,
        "channelCount": identity.audio_channel_count,
        "channelCountMode": "explicit",
        "channelInterpretation": "speakers",
        "numberOfInputs": 0 if platform == "Linux x86_64" else 1,
        "numberOfOutputs": 1,
        "baseLatency": _get_base_latency(platform),
        "outputLatency": _get_output_latency(platform),
    }
    return config


def generate_audio_hash(identity: BrowserIdentity) -> str:
    """Generate a deterministic audio fingerprint hash."""
    seed = (
        f"{identity.platform}:"
        f"{identity.audio_sample_rate}:"
        f"{identity.audio_channel_count}:"
        f"{identity.browser_version}"
    )
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def generate_audio_inject_script(identity: BrowserIdentity) -> str:
    """Generate JavaScript that overrides AudioContext to return consistent values."""
    config = generate_audio_fingerprint(identity)
    expected_hash = identity.audio_hash or generate_audio_hash(identity)

    return f"""
(function() {{
    const SAMPLE_RATE = {config['sampleRate']};
    const EXPECTED_HASH = '{expected_hash}';
    const BASE_LATENCY = {config['baseLatency']};
    const OUTPUT_LATENCY = {config['outputLatency']};

    const OrigAudioContext = window.AudioContext || window.webkitAudioContext;
    const origCreateOscillator = AudioContext.prototype.createOscillator;
    const origCreateAnalyser = AudioContext.prototype.createAnalyser;
    const origCreateDynamicsCompressor = AudioContext.prototype.createDynamicsCompressor;

    // Override sample rate
    Object.defineProperty(AudioContext.prototype, 'sampleRate', {{
        get: function() {{ return SAMPLE_RATE; }}
    }});

    // Override base latency
    Object.defineProperty(AudioContext.prototype, 'baseLatency', {{
        get: function() {{ return BASE_LATENCY; }}
    }});

    // Override output latency
    Object.defineProperty(AudioContext.prototype, 'outputLatency', {{
        get: function() {{ return OUTPUT_LATENCY; }}
    }});

    // Patch createDynamicsCompressor to alter its effect
    const originalDcGetReduction = DynamicsCompressorNode.prototype.getReduction;
    if (!originalDcGetReduction) {{
        DynamicsCompressorNode.prototype.getReduction = function() {{
            return 0;
        }};
    }}
}})();
"""


def _get_base_latency(platform: str) -> float:
    """Approximate base latency by platform (seconds)."""
    if platform == "Win32":
        return 0.01  # WASAPI is fast
    elif platform == "MacIntel":
        return 0.005  # CoreAudio is very fast
    elif platform == "Linux x86_64":
        return 0.015  # ALSA/PulseAudio varies
    return 0.01


def _get_output_latency(platform: str) -> float:
    if platform == "Win32":
        return 0.02
    elif platform == "MacIntel":
        return 0.01
    elif platform == "Linux x86_64":
        return 0.03
    return 0.02
