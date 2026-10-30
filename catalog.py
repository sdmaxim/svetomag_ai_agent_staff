"""
Catalogue search functions -- the backend of the support agent's tools.

    search_products(...)  free text + filters -> short list of matching products
    get_product(id)       full details of one product (price, stock, description)

Every value returned comes straight from catalog.db (built by build_catalog.py).
"""
import re
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "catalog.db"

SUMMARY_FIELDS = ["id", "name", "brand", "category", "sockets", "num_lamps", "power_w", "voltage_v", "ip_rating",
                  "is_led", "light_colour", "finish_colour", "bulbs_included", "price_eur", "quantity"]


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


STOP = {"a", "an", "the", "for", "with", "and", "or", "of", "in", "to", "my", "me", "need", "want",
        "looking", "please", "some", "any", "that", "which", "can", "you", "have", "do", "is", "it", "i"}
MIXED_GROUP = "LED strips, garlands & profiles"   # a group name about many things: never a type hint


def _words(text: str) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", text.lower()) if len(w) > 1]
    return [w for w in words if w not in STOP]


def _fts_query(text: str) -> str | None:
    """User words -> an FTS5 query: every word may match as a prefix, best matches rank first."""
    return " OR ".join(f'"{w}"*' for w in _words(text)) or None


def _type_match(words: list[str], category: str) -> float:
    """Share of the customer's words that name this product's type (its category path)."""
    path = category.replace(MIXED_GROUP + " > ", "")
    cat_words = re.findall(r"[a-z0-9]+", path.lower())
    hits = sum(any(c.startswith(w[:5]) or w.startswith(c[:5]) for c in cat_words) for w in words)
    return hits / len(words) if words else 0.0


def search_products(query: str | None = None, socket: str | None = None, category: str | None = None,
                    is_led: bool | None = None, min_ip: int | None = None,
                    min_power_w: float | None = None, max_power_w: float | None = None, voltage: int | None = None,
                    light_colour: str | None = None, finish_colour: str | None = None,
                    min_price: float | None = None, max_price: float | None = None,
                    in_stock_only: bool = False, limit: int = 10) -> list[dict]:
    """Search the catalogue. All filters are optional; text results are ranked by relevance."""
    where, args = [], []
    if socket:
        where.append("(',' || lower(p.sockets) || ',') LIKE ?")
        args.append(f"%,{socket.strip().lower()},%")
    if category:
        # forgiving: every word must appear somewhere in the path, by its first 5 letters,
        # so "Ceiling lights" finds "Home lighting > Chandeliers > Ceiling"
        for w in re.findall(r"[a-z0-9']+", category.lower()):
            if w in STOP or w in {"light", "lights", "lamp", "lamps"} and len(category.split()) > 1:
                continue
            where.append("lower(p.category) LIKE ?")
            args.append(f"%{w[:5]}%")
    if is_led is not None:
        where.append("p.is_led = ?")
        args.append(int(is_led))
    if min_ip is not None:
        where.append("p.ip_rating >= ?")
        args.append(min_ip)
    if min_power_w is not None:
        where.append("p.power_w >= ?")
        args.append(min_power_w)
    if max_power_w is not None:
        where.append("p.power_w <= ?")
        args.append(max_power_w)
    if voltage is not None:
        where.append("p.voltage_v = ?")
        args.append(voltage)
    if light_colour:
        where.append("p.light_colour = ?")
        args.append(light_colour.strip().lower())
    if finish_colour:
        where.append("lower(p.finish_colour) LIKE ?")
        args.append(f"%{finish_colour.strip().lower()}%")
    if min_price is not None:
        where.append("p.price_eur >= ?")
        args.append(min_price)
    if max_price is not None:
        where.append("p.price_eur <= ?")
        args.append(max_price)
    if in_stock_only:
        where.append("p.quantity > 0")

    cols = ", ".join(f"p.{c}" for c in SUMMARY_FIELDS)
    fts = _fts_query(query) if query else None
    rows: list[dict] = []
    with _connect() as con:
        if fts:
            # 1) text relevance (bm25 weights: name, category_leaf, category path, short_description,
            #    description, parameters, brand), top 200 candidates
            sql = (f"SELECT {cols}, bm25(products_fts, 5.0, 12.0, 8.0, 1.0, 0.5, 0.5, 2.0) AS score "
                   f"FROM products_fts f JOIN products p ON p.id = f.rowid "
                   f"WHERE products_fts MATCH ? {''.join(' AND ' + w for w in where)} "
                   f"ORDER BY score LIMIT 200")
            cands = [dict(r) for r in con.execute(sql, [fts] + args)]
            # 2) rerank: if the customer's words name a product type ("LED strip", "ballast"), products of
            #    that type come first -- a controller "for LED strips" must not beat the strips themselves.
            words = _words(query)
            # in-stock products first among equals (a small penalty, so an exact out-of-stock match still shows)
            cands.sort(key=lambda r: r["score"] - 10.0 * _type_match(words, r["category"] or "")
                       + (1.0 if r["quantity"] == 0 else 0.0))
            rows = [{k: v for k, v in r.items() if k != "score"} for r in cands[:limit]]
        if len(rows) < limit and (where or not fts):
            # Words matched too few products: fill up with products that match the filters alone,
            # so a customer never hears "nothing found" when suitable products exist.
            seen = [r["id"] for r in rows]
            extra = where + ([f"p.id NOT IN ({','.join('?' * len(seen))})"] if seen else [])
            sql = (f"SELECT {cols} FROM products p {('WHERE ' + ' AND '.join(extra)) if extra else ''} "
                   f"ORDER BY p.quantity > 0 DESC, p.price_eur LIMIT ?")
            rows += [dict(r) for r in con.execute(sql, args + seen + [limit - len(rows)])]
    return rows


def get_product(product_id: int) -> dict | None:
    """Full details of one product, including price, stock and the shop's own description."""
    with _connect() as con:
        r = con.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(r) if r else None


if __name__ == "__main__":
    for r in search_products("LED bulb", socket="E27", in_stock_only=True, limit=5):
        print(r)
