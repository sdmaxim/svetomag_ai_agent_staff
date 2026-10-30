"""
20 test searches for the catalogue, written the way customers think.
Each case checks the results with code (not just "something was found").

Usage (from the support_agent folder):
    .\\run.ps1 test catalog
"""
from catalog import get_product, search_products


def has(field, value):
    return lambda r: value.lower() in str(r[field] or "").lower()


def socket_is(s):
    return lambda r: s.lower() in (r["sockets"] or "").lower().split(",")


CASES = [
    # (description, search kwargs, check every result, check top result)
    ("E27 LED bulb", dict(query="bulb", socket="E27", is_led=True),
     [socket_is("E27"), lambda r: r["is_led"] == 1], has("category", "Light bulbs")),
    ("E14 candle bulb", dict(query="candle", socket="E14", category="Light bulbs"),
     [socket_is("E14"), has("category", "Light bulbs")], None),
    ("GU10 bulb, max 50 W", dict(socket="GU10", category="Light bulbs", max_power_w=50),
     [socket_is("GU10"), lambda r: r["power_w"] <= 50], None),
    ("G9 capsule halogen", dict(query="capsule", socket="G9", category="Halogen"),
     [socket_is("G9"), has("category", "Halogen")], None),
    ("T8 fluorescent tube G13 36W", dict(query="tube", socket="G13", min_power_w=36, max_power_w=36),
     [socket_is("G13"), lambda r: r["power_w"] == 36], None),
    ("warm white bulbs", dict(category="Light bulbs", light_colour="warm"),
     [lambda r: r["light_colour"] == "warm"], None),
    ("cold light bulbs", dict(category="Light bulbs", light_colour="cold"),
     [lambda r: r["light_colour"] == "cold"], None),
    ("bathroom light IP44+", dict(query="ceiling light", min_ip=44, category="Home lighting"),
     [lambda r: r["ip_rating"] >= 44], None),
    ("outdoor wall light", dict(category="Outdoor lighting > Wall"),
     [has("category", "Outdoor lighting > Wall")], None),
    ("garden bollard in stock", dict(category="Bollards", in_stock_only=True),
     [has("category", "Bollards"), lambda r: r["quantity"] > 0], None),
    ("chrome chandelier under 100 EUR", dict(query="chandelier", finish_colour="chrome", max_price=100),
     [has("finish_colour", "chrome"), lambda r: r["price_eur"] <= 100], has("category", "Chandeliers")),
    ("cheap table lamp", dict(category="Table lamps", max_price=20),
     [has("category", "Table lamps"), lambda r: r["price_eur"] <= 20], None),
    ("floor lamp E27", dict(category="Floor lamps", socket="E27"),
     [has("category", "Floor lamps"), socket_is("E27")], None),
    ("children's ceiling light", dict(category="Children's"),
     [has("category", "Children's")], None),
    ("Philips bulbs by name", dict(query="Philips", category="Light bulbs"),
     [has("brand", "Philips")], None),
    ("Massive brand spotlight", dict(query="Massive spotlight"),
     [], has("category", "Spotlights")),
    ("LED strip RGB", dict(query="RGB LED strip"),
     [], has("category", "> LED strips")),
    ("Christmas garland outdoor", dict(query="garland outdoor"),
     [], has("category", "> Garlands")),
    ("motion sensor", dict(query="motion sensor"),
     [], has("category", "Motion sensors")),
    ("ballast for fluorescent 36W", dict(query="ballast 36W"),
     [], has("category", "Ballasts")),
]


def main():
    passed = 0
    for i, (title, kwargs, every, top) in enumerate(CASES, 1):
        rows = search_products(limit=10, **kwargs)
        problems = []
        if not rows:
            problems.append("no results")
        for r in rows:
            for check in every:
                if not check(r):
                    problems.append(f"#{r['id']} fails a filter: {r['name'][:50]}")
                    break
        if rows and top and not top(rows[0]):
            problems.append(f"top result is off: {rows[0]['name'][:60]} [{rows[0]['category']}]")
        ok = not problems
        passed += ok
        first = f"{rows[0]['name'][:55]} | {rows[0]['sockets']} | {rows[0]['power_w']}W | EUR {rows[0]['price_eur']} | qty {rows[0]['quantity']}" if rows else "-"
        print(f"{'PASS' if ok else 'FAIL'} {i:2}. {title:34} {len(rows):2} results  top: {first}")
        for p in problems[:3]:
            print(f"        ! {p}")

    p = get_product(rows[0]["id"]) if rows else None
    detail_ok = bool(p) and all(k in p for k in ("price_eur", "quantity", "description"))
    print(f"{'PASS' if detail_ok else 'FAIL'}     get_product returns price, quantity and description")
    print(f"\n{passed + detail_ok}/{len(CASES) + 1} passed")


if __name__ == "__main__":
    main()
