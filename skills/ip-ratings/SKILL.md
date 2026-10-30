---
name: ip-ratings
description: What IP ratings mean (IP20, IP23, IP44, IP54, IP65, IP67, IP68) and which rating suits bathrooms, kitchens, covered and open outdoor places, in-ground and pond lights. Use when a customer asks for a light for a bathroom, outdoors, a garden, a damp place, or asks what an IP number means.
---

# IP ratings (protection against dust and water)

An IP code has two digits: the **first** = protection against solid objects and dust (0-6), the **second** = protection against water (0-8). A higher number means more protection.

| Rating | Meaning in practice | Typical use |
|---|---|---|
| IP20 | no water protection | dry indoor rooms (living room, bedroom) |
| IP23 | protected against light spraying water | dry indoor; some covered places |
| IP44 | protected against splashing water from any direction | bathrooms (outside the shower/bath area), covered outdoor places (porch, under a roof) |
| IP54 | dust-protected, splashing water | outdoor walls, gardens |
| IP65 | dust-tight, water jets | exposed outdoor places, above showers, car ports, washing areas |
| IP67 | dust-tight, short immersion | in-ground lights, places that can flood |
| IP68 | dust-tight, continuous immersion | ponds, fountains, underwater |

## Bathrooms
- Bathrooms are divided into zones around the bath and shower. Close to water (inside or directly above the bath/shower) needs special lights (high IP, often 12 V); further away, at least **IP44** is the usual minimum.
- For a general bathroom ceiling or wall light, search with `min_ip=44`.
- Installation in bathrooms must be done by a qualified electrician: say so, and do not give wiring or zone-distance advice beyond this - offer to pass detailed questions to a specialist.

## Outdoors
- Covered (porch, under a roof): at least IP44 -> `min_ip=44`.
- Exposed to rain: IP54 or higher, IP65 for heavy weather -> `min_ip=54` or `min_ip=65`.
- In the ground or near/under water: IP67 / IP68 -> `min_ip=67`.

## How to search the catalogue
- `search_products(category=..., min_ip=<rating>)`, e.g. bathroom ceiling light: `query="ceiling light", min_ip=44`.
- Always state the product's real IP rating from the tool result.

## Be careful
- Do not claim a light is suitable for a place if its IP rating is lower than the table above.
- If the product data has no IP rating, say "the IP rating is not specified".
