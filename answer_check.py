"""
Code check of an agent reply against what the tools really returned (ToolLog).

For every line that states a price or stock level:
  - find which logged product the line talks about (by its name words),
  - the price must equal that product's price_eur,
  - "in stock (N pcs)" must equal its quantity, and "in stock" must not be said of a product with quantity 0.
Prices that match no logged product at all are flagged as invented.
"""
import re

PRICE_RE = re.compile(r"(?:€\s?(\d+(?:[.,]\d{1,2})?))|(?:(\d+(?:[.,]\d{1,2})?)\s?(?:EUR|euros?)\b)", re.I)
QTY_RE = re.compile(r"(\d+)\s*(?:pcs|pieces|units)\b|in stock\D{0,3}(\d+)", re.I)


def _name_words(name: str) -> set[str]:
    # words of 3+ letters, plus short codes with a digit ("8W", "5W", "G9") -- they tell near-twins apart
    words = re.findall(r"[a-z0-9]+(?:[./][a-z0-9]+)*", name.lower())
    return {w for w in words if len(w) >= 3 or (len(w) >= 2 and re.search(r"\d", w))}


def _line_words(line: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[./][a-z0-9]+)*", line.lower()))


def _match_product(line: str, products: dict[int, dict]) -> dict | None:
    """The logged product this line talks about. Many products have near-identical names
    ("LEDBulb 8W E27 3000K" / "LEDBulb 10W E27 3000K"), so whole words are compared and,
    on a tie, the product with more matching words wins."""
    low = _line_words(line)
    best, best_key = None, (0.0, 0)
    for p in products.values():
        words = _name_words(p["name"])
        if not words:
            continue
        hits = len(words & low)
        key = (hits / len(words), hits)
        if key > best_key:
            best, best_key = p, key
    return best if best_key[0] >= 0.5 else None


WATT_RE = re.compile(r"(?<![\d.,x])(\d+(?:[.,]\d+)?)\s*-?\s*(?:W|watts?)\b", re.I)
SOCKET_RE = re.compile(r"(?<![A-Za-z0-9])(E10|E14|E27|E40|GU10|GU5\.3|GX53|GY6\.35|G4|G9|G13|G5|G23|R7s|2G11|2GX13|G24[dq]?)(?![A-Za-z0-9.])")


def _spec_problems(line: str, p: dict) -> list[str]:
    """Watts and sockets said about a product must be that product's own (database or name)."""
    out = []
    if re.search(r"equivalent|like an?|replaces?", line, re.I):
        return out
    allowed_w = {float(w.replace(",", ".")) for w in re.findall(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*-?\s*W\b", p["name"])}
    if p.get("power_w") is not None:
        allowed_w.add(float(p["power_w"]))
    for w in WATT_RE.findall(line):
        if allowed_w and float(w.replace(",", ".")) not in allowed_w:
            out.append(f"#{p['id']} power said {w} W, product has {sorted(allowed_w)} W")
    sockets = {s.lower() for s in (p.get("sockets") or "").split(",") if s} | {s.lower() for s in SOCKET_RE.findall(p["name"])}
    for s in SOCKET_RE.findall(line):
        if sockets and s.lower() not in sockets:
            out.append(f"#{p['id']} socket said {s}, product has {sorted(sockets)}")
    return out


BUDGET_RE = re.compile(r"(?:under|below|less than|up to|max(?:imum)?|budget(?: of)?|within)\s*"
                       r"(?:€\s?\d+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?\s?(?:EUR|euros?)\b)", re.I)


def check_answer(reply: str, log) -> list[str]:
    """A product's price / stock may be on its own line or on the lines below its name
    (a "block"), so each line is checked against the product named on it, or else the last one named above."""
    problems = []
    known_prices = {round(p["price_eur"], 2) for p in log.products.values()}
    for h in getattr(log, "human_answers", []):   # prices a specialist wrote ("free delivery over €50")
        known_prices |= {round(float((a or b).replace(",", ".")), 2) for a, b in PRICE_RE.findall(h["answer"])}
    current = None
    for line in reply.splitlines():
        named = _match_product(line, log.products)
        if named is not None:
            current = named
        if current is not None:
            problems += _spec_problems(line, current)
        prices = [float((a or b).replace(",", ".")) for a, b in PRICE_RE.findall(BUDGET_RE.sub(" ", line))]
        qtys = [int(a or b) for a, b in QTY_RE.findall(line)]
        # "in stock" without a number is a claim about the block's product only on its own line or an
        # "Availability:" line -- not in a general sentence below it ("alternatives that are in stock")
        says_in_stock = (re.search(r"\bin stock\b", line, re.I) and not re.search(r"\bout of stock\b|not in stock", line, re.I)
                         and (named is not None or re.match(r"\W*(?:availability|stock)\b", line, re.I)))
        if not (prices or qtys or says_in_stock):
            continue
        p = current
        if p is None:
            for price in prices:
                if round(price, 2) not in known_prices:
                    problems.append(f"price €{price} matches no product the tools returned: {line.strip()[:90]}")
            if qtys:   # a general "here are bulbs in stock:" is fine; a stock NUMBER needs a real product
                problems.append(f"stock stated for a product the tools never returned: {line.strip()[:90]}")
            continue
        for price in prices:
            if abs(price - p["price_eur"]) > 0.005:
                problems.append(f"#{p['id']} price said €{price}, tool says €{p['price_eur']}")
        for q in qtys:
            if q != p["quantity"]:
                problems.append(f"#{p['id']} stock said {q}, tool says {p['quantity']}")
        if says_in_stock and p["quantity"] == 0:
            problems.append(f"#{p['id']} said in stock, tool says out of stock")
    return problems
