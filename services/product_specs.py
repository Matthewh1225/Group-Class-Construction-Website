"""Product spec helpers, search text and the search hash.

Common specs keys: nominal_size holds trade sizes like 2x4 or 30x80, actual_size_in holds
lumber thickness and width in inches, length_ft is one piece, sheet or roll, and conductors
counts insulated building-cable wires without the bare ground (12/2 has 2).
Purchase sizes live in sale_unit, content_quantity and content_unit, outside specs.
"""
import hashlib
import json
import re
from decimal import Decimal

# Package units, used by quantity conversions and planner search queries.
CONTAINER_SALE_UNITS = ["pail", "can", "tube", "bottle"]
PACKAGE_UNITS = ["box", "bag", "roll", "bundle", "pack", "case", "carton", "spool",
                 "sheet", "panel"] + CONTAINER_SALE_UNITS

# Leave exclusions out of search text so missing items do not attract matches.
# The matcher still receives them in specs.
SPEC_PHRASES = {
    "material": "material {}", "dimensions_text": "dimensions {}",
    "thickness_in": "thickness {} in", "width_ft": "width {} ft", "length_ft": "length {} ft",
    "nominal_size": "nominal size {}", "fastener_size": "size {}", "length_in": "length {} in",
    "awg": "{} AWG", "conductors": "{} conductors", "pairs": "{} twisted pairs",
    "cable_type": "{} cable", "r_value": "R-{}", "fire_rated_type": "{}", "exposure": "{} use",
    "nominal_diameter_in": "{} in nominal diameter", "schedule": "Schedule {}", "amps": "{} A",
    "capacity_btu": "{} BTU", "strength_psi": "{} psi", "fastener_use": "{} fastener", "includes": "includes {}",
    "voltage": "{}", "power_source": "{} powered", "capacity_gal": "{} gallon capacity", "flow_gpm": "{} GPM",
    "flush_gpf": "{} gallons per flush", "connection_size_in": "{} in connection", "port_sizes_in": "{} in ports",
    "coating_use": "for {}", "sheen": "{} finish", "catalog_part_number": "part number {}",
}


# Restriction clauses ("not premixed", "no fire rating", "sold separately") stay out of search text.
RESTRICTION_STARTS = ("not ", "no ", "do not ", "never ")
EXCLUSION_PHRASES = ("sold separately", "not included", "excluded", " excludes ", "separate purchase")


def is_number(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def number_text(value):
    """Plain number text, such as 2.50 -> "2.5". Going through str() keeps 0.1 as 0.1."""
    return format(Decimal(str(value)).normalize(), "f")


def is_restriction(clause):
    lower = clause.lower()
    return lower.startswith(RESTRICTION_STARTS) or any(phrase in lower for phrase in EXCLUSION_PHRASES)


def spec_phrases(specs):
    """Readable phrases for the specs, in a fixed order."""
    phrases = []
    for key, template in SPEC_PHRASES.items():
        value = specs.get(key)
        if value is not None:
            if is_number(value):
                value = number_text(value)
            elif isinstance(value, list) and all(is_number(n) for n in value):
                value = " x ".join(number_text(n) for n in value)
            elif isinstance(value, list):
                value = " ".join(value)
            phrases.append(template.format(value))
    if specs.get("actual_size_in"):
        thickness, width = specs["actual_size_in"]
        phrases.append(f"actual size {thickness} x {width} in")
    return phrases


def search_text_for(product, segments=None):
    """Keyword search also retains exact identifiers and spelling/size aliases."""
    facts = list(segments if segments is not None else embedding_segments_for(product))
    specs = product.get('specs') or {}
    facts.extend(specs.get(key) for key in ('catalog_part_number', 'source_title'))
    text = '. '.join(str(value) for value in facts if value)
    normalized = normalize_search(text)
    return text + '. ' + normalized if normalized != text.casefold() else text


FRACTION_GLYPHS = {'½': '1/2', '¼': '1/4', '¾': '3/4', '⅛': '1/8', '⅜': '3/8', '⅝': '5/8', '⅞': '7/8'}
INCH_FRACTION_BOTTOMS = (2, 4, 8, 16, 32, 64)
UNIT_WORDS = [('inches', 'in'), ('inch', 'in'), ('feet', 'ft'), ('foot', 'ft')]


def is_word_char(char):
    return char.isalnum() or char == '_'


def word_starts_at(text, index):
    return index == 0 or not is_word_char(text[index - 1])


def word_ends_at(text, index):
    return index == len(text) or not is_word_char(text[index])


def skip_digits(text, index):
    """The index just after a run of digits starting at index."""
    while index < len(text) and text[index].isdecimal():
        index += 1
    return index


def skip_spaces(text, index):
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def digit_at(text, index):
    return index < len(text) and text[index].isdecimal()


def replace_each(text, read):
    """Scan left to right. Where read(text, i) returns (end, new_text), use new_text for text[i:end]."""
    pieces = []
    i = 0
    while i < len(text):
        found = read(text, i)
        if found:
            end, new_text = found
            pieces.append(new_text)
            i = end
        else:
            pieces.append(text[i])
            i += 1
    return ''.join(pieces)


def split_glyph_fractions(text):
    """1½ -> 1 1/2 and ½ -> 1/2."""
    for glyph, fraction in FRACTION_GLYPHS.items():
        pieces = []
        for i, char in enumerate(text):
            if char != glyph:
                pieces.append(char)
            elif i > 0 and text[i - 1].isdecimal():
                pieces.append(' ' + fraction)
            else:
                pieces.append(fraction)
        text = ''.join(pieces)
    return text


def read_mixed_number(text, start):
    """1-1/2 or 1 1/2 -> 1.5"""
    if not digit_at(text, start) or not word_starts_at(text, start):
        return None
    whole_end = skip_digits(text, start)
    if text[whole_end:whole_end + 1] not in (' ', '-') or not digit_at(text, whole_end + 1):
        return None
    top_end = skip_digits(text, whole_end + 1)
    if text[top_end:top_end + 1] != '/' or not digit_at(text, top_end + 1):
        return None
    bottom_end = skip_digits(text, top_end + 1)
    if not word_ends_at(text, bottom_end):
        return None
    bottom = int(text[top_end + 1:bottom_end])
    if bottom == 0:
        return bottom_end, text[start:bottom_end]
    whole = int(text[start:whole_end])
    top = int(text[whole_end + 1:top_end])
    return bottom_end, number_text(whole + top / bottom)


def read_inch_fraction(text, start):
    """1/2 -> 0.5. Only inch-style fractions change; 3/2, 1/3 and 1/2/3 stay as written."""
    if not digit_at(text, start) or (start > 0 and (is_word_char(text[start - 1]) or text[start - 1] == '/')):
        return None
    top_end = skip_digits(text, start)
    if text[top_end:top_end + 1] != '/' or not digit_at(text, top_end + 1):
        return None
    bottom_end = skip_digits(text, top_end + 1)
    if bottom_end < len(text) and (is_word_char(text[bottom_end]) or text[bottom_end] == '/'):
        return None
    top = int(text[start:top_end])
    bottom = int(text[top_end + 1:bottom_end])
    if bottom in INCH_FRACTION_BOTTOMS and top < bottom:
        return bottom_end, number_text(top / bottom)
    return bottom_end, text[start:bottom_end]


def read_tire_size(text, start):
    """225/45 zr 17 -> 225/45r17"""
    size = text[start:start + 6]
    if len(size) < 6 or not (size[:3].isdecimal() and size[3] == '/' and size[4:].isdecimal()):
        return None
    i = skip_spaces(text, start + 6)
    if text[i:i + 1] == 'z':
        i += 1
    if text[i:i + 1] != 'r':
        return None
    i = skip_spaces(text, i + 1)
    rim = text[i:i + 2]
    if len(rim) < 2 or not rim.isdecimal():
        return None
    return i + 2, size + 'r' + rim


def read_number_sign(text, start):
    """Drop "#" or "no." before a number: #8 and no. 8 -> 8."""
    if text[start] == '#' and digit_at(text, start + 1):
        return start + 1, ''
    if text.startswith('no', start) and word_starts_at(text, start):
        i = start + 2
        if text[i:i + 1] == '.':
            i += 1
        i = skip_spaces(text, i)
        if digit_at(text, i):
            return i, ''
    return None


def read_times_sign(text, start):
    """2 x 4 -> 2x4"""
    if start == 0 or not text[start - 1].isdecimal():
        return None
    i = skip_spaces(text, start)
    if text[i:i + 1] != 'x':
        return None
    i = skip_spaces(text, i + 1)
    if not digit_at(text, i):
        return None
    return i, 'x'


def read_inch_mark(text, start):
    """2" -> 2 in"""
    if start > 0 and text[start - 1].isdecimal() and text[start] in '"″':
        return start + 1, ' in'
    return None


def read_unit_word(text, start):
    """inches/inch -> in and feet/foot -> ft, as whole words."""
    if not word_starts_at(text, start):
        return None
    for word, short in UNIT_WORDS:
        end = start + len(word)
        if text.startswith(word, start) and word_ends_at(text, end):
            return end, short
    return None


def normalize_search(text):
    """Normalize equivalent measurements without discarding fractional values.

    The site's SQL search and the stored search_text both use this, so any change here
    needs python -m services.product_index to rewrite search_text.
    """
    text = str(text or '').casefold().replace('×', 'x').replace('–', '-').replace('−', '-')
    text = split_glyph_fractions(text)
    for read in (read_mixed_number, read_inch_fraction, read_tire_size, read_number_sign,
                 read_times_sign, read_inch_mark, read_unit_word):
        text = replace_each(text, read)
    return ' '.join(text.split())


def embedding_segments_for(product):
    """Concise, positive buying facts; no identifiers, JSON, or supplier boilerplate."""
    specs = product.get("specs") or {}
    name = product.get('product_name') or product.get('name')
    vector_specs = {key: value for key, value in specs.items() if key != 'catalog_part_number'}
    # Names keep the ZR speed rating; use the radial size already in specs so it shows up once.
    nominal = specs.get('nominal_size', '')
    if product.get('subcategory') == 'Tires' and re.fullmatch(r'\d{3}/\d{2}R\d{2}', nominal, re.I):
        name = re.sub(r'\d{3}/\d{2}\s*Z?R\s*\d{2}', nominal, name, flags=re.I)
        if specs.get('dimensions_text', '') in nominal:
            vector_specs.pop('dimensions_text', None)
    segments = [name]
    segments.extend(spec_phrases(vector_specs))
    segments.extend(specs.get(key) for key in ('fitment', 'assembly_contents'))
    for field in ('details', 'description', 'keywords', 'subcategory'):
        for clause in re.split(r';|[\n|]|\s·\s|(?<!\d)\.\s+', product.get(field) or ''):
            if re.search(r'https?://|catalog reference|demo|fictional|listed part number|vehicle compatibility unspecified|confirm .*before|^part\s', clause, re.I):
                continue
            if not is_restriction(clause.strip()):
                segments.append(clause)
    if specs.get("thickness_nominal"):
        segments.append("nominal thickness")
    if product.get("content_quantity") is not None and product.get("content_unit"):
        segments.append(f"{number_text(product['content_quantity'])} {product['content_unit']} per {product['sale_unit']}")
    elif (product.get("itemQty") or 1) > 1:
        segments.append(f"{product['itemQty']} pieces per {product['sale_unit']}")
    result, seen, tokens_seen = [], [], set()
    part = specs.get('catalog_part_number')
    for segment in segments:
        if not segment: continue
        segment = str(segment).strip(' .;,')
        if part:
            segment = re.sub(r'(?<!\w)' + re.escape(part) + r'(?!\w)', '', segment, flags=re.I).strip()
        normalized = normalize_search(segment)
        normalized = re.sub(r'\b\d+\.\d+\b', lambda m: number_text(m[0]), normalized)
        tokens = set(re.findall(r'[\w]+(?:[./-][\w]+)*', normalized)) - {
            'material', 'dimensions', 'dimension', 'thickness', 'thick', 'length', 'width', 'size', 'nominal', 'use'}
        if normalized and tokens and not tokens.issubset(tokens_seen) and not any(
                normalized == old or (' ' + normalized + ' ') in (' ' + old + ' ') for old in seen):
            result.append(segment); seen.append(normalized); tokens_seen.update(tokens)
    return result


def text_hash(product, segments=None):
    """Fingerprint the stored facts used by both search indexes."""
    if segments is None:
        segments = embedding_segments_for(product)
    return hashlib.sha256(json.dumps(segments, ensure_ascii=False).encode("utf-8")).hexdigest()


def product_from_row(row):
    """Convert a database row to a product dictionary, decoding its JSON specs."""
    product = dict(row)
    specs = product.get("specs")
    if isinstance(specs, (str, bytes)):
        specs = json.loads(specs)
    product["specs"] = specs or {}
    return product
