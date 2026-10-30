"""
Step 1: build a searchable product catalogue for the support agent.

    data/products_all_en.json   (English products, demo EUR prices, quantity)
  + data/category_paths.json  (full category path of each product)
  -> catalog.db               (SQLite: clean search fields + full-text index)

Everything here is plain code -- no LLM. Every extracted value comes from the
product's own text, so the agent can only ever quote what the shop data says.

Usage (from the support_agent folder):
    .\\run.ps1 build
"""
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
PRODUCTS = HERE / "data" / "products_all_en.json"
CATEGORY_PATHS = HERE / "data" / "category_paths.json"
DB = HERE / "catalog.db"


# Lamp sockets / bases seen in this catalogue. A whitelist, so model codes are never mistaken for sockets.
SOCKETS = ["E10", "E14", "E27", "E40", "B15d", "B22", "BA15s", "BA15d", "BAY15d", "BAU15s", "BA9s",
           "G4", "GY6.35", "G5.3", "GU5.3", "GX5.3", "GU4", "G9", "GU10", "GZ10", "G53", "GX53", "GX70",
           "G5", "G13", "G23", "G24d-1", "G24d-2", "G24d-3", "G24q-1", "G24q-2", "G24q-3", "G24d", "G24q",
           "GX24q-2", "GX24q-3", "GX24q-4", "GX24q", "2G7", "2G11", "2GX13", "G10q", "GR8", "GR10q",
           "R7s", "RX7s", "Fc2", "G12", "G8.5", "GX9.5", "G6.35", "GY9.5", "P28s", "PGJ19", "PG13", "Fa4",
           "H1", "H3", "H4", "H7", "H11", "HB3", "HB4", "W5W", "T4W"]
SOCKET_ALT = "|".join(sorted(map(re.escape, SOCKETS), key=len, reverse=True))
SOCKET_RE = re.compile(r"(?<![A-Za-z0-9])(" + SOCKET_ALT + r")(?![A-Za-z0-9.])")
CANON_SOCKET = {s.lower(): s for s in SOCKETS}

FINISH_COLOURS = ["Matte chrome", "Chrome", "Black", "White", "Bronze", "Copper", "Gold", "Aluminum", "Gray",
                  "Brown", "Beige", "Silver", "Nickel", "Brass", "Red", "Blue", "Green", "Orange", "Yellow",
                  "Pink", "Purple", "Transparent", "Wood", "Multicolored", "Antique bronze", "Matte nickel",
                  "Matte white", "Old gold", "Old silver", "Rusty", "Ivory", "Graphite"]
LIGHT_COLOUR = {"warm": "warm", "neutral": "neutral", "daylight": "daylight", "cold": "cold", "cool": "cold"}


def category_paths() -> dict[str, str]:
    """product_id -> English category path, exported once from the shop's SQL dump
    (see ../export_category_paths.py)."""
    return json.loads(CATEGORY_PATHS.read_text(encoding="utf-8"))


def first(pattern: str, *texts: str, flags=re.I):
    for t in texts:
        m = re.search(pattern, t or "", flags)
        if m:
            return m
    return None


WATT_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*-?\s*(?:W|watts?)\b", re.I)
# "equivalent 92 watt incandescent", "shines like a 40 W bulb", "replaces 75W": not the product's own power
EQUIV_RE = re.compile(r"(?:equivalent|equiv\.|like an?|replaces?|corresponds? to|instead of|analogue? of|comparable to)"
                      r"[^,.;]{0,25}$", re.I)


def own_watts(text: str) -> float | None:
    for m in WATT_RE.finditer(text or ""):
        if not EQUIV_RE.search(text[max(0, m.start() - 40):m.start()]):
            return float(m.group(1).replace(",", "."))
    return None


def extract_power(name: str, sdesc: str, desc: str, params: list[str], is_bulb: bool) -> float | None:
    """Power per lamp/bulb. For BULBS the name is the manufacturer's code ("TL-E 22W/33-640") and the
    most reliable source, then the wattage parameter; shop descriptions have copy-paste slips
    ("Daylightstar 15W" on an 18 W tube). For FIXTURES the description's "max power" wins."""
    param = own_watts(" ".join(params))
    if is_bulb:
        m = re.search(r"(?<![\d.])(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*W\b", name, re.I)   # "GU10i-3x1W" = 3 W in total
        if m:
            return int(m.group(1)) * float(m.group(2).replace(",", "."))
    order = [name, param, sdesc, desc] if is_bulb else [desc, sdesc, name, param]
    for src in order:
        w = src if isinstance(src, float) else own_watts(src)
        if w is not None:
            return w
    return None


def extract(p: dict, path: str) -> dict:
    name, sdesc, desc = p["product_name"], p["product_s_desc"], p["product_desc"]
    params = [p[f"parameter_{i}"] for i in range(1, 9)]
    plain_params = [re.sub(r"^\d+_", "", v).lstrip(";") for v in params]   # "102_E27" -> "E27"
    texts = [desc, sdesc, name, " | ".join(plain_params)]                  # description wins, then name, then params

    sockets = []
    for t in [name, sdesc, desc, " ".join(plain_params)]:
        for s in SOCKET_RE.findall(t):
            s = CANON_SOCKET.get(s.lower(), s)
            if s not in sockets:
                sockets.append(s)

    # power: "4 x 40 W", "1x40W", "Power - 40W", "40W"; first number of lamps from "N x <socket|power>"
    lamps = first(r"(?:number of (?:bulbs|lamps)\s*[-:]\s*)(\d+)", desc, sdesc)
    nx = first(r"\b(\d{1,2})\s*x\s*(?:(?:" + SOCKET_ALT + r")(?![A-Za-z0-9.])|\d+(?:[.,]\d+)?\s*W)", name, sdesc, desc)
    num_lamps = int(lamps.group(1)) if lamps else (int(nx.group(1)) if nx else None)
    power_w = extract_power(name, sdesc, desc, plain_params, is_bulb=path.startswith("Light bulbs"))

    v = first(r"(?<![\d.,])(\d{1,3})\s*V\b", desc, sdesc, name, " ".join(plain_params))
    voltage_v = int(v.group(1)) if v else None

    ip = first(r"\bIP\s?(\d{2})\b", desc, sdesc, name, " ".join(plain_params))
    ip_rating = int(ip.group(1)) if ip else None

    k = first(r"(?<!\d)(\d{4})\s?K\b", desc, sdesc, name)
    colour_temp_k = int(k.group(1)) if k and 1500 <= int(k.group(1)) <= 10000 else None
    lc = first(r"\b(warm|neutral|daylight|cold|cool)\b", " ".join(plain_params), sdesc, name)
    light_colour = LIGHT_COLOUR[lc.group(1).lower()] if lc else None
    if light_colour is None and colour_temp_k:
        light_colour = "warm" if colour_temp_k <= 3500 else "neutral" if colour_temp_k <= 4500 else \
                       "daylight" if colour_temp_k <= 5500 else "cold"

    # finish colour: the description wins ("Color - brown heterogeneous"), then parameter_2 (body colour).
    # parameter_3 is usually the shade/glass colour ("Chrome | White" = chrome frame, white shade).
    m = first(r"\bcolou?r(?!\s*(?:rendering|temperature|of)\b)[:\-\s]*([A-Za-z][A-Za-z -]{2,25}?)\s*(?:[,.;(]|$)",
              desc, sdesc)
    finish = m.group(1).strip().capitalize() if m else None
    if finish and re.fullmatch(r"(warm|neutral|cool|cold|daylight) white", finish, re.I):
        light_colour = light_colour or LIGHT_COLOUR[finish.split()[0].lower()]   # LED light colour, not the body
        finish = None
    if finish and re.match(r"as (in|on) the (picture|photo)", finish, re.I):
        finish = None
    if finish is None and plain_params[1] in FINISH_COLOURS:
        finish = plain_params[1]
    shade = plain_params[2] if plain_params[2] in FINISH_COLOURS + ["Frost", "Crystal"] else None

    if re.search(r"bulbs? (?:are |is )?not included|without bulbs?|sold separately", " ".join([desc, sdesc, name]), re.I):
        bulbs_included = 0
    elif re.search(r"bulbs? (?:are |is )?included|included\s*[-:]?\s*\w*\s*bulbs?|with bulbs?\b", " ".join([desc, sdesc, name]), re.I):
        bulbs_included = 1
    else:
        bulbs_included = None   # unknown -- the agent must not guess

    blob = " ".join([name, sdesc, desc, path] + plain_params).lower()
    return {
        "id": int(p["product_id"]),
        "sku": p["product_sku"],
        "name": name,
        "brand": p["manufacturer"] or params[0] or None,
        "category": path,
        "category_leaf": path.split(" > ")[-1] if path else None,   # "LED strips", not the whole group name
        "group_name": path.split(" > ")[0] if path else None,
        "sockets": ",".join(sockets) or None,
        "num_lamps": num_lamps,
        "power_w": power_w,
        "voltage_v": voltage_v,
        "ip_rating": ip_rating,
        "is_led": int(bool(re.search(r"\bled\b", blob))),
        "dimmable": int("dimm" in blob),
        "light_colour": light_colour,
        "colour_temp_k": colour_temp_k,
        "finish_colour": finish,
        "shade_colour": shade,
        "bulbs_included": bulbs_included,
        "price_eur": float(p["product_price"]),
        "quantity": int(p["quantity"]),
        "short_description": sdesc,
        "description": desc,
        "parameters": " | ".join(v for v in plain_params if v),
    }


def main():
    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    paths = category_paths()
    rows = [extract(p, paths.get(p["product_id"], "")) for p in products]

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    cols = list(rows[0])
    con.execute(f"CREATE TABLE products ({', '.join(c + (' INTEGER PRIMARY KEY' if c == 'id' else '') for c in cols)})")
    con.executemany(f"INSERT INTO products VALUES ({', '.join('?' * len(cols))})", [tuple(r.values()) for r in rows])
    con.execute("CREATE VIRTUAL TABLE products_fts USING fts5(name, category_leaf, category, short_description, "
                "description, parameters, brand, content='products', content_rowid='id', tokenize='porter unicode61')")
    con.execute("INSERT INTO products_fts(rowid, name, category_leaf, category, short_description, description, "
                "parameters, brand) SELECT id, name, category_leaf, category, short_description, description, "
                "parameters, brand FROM products")
    for c in ("sockets", "category", "price_eur", "quantity", "ip_rating", "power_w"):
        con.execute(f"CREATE INDEX idx_{c} ON products({c})")
    con.commit()

    # coverage report: how many products got each field, per main group
    print(f"catalog.db: {len(rows)} products\n")
    groups = Counter(r["group_name"] for r in rows)
    fields = ["sockets", "power_w", "num_lamps", "voltage_v", "ip_rating", "light_colour", "finish_colour", "bulbs_included"]
    print(f"{'group':34}{'count':>6}" + "".join(f"{f:>14}" for f in fields))
    for g, n in groups.most_common():
        rs = [r for r in rows if r["group_name"] == g]
        print(f"{str(g):34}{n:>6}" + "".join(f"{100 * sum(r[f] is not None for r in rs) / n:>13.0f}%" for f in fields))
    print("\nmost common sockets:", Counter(s for r in rows if r["sockets"] for s in r["sockets"].split(",")).most_common(15))


if __name__ == "__main__":
    main()
