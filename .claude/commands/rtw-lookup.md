---
description: Look up airport continent and tariff conference
argument-hint: [airport-codes]
allowed-tools: Bash(python3:*)
model: haiku
---

# Airport Lookup

Quick lookup of airport codes to continent and tariff conference.

Run: `python3 -m rtw continent $ARGUMENTS`

Present the results. If the user provided city names instead of codes, help them find the right IATA code.

Common mappings for reference:
- London = LHR (Heathrow) or LGW (Gatwick)
- Tokyo = NRT (Narita) or HND (Haneda)
- New York = JFK or EWR
- Paris = CDG
- Dubai = DXB
- Singapore = SIN
- Hong Kong = HKG
- Sydney = SYD
- Bangkok = BKK
- Istanbul = IST
