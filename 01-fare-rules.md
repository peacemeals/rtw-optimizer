# oneworld Explorer Fare Rules - Comprehensive Reference

## 1. Product Overview

The **oneworld Explorer** is a continent-based round-the-world fare product offered by the oneworld alliance. Unlike the mileage-based Global Explorer, pricing is determined by:
- **Cabin class** (Economy / Business / First)
- **Number of continents** visited (3 to 6)

There is **no overall mileage cap** - the constraint is segment count and per-continent limits.

**Rule reference**: Rule 3015 (oneworld Explorer)

---

## 2. Fare Basis Codes

Format: `[Cabin Letter]ONE[Number of Continents]`

| Prefix | Cabin | Examples |
|--------|-------|----------|
| **L** | Economy | LONE3, LONE4, LONE5, LONE6 |
| **D** | Business | DONE3, DONE4, DONE5, DONE6 |
| **A** | First | AONE3, AONE4, AONE5, AONE6 |

**Important**: The number represents continents, not segments. DONE5 = Business class, 5 continents.

### DRNE5 / RNE Variants
The "RNE" suffix appears to be a restricted/non-endorsable variant. Research is inconclusive on exact differences from standard DONE5. When your agent sees DRNE5 instead of DONE5, it may be a regional filing variant - the underlying rules should be identical.

### Cabin Class Rule (Critical)
**Only one cabin class per ticket.** The fare for the highest class used on ANY segment applies to the ENTIRE ticket. You cannot mix business and economy on the same ticket - if even one segment is booked in D class, the whole ticket is priced as DONE.

There is no premium economy fare on oneworld Explorer. Economy tickets allow paid upgrades on individual segments.

---

## 3. Continent Definitions

oneworld divides the world into **6 continents** mapped to IATA Tariff Conferences:

### Tariff Conference 2 (TC2)
| Continent | Includes |
|-----------|----------|
| **Europe/Middle East** | All of Europe, Middle East, **Egypt**, Libya, Sudan, Algeria, Morocco, Tunisia, Russia west of Urals, Armenia, Azerbaijan, Georgia, Moldova, Yemen |
| **Africa** | Sub-Saharan Africa (South Africa, Kenya, etc.) - does NOT include North Africa |

### Tariff Conference 3 (TC3)
| Continent | Includes |
|-----------|----------|
| **Asia** | Japan, China, Hong Kong, Taiwan, SE Asia, India, Russia east of Urals |
| **South West Pacific (SWP)** | Australia, New Zealand, Fiji, Pacific Islands (Kiribati, Tuvalu, Samoa, New Caledonia, Vanuatu, Tonga, etc.) |

### Tariff Conference 1 (TC1)
| Continent | Includes |
|-----------|----------|
| **North America** | USA, Canada, **Mexico**, Caribbean, Bermuda, Central America, Panama, **Hawaii** |
| **South America** | All of South America south of Panama |

### Key Classifications to Remember
- **Egypt (CAI)** = Europe/Middle East (NOT Africa)
- **Qatar (DOH)** = Europe/Middle East
- **Jordan (AMM)** = Europe/Middle East
- **Mexico (MEX)** = North America
- **Hawaii (HNL)** = North America
- **Fiji (NAN)** = South West Pacific
- **Kiribati (TRW)** = South West Pacific
- **Tuvalu (FUN)** = South West Pacific
- **Samoa (APW)** = South West Pacific

---

## 4. Segment Rules

### Overall Limit
- **Minimum**: 3 segments
- **Maximum**: 16 segments (including surface sectors)

### Per-Continent Limits (after departing origin continent)
| Continent | Max Flight Segments |
|-----------|-------------------|
| Europe/Middle East | 4 |
| Africa | 4 |
| Asia | 4 |
| South West Pacific | 4 |
| North America | **6** |
| South America | 4 |

### What Counts as a Segment
- **Flight segment**: A direct flight between two airports (may include technical stops en route)
- **Surface segment**: Landing at one airport and departing from a different airport by ground transport. **Surface segments count toward the 16-segment limit and per-continent limits.**

### Intercontinental Departures/Arrivals
- Only **one intercontinental departure** and **one intercontinental arrival** permitted in each continent
- **Exceptions**:
  - **Two** permitted in North America
  - **Two** permitted in Asia when one is for travel between SWP and Europe
  - **Two** permitted for US-origin when one arrival-departure is a transfer without stopover

---

## 5. Direction of Travel & Ocean Crossings

### Continuous Forward Direction
Travel must be in a **continuous forward direction** between Tariff Conferences: TC1 - TC2 - TC3 (or reverse). You choose eastbound or westbound and must maintain that direction between TCs.

### Within a Continent
**Backtracking within a continent is permitted** (with some exceptions - see below).

### Ocean Crossings
- Must cross both the **Atlantic** and **Pacific** oceans
- Only **one crossing of each ocean** is permitted
- Ocean crossings must be **flown** (not surface sectors)
- **Exception**: For itineraries originating in SWP, one transoceanic surface sector between TC1-TC2 or TC1-TC3 is permitted

### Backtracking Exceptions
- **Hawaii**: Backtracking between Hawaii and other points in North America is NOT permitted
- **Alaska**: Only one flight TO Alaska and one flight FROM Alaska permitted

---

## 6. Stopover Rules

### Definition
- **Stopover**: More than 24 hours between scheduled arrival and departure
- **Transfer/Transit**: 24 hours or less between flights

### Requirements
- **Minimum**: 2 stopovers required in the entire itinerary
- **Origin continent limit**: Maximum 2 stopovers in continent of origin
- **Country of origin**: Maximum 1 stopover per direction in the country of origin

### Multiple Stopovers at Same City
- You can stop at the same place up to **4 times** (5 in North America)
- No restriction on multiple stopovers at the same place (except point of origin)

### Return to Origin
- You **cannot return to your country of origin** until the end of the journey
- **Exception**: US-origin passengers may transit the USA once without a stopover

---

## 7. Surface Sector Rules

### Permitted Surface Sectors
- Intermediate surface sectors are permitted **at the passenger's expense**
- Surface sectors between the following pairs do NOT count toward segment limits (origin-destination exception):
  - Within country of origin
  - Within Middle East
  - USA / Canada
  - Hong Kong / China
  - Malaysia / Singapore
  - Within Africa
  - Maldives / Sri Lanka / India

### Prohibited Surface Sectors
- **Transoceanic surface sectors** between TC1-TC2 and TC1-TC3 are **NOT permitted**
- Exception: SWP-origin itineraries may have one transoceanic surface sector

### Avoiding Wasted Segments
Surface segments like LGA-JFK or LHR-LGW waste a segment. Strategy: find routing where such segments are eliminated.

---

## 8. City Pair Restrictions

- **Same city pair cannot be flown more than once in the same direction**
- This means NRT-TPE and TPE-NRT are fine (different directions), but NRT-TPE twice is not

---

## 9. Australia-Specific Restrictions

Only **one nonstop/single-plane service flight** permitted between specific city pairs:
- BNE/CBR/CNS/SYD/MEL ↔ PER
- CBR/MEL/SYD ↔ DRW
- BNE/MEL/SYD ↔ BME/KTA

Exceptions apply for Perth and New Zealand origins with specific Africa connections.

---

## 10. North America Transcontinental Restrictions

- Only **one nonstop transcontinental flight** permitted within USA/Canada (defined as travel between Eastern and Western state groupings)
- Only one flight to Alaska and one from Alaska
- No backtracking between Hawaii and mainland

---

## 11. Northern/Southern Hemisphere Revisit Rule

- Northern hemisphere continents can be visited **twice**
- Southern hemisphere continents can be visited **only once**
- To revisit a northern continent, you must travel to its **southern hemisphere neighbor** and return
- You can stopover in the northern continent both before and after traveling south

### Europe/Middle East Zone Rule
If both intercontinental flights are between Africa and the Europe Zone, then **South Africa and Mauritius cannot be included** in the itinerary.

---

## 12. Ticket Validity & Stay Requirements

- **Maximum stay**: 12 months from departure (return travel from last stopover must commence within 12 months)
- **Minimum stay**: 10 days
- Airlines allow booking up to 1 year in advance
- Date changes are free (don't trigger re-pricing after first flight departure)

---

## 13. Booking Classes for Business (DONE)

For DONE* Business Class fares:
- Primary booking class: **D** (on most carriers)
- Fallback: **B** class (except on American Airlines)
- On American Airlines: **H** class
- The fare for the highest class used applies, without compensation for downgrade

### Key Carrier Booking Classes (Business)
| Airline | Business Classes |
|---------|-----------------|
| Qatar Airways (QR) | D, J, C, I, R |
| British Airways (BA) | D, J, C |
| Qantas (QF) | D, J, C |
| Cathay Pacific (CX) | D, J, C |
| Japan Airlines (JL) | D, J, C |
| American Airlines (AA) | D, J (note: H class fallback for DONE) |
| Fiji Airways (FJ) | D, J |
| Royal Jordanian (RJ) | D, J, C |

---

## 14. Changes & Cancellations

### Ticketed Point Changes (airports, connection changes)
- USD 125 fee per change event
- Add-ons recalculated

### Non-Ticketed Point Changes (dates, airline substitution)
- No change fee (possible service fee)
- May trigger re-price if made before departure and first segment affected

### Capacity Changes
- **Adding continents / upgrading class**: No fee; must pay recalculated fare
- **Downgrading class**: No refund, USD 125 fee

### Cancellation
- Fee applies; can cancel anytime

---

## 15. Eligible Airlines (Current oneworld Members, as of 2025-2026)

### Full Members
1. American Airlines (AA)
2. British Airways (BA)
3. Cathay Pacific (CX)
4. **Fiji Airways (FJ)** - joined April 1, 2025
5. Finnair (AY)
6. Iberia (IB)
7. Japan Airlines (JL)
8. Malaysia Airlines (MH)
9. Qantas (QF)
10. Qatar Airways (QR)
11. Royal Air Maroc (AT)
12. Royal Jordanian (RJ)
13. S7 Airlines (S7)
14. SriLankan Airlines (UL)

**Note**: LATAM Airlines left oneworld in 2020 and joined SkyTeam. They are NOT eligible for oneworld Explorer tickets. This critically limits South America routing to connections via AA (MIA hub), BA, IB, or QR.

### Affiliate Airlines (relevant)
- **Fiji Link** - oneworld affiliate; extends network to Pacific islands including domestic Fiji routes plus Tonga, Samoa, Tuvalu, Vanuatu
- Alaska Airlines (AS) - can be used on certain routes

### Note on Fiji Airways/Fiji Link
Fiji Airways became a **full oneworld member on April 1, 2025** (previously oneworld Connect from 2018). Fiji Link as an affiliate extends to: Suva, Nadi, Labasa, Taveuni, Kadavu domestically; plus Tonga, Samoa, Tuvalu, Vanuatu regionally.

---

## 16. Continent Counting Rules

- You pay per continent **visited**, including your origin continent
- Even technical plane stops count (e.g., London-Sydney stopping in Singapore = you pay for Asia)
- Non-stop trans-Asia flights (e.g., London-Perth) still charge for Asia continent
- The continent of origin always counts as one of your continents
- **Transits count as continent visits**: Even a 2-hour connection in Singapore counts Asia as visited for pricing purposes

---

## 17. No Mileage Cap (oneworld Explorer)

- oneworld Explorer has **NO maximum mileage limit** - it is purely continent-based
- The **Global Explorer** (different product) IS distance-based with mileage caps
- **Known bug**: The online booking tool sometimes erroneously applies the 34,000-mile Global Explorer limit to oneworld Explorer itineraries. **Workaround**: Book by phone through AA RTW desk (+1 800 843 3000) or a travel agent

---

## 18. Open Jaw Rules

### Origin-Destination Open Jaw
The ticket requires returning to the same origin point, BUT surface segments are permitted within specific geographic regions:

| Open Jaw Between | Permitted? |
|------------------|-----------|
| Within country of origin | YES |
| Within the Middle East | YES |
| Between USA and Canada | YES |
| Between Hong Kong and China | YES |
| Between Malaysia and Singapore | YES |
| Within Africa | YES |
| Between Maldives and Sri Lanka/India | YES |
| Between any other countries | NO |

### Intermediate Open Jaws
Intermediate surface sectors (landing at one airport, departing from another en route) are always permitted. They count as one of the 16 segments.

---

## 19. Additional Rules

### QR as First Carrier
- **Qatar Airways (QR) CANNOT be the first flight** on a oneworld Explorer ticket
- QR can operate segments later in the itinerary

### PNR Requirement
- **OSI YY OW RTW** must be inserted into the PNR to avoid reservation cancellation

### Children and Infants
| Category | Discount |
|----------|---------|
| Child (2-11 years) with seat | **75% of adult fare** |
| Infant (under 2) without seat | **10% of adult fare** |
| Unaccompanied minors | **NOT accepted** |

### Guam Classification
- **Guam = Asia (TC3 South East Asia sub-area)**, NOT North America, despite being a US territory

### International Transfer Limit
- Maximum **4 international transfers** from any single country
- USA-Canada is NOT counted as international for this rule

### Premium Economy
- No separate Premium Economy fare tier on oneworld Explorer
- Economy passengers can pay a per-segment surcharge (shown as "-Q-" in fare calculation) to fly Premium Economy on select carriers (AA, BA, CX, IB, JL, QF)

---

## 20. Key "Gotcha" Rules Summary

| Rule | Detail |
|------|--------|
| Egypt is NOT Africa | Egypt = Europe/Middle East continent |
| Mexico is NOT South America | Mexico = North America continent |
| Guam is NOT North America | Guam = Asia (TC3 South East Asia) |
| Hawaii backtracking banned | Cannot return to US mainland after going to Hawaii |
| Surface sectors count | Surface sectors count toward 16-segment and per-continent limits |
| No mileage cap | oneworld Explorer has NO mileage limit (unlike Global Explorer) |
| Highest class = whole ticket price | One business class segment on an economy ticket = whole ticket repriced to business |
| First carrier cannot be QR | Qatar Airways cannot be the first flight |
| Transit counts as continent visit | Even a 2-hour connection counts the continent for pricing |
| No Premium Economy tier | PE is a per-segment surcharge on Economy |
| 10-day minimum stay | Must be away at least 10 days |
| D class on AA = H class | American Airlines uses H class (not D) for OWE business |

---

## Sources

- [oneworld Explorer Rule 3015 (official PDF)](https://www.oneworld.com/images/faqs/oneworldFAQPDF.pdf)
- [FlyerTalk oneworld Explorer User Guide](https://www.flyertalk.com/forum/oneworld/2008084-oneworld-explorer-user-guide.html)
- [Australian Frequent Flyer Guide](https://www.australianfrequentflyer.com.au/oneworld-explorer-rtw-guide/)
- [Qantas Quick Reference Guide](https://www.qantas.com/content/dam/qac/oneworld-clue-cards/oneworld-quick-reference-guide.pdf)
- [Qantas Rule 3015 (April 2025 update)](https://www.qantas.com/content/dam/qac/products-and-network/oneworld-explorer-16Apr2025.pdf)
- [oneworld RTW page](https://www.oneworld.com/round-the-world)
