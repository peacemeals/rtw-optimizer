# oneworld Explorer DONE4/DONE5 Optimization Guide

## 1. DONE4 vs DONE5 Decision Framework

### Incremental Cost
- DONE4 to DONE5 typically costs an additional **$700-$1,000** in business class
- From cheaper origins (ex-Japan, ex-CAI), the increment can be as low as ~$900
- From expensive origins (ex-US), the increment is $1,200-$1,500+

### Reference Pricing (Business Class, approximate)
| Continents | Ex-US | Ex-Japan | Ex-Cairo | Ex-South Africa |
|-----------|-------|----------|----------|----------------|
| DONE3 | ~$9,000 | ~$5,500 | ~$3,500+ | ~$4,000 |
| DONE4 | ~$10,500 | ~$6,360 | ~$4,000+ | ~$5,000 |
| DONE5 | ~$12,000 | ~$7,260 | ~$4,400+ | ~$5,700 |
| DONE6 | ~$14,099 | ~$8,500 | ~$5,500+ | ~$6,662 |

*Note: These are approximate and fluctuate with currency rates and fare filings.*

### When DONE5 is Worth It
- If you're already visiting 4 continents AND your routing naturally touches a 5th
- When the incremental cost is small relative to what a separate ticket to that continent would cost
- Ex-CAI: The increment from DONE4 to DONE5 is minimal, making DONE5 almost always worth it
- Adding South America via DFW-SCL-JFK costs ~$900 extra but saves thousands vs a separate business class ticket to Santiago

### When DONE4 is Sufficient
- If your itinerary stays within Asia + SWP + NA + EU/ME
- If adding a 5th continent requires an awkward routing detour
- If you're on a tight budget and the 5th continent can be visited on a separate trip

---

## 2. Cheap Origin Cities

### Tier 1: Cheapest Known Origins
| City | Currency Advantage | Notes |
|------|-------------------|-------|
| **Cairo (CAI)** | EGP devaluation (2024: USD/EGP hit 50+) | Historically the killer sweet spot. OW even pulled ex-Egypt fares briefly because they were too cheap. DONE5 ~$4,400 GBP / ~145k EGP |
| **Oslo (OSL)** | Norway filing advantage | ~$5,794 EUR for DONE5 vs ~$8,099 from Netherlands. Easy positioning from London |
| **Johannesburg (JNB)** | ZAR weakness | DONE6 as low as $6,662. Good if Africa is on your route anyway |

### Tier 2: Moderate Value Origins
| City | Notes |
|------|-------|
| **Tokyo (NRT/HND)** | DONE4 ~$6,360, DONE5 ~$7,260. Higher taxes/YQ than CAI/OSL |
| **Colombo (CMB)** | Occasionally mentioned as cheap. SriLankan Airlines is oneworld |
| **Karachi (KHI)** | Historically cheap, limited current data |

### Tier 3: Expensive Origins (Avoid if Possible)
| City | Notes |
|------|-------|
| **USA origins** | DONE5 ~$12,000+, DONE6 ~$14,099 |
| **UK origins (LHR)** | Higher than OSL/CAI, plus high UK departure taxes |
| **Australia (SYD)** | Ex-Japan is roughly half the price for same itinerary |

### Positioning Strategy
- If based in London: Position to CAI or OSL for cheap tickets
- CAI positioning: ~$100-200 on budget carrier or Avios
- OSL positioning: ~$100-150 from London
- The positioning cost is trivial compared to fare savings

---

## 3. YQ/YR Surcharge Optimization

### Understanding YQ/YR
- YQ and YR are carrier-imposed surcharges (fuel surcharges/carrier fees)
- These are charged **per segment** and vary enormously by carrier
- On a 16-segment DONE5, YQ can be the difference between $500 and $3,000+

### Carrier Surcharge Rankings (Approximate)
| Carrier | YQ Level | Notes |
|---------|----------|-------|
| **Japan Airlines (JL)** | LOW | Recommended to minimize surcharges |
| **American Airlines (AA)** | LOW-MED | Generally reasonable |
| **Fiji Airways (FJ)** | LOW | New member, limited data |
| **Qatar Airways (QR)** | MEDIUM | Significant fuel surcharges |
| **Qantas (QF)** | MEDIUM-HIGH | |
| **Cathay Pacific (CX)** | MEDIUM | Better than BA |
| **British Airways (BA)** | **VERY HIGH** | Notorious for massive fuel surcharges, especially on premium cabins |
| **Iberia (IB)** | **VERY HIGH** | ~$850 one-way surcharges on business class |

### Optimization Strategies
1. **Avoid BA long-haul segments where possible** - or use BA only for short-haul EU legs where YQ is lower
2. **Use JL or AA for Pacific crossings** - much lower surcharges than QF or CX
3. **Route through DOH instead of LHR** - QR QSuite is better product AND lower surcharges than BA
4. **Validating carrier matters**: The validating (issuing) carrier affects how surcharges are calculated. QR, JL, or QF are often preferred over BA

### UK Tax Optimization
- UK has **zero landing fees** but **very high departure taxes** (especially premium cabin long-haul)
- Strategy: Fly INTO the UK but depart from elsewhere if possible
- For ex-CAI routing returning via LHR-CAI: the LHR departure is short-haul to CAI which has lower UK APD

---

## 4. Segment Optimization Strategy

### Core Principle
Every segment on a 16-segment ticket is worth the same to you regardless of flight length. Therefore:
- **Use DONE segments for long-haul, expensive flights**
- **Buy short, cheap flights separately as side trips**

### What Should Be ON the DONE Ticket
- Long-haul intercontinental flights (6+ hours) - these are very expensive in business class
- Remote Pacific island flights (NAN-TRW, NAN-FUN, NAN-APW) - expensive and infrequent
- Any flight where business class one-way would cost $500+

### What Should Be Side Trips
- Flights under 2 hours where economy is cheap: SYD-MEL (~$50-80 RT), HNL-LIH (~$80-100 RT)
- Japan domestic (use Shinkansen for Tokyo-Kyoto-Osaka)
- Mainland China side trips from HKG/TPE
- Short intra-Australia hops
- Budget carrier routes in SE Asia

### The "Leftover Segments" Trick
If you have unused segments after building your core routing:
- From a northern hemisphere origin, you can take free/cheap US round trips using remaining NA segments
- Example: If returning via JFK-LHR-CAI and you have 2 spare NA segments, add JFK-MIA-JFK for free

---

## 5. Amadeus Pricing Guide (For Your Travel Agent)

### Step 0: Pre-Price Without PNR (FQP)
```
FQPLON/ABA/VRW CHI HNL SYD BKK LON
```
- Prices a routing **without creating a PNR** - useful for testing multiple routings quickly
- Replace cities with your planned itinerary

### Step 1: Display RTW Fare Table
```
FQDCAICAI/VRW/15MAR
```
- Note: Same city must appear twice (CAICAI, not just CAI)
- Replace CAI with origin city, 15MAR with travel date
- This shows all available xONEx fare bases (DONE3-6, LONE3-6, AONE3-6)
- Filter by carrier: `FQDCAICAI/VRW/AAA` (AA fares), `FQDCAICAI/VRW/ABA` (BA fares)
- Scroll: `MD` (down), `MU` (up)
- View fare notes: `FQN3` (for line 3); fare rules: `FRN3`; routing: `FQR3`

### Step 2: Verify DONE5 Exists for Your Origin
Look for DONE5 in the fare display results. If it's not there, the fare may not be filed for that origin/date/carrier.

### Step 3: Build the PNR
- Ensure all segments booked in correct booking classes:
  - **Business**: D class (most carriers), B class (all except AA), **H class (AA only)**
  - **Economy**: L class (most carriers), I class (some carriers)
- Ensure all carriers are oneworld members/affiliates
- **Insert `OSI YY OW RTW`** into the PNR to prevent cancellation

### Step 4: Force DONE5 Pricing
```
FXP/S2RW/A-DONE5
```
- `FXP` = Price PNR and create TST
- `/S2` = Start RTW pricing from segment 2 (adjust number to match first RTW segment)
- `RW` = Force Round-the-World pricing
- `/A-DONE5` = **Validated** fare basis override (gives FCMI=0 automatic TST)

**CRITICAL**: Always use `/A-DONE5` (validated), NOT `/L-DONE5` (manual override). The `/L-` version bypasses validation, creates a manual TST (FCMI=M) that airlines may reject at audit.

### Force Validating Carrier
```
FXP/S2RW/A-DONE5/R,VC-AA
```
- `/R,VC-AA` = Force American Airlines as validating carrier (lowest YQ)

### Common Problems
1. **System defaults to LONE5**: Agent ran `FXP` without the `/SxRW/A-DONE5` modifiers
2. **Wrong fare basis selected**: Delete old TSTs with `TTE/ALL` and re-price from scratch
3. **Economy classes booked on some segments**: System will pick LONE5 if any segment is in L-class
4. **AA H-class mismatch**: AA uses H class for business, not D or B - #1 cause of DONE pricing failures
5. **If `/A-` fails but `/L-` works**: You have a booking class mismatch that needs fixing, not overriding

### Troubleshooting Workflow
```
TQT                              -- Check existing TSTs
TTE/ALL                          -- Delete ALL old TSTs
-- Fix booking classes if needed --
FXP/S2RW/A-DONE5                 -- Re-price
FXP/S2RW/A-DONE5/R,VC-AA        -- Try forcing AA as validating carrier
```

### What to Tell Your Travel Agent
> "Please price this as a oneworld Explorer DONE5 in Amadeus, not LONE5.
> Use the RW table: `FQDCAICAI/VRW/[date]` to confirm DONE5 is filed.
> With the itinerary in business booking codes, run:
> `FXP/SxRW/A-DONE5/R,VC-AA`
> where Sx is the first RTW sector. Use AA as validating carrier for lowest surcharges.
> Make sure AA segments are booked in H class (not D).
> Insert `OSI YY OW RTW` into the PNR."

---

## 6. Validating Carrier Selection

The validating carrier (who issues the ticket) matters for:
- Surcharge levels (YQ/YR)
- Customer service for changes
- Lounge access policies
- Mileage earning rules

### Recommended Validating Carriers
| Carrier | Pros | Cons |
|---------|------|------|
| **Qatar Airways (QR)** | Good service, reasonable YQ, files fares from many origins | Can't originate from DOH on oneworld Explorer |
| **Japan Airlines (JL)** | Low surcharges, excellent service | Best from ex-Japan origins |
| **Qantas (QF)** | Good for ex-SYD/MEL, extensive rules knowledge | Higher YQ than JL |
| **British Airways (BA)** | Easy for UK-based travelers, files from many origins | HIGH surcharges |

### Important Note
- **Doha (DOH) cannot be used as the origin city** for oneworld Explorer/Global Explorer tickets
- The online booking tool typically issues through the first-segment airline (not always QR)
- Best practice: Call the airline RTW desk directly rather than using the online tool

---

## 7. Side Trip Economics (For Your Specific Trip)

### Flights That Should Be ON the DONE5 Ticket
| Route | One-way J estimate | Why on ticket |
|-------|-------------------|---------------|
| CAI-DOH | $800+ | Long-haul intercontinental |
| DOH-JNB or DOH-NRT | $2,000+ | Ultra long-haul |
| JNB-SYD or NRT-NAN | $1,500+ | Major intercontinental |
| NAN-NOU/AKL | $400-600+ | Expensive regional |
| AKL-NRT / SYD-HKG | $1,500+ | Major intercontinental |
| NRT-HNL | $1,200+ | Trans-Pacific |
| HNL-LAX | $500+ | Domestic long-haul |
| LAX-MEX | $400+ | International |
| MEX-JFK or DFW-JFK | $400+ | Domestic |
| JFK-LHR | $2,000+ | Transatlantic |
| LHR-CAI | $300+ | Short international |

### Flights Better as Side Trips
| Route | Economy RT estimate | Flight time | Cabin |
|-------|-------------------|-------------|-------|
| HNL-LIH (Kauai) | ~$100 | 44 min | Economy |
| SYD-MEL | ~$60-80 | 1h30 | Economy |
| NAN-TRW (Kiribati) | ~$530 | 3h+ | Economy (if not on ticket) |
| NAN-FUN (Tuvalu) | ~$550 | 3h | Economy |
| NAN-APW (Samoa) | ~$350 | 3h | Economy |
| NRT-TPE (if not on ticket) | ~$150-200 | 4h | Economy |
| Tokyo-Kyoto | ~$130 (Shinkansen) | 2h15 | Train |

---

## 8. Booking Timeline Tips

- **American Airlines** only allows 330-day advance bookings (vs ~360 for most others)
- Book by mid-February at latest for dummy bookings on far-out flights
- Date changes are free and don't trigger re-pricing after first flight
- Strategy: Use dummy dates for distant flights, change dates later for free
- Have all flight numbers, dates, and airport codes ready before calling the airline RTW desk

---

## 9. Mileage Earning Optimization

- Business class oneworld Explorer earns significant frequent flyer miles
- With Platinum status + 100% business class bonus, expect 100,000+ miles on a DONE4
- Choose your earning program strategically:
  - **BAEC (British Airways)**: Good for Avios earning, tier points
  - **QR Privilege Club**: Good for earning on QR flights
  - **AA AAdvantage**: Good for status credits on AA segments
  - **JAL Mileage Bank**: Good value redemptions in Asia

---

## Sources

- [FlyerTalk oneworld Explorer User Guide](https://www.flyertalk.com/forum/oneworld/2008084-oneworld-explorer-user-guide.html)
- [FlyerTalk Booking & Pricing Experiences](https://www.flyertalk.com/forum/oneworld/1776577-oneworld-booking-pricing-experiences.html)
- [FlyerTalk Fuel Surcharge Differences](https://www.flyertalk.com/forum/oneworld/919981-fuel-surcharge-differences-xonex-fares.html)
- [FlyerTalk Cheapest Europe Origins](https://www.flyertalk.com/forum/oneworld/2133996-cheapest-place-europe-one-world-explorer-fares.html)
- [Australian Frequent Flyer Guide](https://www.australianfrequentflyer.com.au/oneworld-explorer-rtw-guide/)
- [Qantas Quick Reference Guide](https://www.qantas.com/content/dam/qac/oneworld-clue-cards/oneworld-quick-reference-guide.pdf)
- [LoyaltyLobby Ex-Cairo RTW](https://loyaltylobby.com/2016/11/09/my-oneworld-around-the-world-ticket-ex-cairo-16-segments-33k-miles/)
- [Amadeus RTW Booking Options](https://servicehub.amadeus.com/c/portal/view-solution/875457/round-the-world-booking-options-rtw/ct-)
- [Amadeus FQD Options](https://servicehub.amadeus.com/c/portal/view-solution/716365606/how-to-request-a-fare-display-fqd-with-options-cryptic-)

### Detailed Research Files
- `specs/oneworld-explorer-optimization/research.md` - Amadeus GDS Technical Guide (commands, DRNE5 analysis, YQ comparison, ex-CAI specifics)
- `specs/oneworld-explorer-optimization/ow-explorer-fare-rules-research.md` - Deep Fare Rules Research (16 sections of detailed rule analysis)
