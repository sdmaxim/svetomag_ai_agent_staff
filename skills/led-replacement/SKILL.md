---
name: led-replacement
description: Choosing an LED bulb to replace an incandescent, halogen or energy-saving bulb - wattage equivalents (e.g. 60 W -> about 8-9 W LED), keeping the same socket and shape, dimmers, 12 V halogen spots. Use when a customer wants to switch to LED or asks "which LED replaces my X W bulb".
---

# Replacing an old bulb with LED

## Rule 1: keep the socket and the shape
An LED replacement must have the **same socket** (E27, E14, GU10, GU5.3, G9...) as the old bulb, and a similar **shape**, so it fits the lamp:
- pear / standard: A55, A60, A67 (E27)
- candle: B35, C35, "candle" (mostly E14)
- small ball / golf ball: P45, P40, P20 (E14 or E27)
- spot / reflector: PAR16, MR16, "spot" (GU10 at 230 V, GU5.3 at 12 V)
- capsule: G9 (230 V), G4 (12 V)

## Rule 2: compare light output, not watts
LEDs use far fewer watts for the same light. Typical equivalents (light output in lumens, lm):

| Old incandescent | Light output | Typical LED |
|---|---|---|
| 25 W | about 250 lm | 2-4 W |
| 40 W | about 470 lm | 4-6 W |
| 60 W | about 800 lm | 7-10 W |
| 75 W | about 1050 lm | 10-12 W |
| 100 W | about 1500 lm | 13-16 W |

A 50 W GU10 or GU5.3 halogen spot is usually replaced by a 5-7 W LED spot.
An energy-saving (CFL) bulb needs roughly 1.5 times the watts of an LED for the same light (an 11 W CFL is about a 7 W LED).

## How to search the catalogue
- `search_products(socket=<same socket>, is_led=True, category="Light bulbs", min_power_w=..., max_power_w=...)` with the range from the table.
  Example: 60 W E27 -> socket "E27", is_led True, min_power_w 7, max_power_w 10.
- Add `query` with the shape word if the customer gave one ("candle", "P45", "PAR16").
- If the customer wants the same light colour as an old incandescent/halogen: `light_colour="warm"`.
- Show 2-4 options with different wattages so the customer can choose brightness.

## Be careful
- **Dimmers:** an LED on a dimmer must be dimmable. Say a product is dimmable only if its data says so; otherwise say "dimmability is not specified" and suggest checking with a specialist.
- **12 V spots (GU5.3 / MR16, G4):** they run on a transformer. GU5.3 lamps are sold in BOTH 12 V and 220-230 V versions: if the customer has a transformer, offer ONLY 12 V lamps (check `voltage_v` in the tool result; use get_product_details if it is missing) -- a 220 V lamp will not work on a 12 V transformer. Some old transformers also do not work well with LEDs (flicker, no light). You cannot verify the customer's transformer: say so honestly and offer to pass the question to a specialist.
- Never promise exact brightness in lumens unless the product data states it.
