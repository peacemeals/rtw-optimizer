---
description: Compare RTW fares across origin cities
argument-hint: [ticket-type]
allowed-tools: Bash(python3:*), AskUserQuestion
---

# RTW Fare Comparison Across Origins

Compare what the same RTW ticket costs from different starting cities. Helps users find the cheapest origin.

## Get Ticket Type

If `$ARGUMENTS` contains a ticket type (DONE3, DONE4, DONE5, DONE6, LONE3, LONE4, LONE5, LONE6), use it.

Otherwise, use AskUserQuestion:
- header: "Ticket type"
- question: "Which ticket type do you want to compare across origins?"
- options:
  - label: "DONE4 (Recommended)"
    description: "Business class, 4 continents — most popular"
  - label: "DONE3"
    description: "Business class, 3 continents"
  - label: "LONE4"
    description: "Economy class, 4 continents"
  - label: "DONE6"
    description: "Business class, 6 continents — maximum"
- multiSelect: false

## Run Comparison

Execute this Python to get fare comparison:

```python
python3 -c "
from rtw.cost import CostEstimator
from rtw.models import TicketType
e = CostEstimator()
results = e.compare_origins(TicketType('[TICKET_TYPE]'))
for r in results:
    print(f\"{r['origin']:>5} ({r['name']:<20}) ${r['fare_usd']:>10,.0f}  {r['notes']}\")
print(f\"\\nCheapest: {results[0]['origin']} at ${results[0]['fare_usd']:,.0f}\")
print(f\"Most expensive: {results[-1]['origin']} at ${results[-1]['fare_usd']:,.0f}\")
print(f\"Savings: ${results[-1]['fare_usd'] - results[0]['fare_usd']:,.0f} by choosing {results[0]['origin']} over {results[-1]['origin']}\")
"
```

Present the results as a ranked table, cheapest first. Highlight:
- The cheapest origin and how much it saves vs the most expensive
- Any origins that are particularly good value (e.g., Cairo, Oslo)
- Note that positioning flights to a cheaper origin can save thousands

Suggest: "Use `/rtw-plan` to start planning from your chosen origin."
