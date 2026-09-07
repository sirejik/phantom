"""RFC 8785 JSON Canonicalization Scheme.

PHANTOM hashes semantic artifacts (wire schema projection, CommissioningBundle,
component configuration, build identity) and requires Quest and EV3 to derive the
same bytes independently.  ``json.dumps(sort_keys=True)`` is not JCS: it orders
keys by Unicode code point instead of UTF-16 code unit and serialises numbers
with Python rules instead of ECMAScript ``Number::toString``.  Both differences
are invisible for ASCII-keyed integer documents and become hash divergence as
soon as a measured floating point value or a non-BMP key appears.

This module is the single canonicalizer for every Python component, including
the Python 3.5 runtime on the pinned ev3dev image, so it deliberately avoids
f-strings, typing syntax and any dependency outside the standard library.
"""

import json
import math

MAX_SAFE_INTEGER = 9007199254740991


class CanonicalizationError(ValueError):
    """The value cannot be represented in the JCS-supported I-JSON domain."""


def _sort_key(name):
    # RFC 8785 orders members by their UTF-16 code units.  Comparing the
    # big-endian UTF-16 encoding compares exactly those code units, which keeps
    # surrogate pairs below U+E000..U+FFFF the way ECMAScript sorts them.
    return name.encode("utf-16-be")


def _digits_and_exponent(value):
    """Return ``(s, n)`` with ``0.s * 10**n == value`` and ``s`` minimal.

    ``repr`` already yields the shortest round-tripping decimal digits, so only
    the ECMAScript framing has to be reconstructed from it.
    """
    text = repr(float(value))
    if text[0] == "-":
        text = text[1:]
    if "e" in text:
        mantissa, unused, exponent_text = text.partition("e")
        exponent = int(exponent_text)
    else:
        mantissa, exponent = text, 0
    integer_part, unused, fraction_part = mantissa.partition(".")
    combined = integer_part + fraction_part
    significant = combined.lstrip("0")
    if not significant:
        return "0", 1
    leading_zeros = len(combined) - len(significant)
    exponent_of_point = len(integer_part) - leading_zeros + exponent
    return significant.rstrip("0") or "0", exponent_of_point


def serialize_number(value):
    """Serialise a JSON number exactly like ECMAScript ``Number::toString``."""
    if isinstance(value, bool):
        raise CanonicalizationError("boolean is not a number")
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError(
                "integer %d is outside the IEEE-754 exact range" % value)
        return str(value)
    if not isinstance(value, float):
        raise CanonicalizationError("unsupported numeric type")
    if math.isnan(value) or math.isinf(value):
        raise CanonicalizationError("NaN and Infinity are not JSON numbers")
    if value == 0.0:
        # RFC 8785 folds negative zero onto "0".
        return "0"
    sign = "-" if value < 0 else ""
    digits, point = _digits_and_exponent(abs(value))
    count = len(digits)
    if count <= point <= 21:
        return sign + digits + "0" * (point - count)
    if 0 < point <= 21:
        return sign + digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return sign + "0." + "0" * (-point) + digits
    exponent = point - 1
    exponent_text = ("e+" if exponent >= 0 else "e-") + str(abs(exponent))
    if count == 1:
        return sign + digits + exponent_text
    return sign + digits[0] + "." + digits[1:] + exponent_text


def serialize_string(value):
    """Serialise a JSON string with the minimal ECMAScript escape set."""
    # json.dumps escapes exactly `"`, `\` and C0 controls, preferring the short
    # \b \t \n \f \r forms, which is the RFC 8785 escape table.
    return json.dumps(value, ensure_ascii=False)


def _write(value, out):
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(serialize_string(value))
    elif isinstance(value, (int, float)):
        out.append(serialize_number(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for name in value:
            if not isinstance(name, str):
                raise CanonicalizationError("object member names must be strings")
        out.append("{")
        for index, name in enumerate(sorted(value, key=_sort_key)):
            if index:
                out.append(",")
            out.append(serialize_string(name))
            out.append(":")
            _write(value[name], out)
        out.append("}")
    else:
        raise CanonicalizationError("unsupported JSON type: " + type(value).__name__)


def canonicalize(value):
    """Return the RFC 8785 canonical UTF-8 bytes of an already-parsed document."""
    out = []
    _write(value, out)
    return "".join(out).encode("utf-8")
