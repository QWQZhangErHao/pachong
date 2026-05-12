"""JA3/JA4 TLS fingerprint management.

TLS fingerprinting identifies clients by their TLS ClientHello:
- Cipher suites offered
- TLS extensions
- Elliptic curves
- Signature algorithms

JA3 and JA4 are the two main fingerprint formats. We generate consistent
fingerprints that match the declared browser identity.
"""

from __future__ import annotations

import hashlib

from pachong.core.models import BrowserIdentity


# Chrome 130 cipher suites in preference order (realistic)
CHROME_CIPHERS = [
    0x1301,  # TLS_AES_128_GCM_SHA256
    0x1302,  # TLS_AES_256_GCM_SHA384
    0x1303,  # TLS_CHACHA20_POLY1305_SHA256
    0xC02B,  # ECDHE-ECDSA-AES128-GCM-SHA256
    0xC02F,  # ECDHE-RSA-AES128-GCM-SHA256
    0xCCA9,  # ECDHE-ECDSA-CHACHA20-POLY1305
    0xCCA8,  # ECDHE-RSA-CHACHA20-POLY1305
    0xC02C,  # ECDHE-ECDSA-AES256-GCM-SHA384
    0xC030,  # ECDHE-RSA-AES256-GCM-SHA384
    0x009E,  # DHE-RSA-AES128-GCM-SHA256
    0x009F,  # DHE-RSA-AES256-GCM-SHA384
]

# Chrome TLS extensions
CHROME_EXTENSIONS = [
    0,     # server_name (SNI)
    5,     # status_request
    10,    # supported_groups
    11,    # ec_point_formats
    13,    # signature_algorithms
    16,    # application_layer_protocol_negotiation (ALPN)
    17,    # status_request_v2
    18,    # signed_certificate_timestamp
    21,    # padding
    23,    # extended_master_secret
    27,    # compress_certificate
    28,    # record_size_limit
    35,    # session_ticket
    41,    # pre_shared_key
    43,    # supported_versions
    45,    # psk_key_exchange_modes
    51,    # key_share
    57,    # application_settings (GREASE)
    17513, # encrypted_client_hello (ECH) / GREASE
]

# Elliptic curves for supported_groups extension
CHROME_ELLIPTIC_CURVES = [
    0x001D,  # x25519
    0x0017,  # secp256r1
    0x0018,  # secp384r1
    0x0100,  # GREASE
]


def compute_ja3_hash(identity: BrowserIdentity) -> str:
    """Compute a JA3 fingerprint hash for the identity.

    JA3 = MD5(TLSVersion,Ciphers,Extensions,EllipticCurves,ECPointFormats)

    Returns a 32-char hex string that looks like a real JA3 fingerprint.
    """
    # Build the JA3 string components
    tls_version = "771"  # TLS 1.2 (771), TLS 1.3 (772)
    ciphers = identity.tls_cipher_suites or CHROME_CIPHERS
    extensions = CHROME_EXTENSIONS
    curves = CHROME_ELLIPTIC_CURVES
    ec_formats = [0]  # uncompressed

    ciphers_str = "-".join(str(c) for c in ciphers[:12])
    extensions_str = "-".join(str(e) for e in extensions)
    curves_str = "-".join(str(c) for c in curves)
    ec_str = "-".join(str(f) for f in ec_formats)

    ja3_string = f"{tls_version},{ciphers_str},{extensions_str},{curves_str},{ec_str}"
    return hashlib.md5(ja3_string.encode()).hexdigest()


def compute_ja4_hash(identity: BrowserIdentity) -> str:
    """Compute a JA4 fingerprint hash.

    JA4 = SHA256(Protocol,TLSVersion,SNI,ALPN,Ciphers,Extensions)

    JA4 is more modern and handles TLS 1.3 + ECH correctly.
    """
    protocol = "t"  # TCP
    tls_version = "13"  # TLS 1.3
    sni = "d"  # domain-level SNI (not IP)
    alpn = "h2" if identity.http2_settings else "h1"

    ciphers = identity.tls_cipher_suites or CHROME_CIPHERS
    # Sort and take top 12
    sorted_ciphers = sorted(ciphers[:12])
    ciphers_hash = format(sorted_ciphers[0] ^ sorted_ciphers[-1], "04x") if sorted_ciphers else "0000"

    extensions = CHROME_EXTENSIONS
    ext_hash = format(sum(extensions[:8]) & 0xFFFF, "04x")

    ja4_string = f"{protocol}{tls_version}{sni}{alpn}_{ciphers_hash}_{ext_hash}"
    return hashlib.sha256(ja4_string.encode()).hexdigest()[:12]


def build_tls_config(identity: BrowserIdentity) -> dict:
    """Build a complete TLS configuration for use in network sessions."""
    return {
        "ja3_hash": identity.tls_ja3_hash or compute_ja3_hash(identity),
        "ja4_hash": identity.tls_ja4_hash or compute_ja4_hash(identity),
        "cipher_suites": identity.tls_cipher_suites or CHROME_CIPHERS,
        "extensions": CHROME_EXTENSIONS,
        "elliptic_curves": CHROME_ELLIPTIC_CURVES,
        "alpn_protocols": ["h2", "http/1.1"],
        "tls_min_version": 1.2,  # Chrome 100+ minimum
        "tls_max_version": 1.3,
        "signature_algorithms": [
            0x0804,  # rsa_pss_rsae_sha256
            0x0401,  # rsa_pkcs1_sha256
            0x0805,  # rsa_pss_rsae_sha384
            0x0501,  # rsa_pkcs1_sha384
            0x0806,  # rsa_pss_rsae_sha512
            0x0601,  # rsa_pkcs1_sha512
            0x0201,  # rsa_pkcs1_sha1
            0x0403,  # ecdsa_secp256r1_sha256
            0x0503,  # ecdsa_secp384r1_sha384
            0x0603,  # ecdsa_secp521r1_sha512
        ],
    }
