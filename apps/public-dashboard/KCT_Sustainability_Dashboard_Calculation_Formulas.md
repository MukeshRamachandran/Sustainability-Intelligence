# KCT Sustainability Dashboard --- Calculation Formula Reference

## 1. Purpose

This document contains the calculation formulas used/planned for the KCT
Sustainability Dashboard covering:

-   Scope 1 --- Petrol, transport diesel and diesel generator (DG)
-   Scope 2 --- Grid electricity
-   Renewable energy and emissions avoided
-   Gross and net carbon indicators
-   Monthly, yearly and YTD analytics
-   Comparison metrics
-   Contribution and intensity indicators
-   Dynamic dashboard insight calculations

> **Important:** The emission factors must be the approved factors
> adopted for the KCT project, with their source, year/version and units
> documented in the master data. Do not silently substitute generic
> factors.

------------------------------------------------------------------------

## 2. General Emission Formula

If an emission factor is expressed as **kg CO₂e per activity unit**:

**CO₂e (tCO₂e) = Activity Data × Emission Factor / 1000**

where:

-   Activity Data = consumption/activity quantity
-   Emission Factor = kg CO₂e per unit
-   1000 converts kg CO₂e to tCO₂e

------------------------------------------------------------------------

# 3. Scope 1 --- Petrol

### Petrol consumption

**Petrol Consumption = Σ Petrol Litres**

### Petrol emissions

**Petrol Emissions (tCO₂e) = Petrol Consumption (L) × Petrol EF
(kgCO₂e/L) / 1000**

Units:

-   Consumption: L
-   Emissions: tCO₂e

------------------------------------------------------------------------

# 4. Scope 1 --- Transport Diesel

### Diesel consumption

**Transport Diesel Consumption = Σ Transport Diesel Litres**

### Transport diesel emissions

**Transport Diesel Emissions (tCO₂e) = Transport Diesel Consumption (L)
× Diesel EF (kgCO₂e/L) / 1000**

Units:

-   Consumption: L
-   Emissions: tCO₂e

------------------------------------------------------------------------

# 5. Scope 1 --- Diesel Generator

DG diesel must remain separate from transport diesel for reporting and
dashboard analysis.

### DG consumption

**DG Diesel Consumption = Σ DG Diesel Litres**

### DG emissions

If the same approved diesel factor is applicable:

**DG Emissions (tCO₂e) = DG Diesel Consumption (L) × Diesel EF
(kgCO₂e/L) / 1000**

If the adopted methodology provides a dedicated DG factor:

**DG Emissions (tCO₂e) = DG Diesel Consumption × DG EF / 1000**

------------------------------------------------------------------------

# 6. Total Scope 1

Scope 1 consists of:

-   Petrol
-   Transport diesel
-   DG diesel

**Scope 1 = Petrol Emissions + Transport Diesel Emissions + DG
Emissions**

Unit: **tCO₂e**

------------------------------------------------------------------------

# 7. Scope 2 --- Grid Electricity

### Total grid electricity

If multiple grid connections exist:

**Total Grid Electricity = Electricity₁ + Electricity₂ + ... +
Electricityₙ**

### Scope 2 emissions

**Scope 2 (tCO₂e) = Grid Electricity (kWh) × Grid EF (kgCO₂e/kWh) /
1000**

Units:

-   Electricity: kWh
-   Emissions: tCO₂e

------------------------------------------------------------------------

# 8. Gross GHG Emissions

For the current project scope:

**Gross Emissions = Scope 1 + Scope 2**

Expanded:

**Gross Emissions = Petrol Emissions + Transport Diesel Emissions + DG
Emissions + Grid Electricity Emissions**

Unit: **tCO₂e**

------------------------------------------------------------------------

# 9. Renewable Energy Generation

If renewable energy generation is recorded in kWh:

**Renewable Energy = Σ Renewable Energy Generation (kWh)**

Unit: **kWh**

------------------------------------------------------------------------

# 10. Renewable Energy --- Emissions Avoided

If renewable energy is treated as displacing grid electricity:

**Emissions Avoided (tCO₂e) = Renewable Energy (kWh) × Grid EF
(kgCO₂e/kWh) / 1000**

Preferred dashboard label:

**Emissions Avoided by Renewable Energy**

Avoid presenting this as a formal Scope 2 reduction unless the adopted
reporting methodology explicitly supports that treatment.

------------------------------------------------------------------------

# 11. Net Carbon Indicator

For a dashboard-derived indicator:

**Net Carbon Indicator = Gross Emissions − Renewable Emissions Avoided**

Unit: **tCO₂e**

This should be clearly labelled as a derived dashboard indicator rather
than automatically treating it as the official GHG inventory total.

------------------------------------------------------------------------

# 12. Renewable Energy Share

If renewable and grid electricity represent the same electricity demand
boundary:

**Renewable Share (%) = Renewable Energy / (Renewable Energy + Grid
Electricity) × 100**

Unit: **%**

------------------------------------------------------------------------

# 13. Total Energy Consumption

Do not add litres and kWh directly.

First convert fuels into a common energy unit such as kWh or MJ.

### Electricity

**Electricity Energy = Grid Electricity (kWh)**

### Fuel

If an approved energy-content factor is available:

**Fuel Energy (kWh) = Fuel Consumption (L) × Energy Content Factor
(kWh/L)**

Then:

**Total Energy = Petrol Energy + Transport Diesel Energy + DG Energy +
Electricity Energy**

The conversion factor and its source must be documented.

------------------------------------------------------------------------

# 14. Monthly Consumption

For a selected month:

**Monthly Consumption = Consumption recorded for the selected month**

This applies separately to:

-   Petrol
-   Transport diesel
-   DG diesel
-   Grid electricity
-   Renewable energy

------------------------------------------------------------------------

# 15. Annual Consumption

**Annual Consumption = Σ Monthly Consumption**

For a full year:

**Annual Value = Jan + Feb + Mar + ... + Dec**

Apply separately to each activity category.

------------------------------------------------------------------------

# 16. Monthly Emissions

### Monthly Scope 1

**Monthly Scope 1 = Monthly Petrol Emissions + Monthly Transport Diesel
Emissions + Monthly DG Emissions**

### Monthly Scope 2

**Monthly Scope 2 = Monthly Grid Electricity × Grid EF / 1000**

### Monthly Gross Emissions

**Monthly Gross = Monthly Scope 1 + Monthly Scope 2**

------------------------------------------------------------------------

# 17. Year-on-Year Comparison

For the same month in two years:

**Absolute Change = Current Period Value − Previous Year Same Period
Value**

**Percentage Change = (Current Period Value − Previous Year Same Period
Value) / Previous Year Same Period Value × 100**

Example:

April 2025 vs April 2026.

A negative percentage means the current value is lower.

------------------------------------------------------------------------

# 18. Month-on-Month Comparison

For consecutive months:

**MoM Change = Current Month Value − Previous Month Value**

**MoM % Change = (Current Month Value − Previous Month Value) / Previous
Month Value × 100**

Example:

April 2026 vs March 2026.

------------------------------------------------------------------------

# 19. Year-to-Date (YTD)

If the selected month is April:

**YTD = January + February + March + April**

General formula:

**YTD = Σ Monthly Value from January through Selected Month**

Apply to:

-   Scope 1
-   Scope 2
-   Gross emissions
-   Fuel consumption
-   Electricity consumption
-   Renewable energy
-   Emissions avoided

------------------------------------------------------------------------

# 20. YTD vs Previous Year YTD

**YTD Change = Current YTD − Previous Year YTD**

**YTD % Change = (Current YTD − Previous Year YTD) / Previous Year YTD ×
100**

Example:

**Jan--Apr 2026 vs Jan--Apr 2025**

------------------------------------------------------------------------

# 21. Per-Person Carbon Footprint

If campus population is available:

**Carbon Footprint per Person (tCO₂e/person) = Gross Emissions (tCO₂e) /
Campus Population**

For kg CO₂e/person:

**kgCO₂e/person = Gross Emissions (tCO₂e) × 1000 / Population**

------------------------------------------------------------------------

# 22. Scope 1 Source Contribution

### Petrol contribution

**Petrol Contribution (%) = Petrol Emissions / Scope 1 × 100**

### Transport diesel contribution

**Transport Diesel Contribution (%) = Transport Diesel Emissions / Scope
1 × 100**

### DG contribution

**DG Contribution (%) = DG Emissions / Scope 1 × 100**

These values can feed the Scope 1 / emission-profile donut chart.

------------------------------------------------------------------------

# 23. Scope 1 and Scope 2 Contribution to Gross Emissions

### Scope 1 contribution

**Scope 1 Contribution (%) = Scope 1 / Gross Emissions × 100**

### Scope 2 contribution

**Scope 2 Contribution (%) = Scope 2 / Gross Emissions × 100**

If gross emissions contain only Scope 1 and Scope 2:

**Scope 1 Contribution + Scope 2 Contribution = 100%**

------------------------------------------------------------------------

# 24. Emission Intensity

If total energy has been converted to MWh:

**Emission Intensity (tCO₂e/MWh) = Gross Emissions (tCO₂e) / Total
Energy (MWh)**

This is an advanced KPI and should only be shown when the energy
conversion methodology is documented consistently.

------------------------------------------------------------------------

# 25. Electricity Consumption per Person

**Electricity per Person (kWh/person) = Grid Electricity (kWh) / Campus
Population**

------------------------------------------------------------------------

# 26. Electricity Intensity by Area

If reliable campus/building area data is available:

**Electricity Intensity (kWh/m²) = Electricity Consumption (kWh) / Area
(m²)**

Use this only when the area boundary is clearly defined and consistently
maintained.

------------------------------------------------------------------------

# 27. Consumption Comparison

The same comparison formula can be applied to:

-   Petrol
-   Transport diesel
-   DG diesel
-   Grid electricity
-   Renewable energy
-   Scope 1
-   Scope 2
-   Gross emissions
-   Emissions avoided

**Change = Current Value − Comparison Value**

**Change (%) = (Current Value − Comparison Value) / Comparison Value ×
100**

------------------------------------------------------------------------

# 28. Renewable Avoided Emission Ratio

As a dashboard-derived indicator:

**Avoided Emission Ratio (%) = Renewable Emissions Avoided / Gross
Emissions × 100**

This should be labelled as a derived indicator, not automatically as an
official GHG accounting metric.

------------------------------------------------------------------------

# 29. Latest Complete Reporting Period

This is a data-completeness rule rather than an emissions formula.

**Latest Complete Period = Latest Year/Month for which all required data
categories are available**

Required categories:

-   Transport
-   DG
-   Grid electricity
-   Renewable energy
-   Required emission factors

Example:

If May has missing renewable data but April is complete:

**Latest Complete Period = April 2026**

This prevents incomplete monthly records from being used as the official
comparison period.

------------------------------------------------------------------------

# 30. Dynamic Dashboard Insight Rules

The dashboard can generate statements from calculated changes.

### Decrease

If:

**Change % \< 0**

Display:

> Emissions decreased by X% compared with the comparison period.

### Increase

If:

**Change % \> 0**

Display:

> Emissions increased by X% compared with the comparison period.

### No change

If:

**Change % = 0**

Display:

> Emissions remained unchanged compared with the comparison period.

The same pattern can be applied to:

-   Electricity consumption
-   Petrol consumption
-   Diesel consumption
-   DG consumption
-   Renewable energy
-   Emissions avoided
-   Scope 1
-   Scope 2
-   Gross emissions

------------------------------------------------------------------------

# 31. Recommended Calculation Architecture

Keep the dashboard code separated into four layers:

``` text
Official Excel / CSV
        ↓
data-loader.js
        ↓
calculations.js
        ↓
app.js
        ↓
KPI + Charts + Comparisons + Insights
```

### data-loader.js

Responsible for:

-   Loading Excel/CSV/JSON data
-   Parsing records
-   Validating columns
-   Handling missing values

### calculations.js

Responsible for:

-   Emission factors
-   Scope 1 calculations
-   Scope 2 calculations
-   Renewable avoided emissions
-   Gross emissions
-   Net dashboard indicator
-   Comparisons
-   YTD
-   Contribution percentages
-   Intensity metrics

### app.js

Responsible for:

-   KPI rendering
-   Charts
-   Filters
-   Tables
-   Insight statements
-   User interactions

------------------------------------------------------------------------

# 32. Core Calculation Engine --- Quick Reference

The essential formulas are:

1.  **Petrol CO₂e**\
    Petrol L × Petrol EF / 1000

2.  **Transport Diesel CO₂e**\
    Diesel L × Diesel EF / 1000

3.  **DG CO₂e**\
    DG Diesel L × DG EF / 1000

4.  **Scope 1**\
    Petrol CO₂e + Transport Diesel CO₂e + DG CO₂e

5.  **Scope 2**\
    Grid Electricity kWh × Grid EF / 1000

6.  **Gross Emissions**\
    Scope 1 + Scope 2

7.  **Renewable Avoided Emissions**\
    Renewable kWh × Grid EF / 1000

8.  **Net Carbon Indicator**\
    Gross Emissions − Renewable Avoided Emissions

9.  **Renewable Share**\
    Renewable / (Renewable + Grid) × 100

10. **Per-Person Footprint**\
    Gross Emissions / Population

11. **Absolute Change**\
    Current − Comparison

12. **Percentage Change**\
    (Current − Comparison) / Comparison × 100

13. **YTD**\
    Sum of monthly values from January through selected month

14. **YTD % Change**\
    (Current YTD − Previous YTD) / Previous YTD × 100

15. **Source Contribution %**\
    Source Emissions / Relevant Total Emissions × 100

------------------------------------------------------------------------

# 33. Recommended Master Data Fields

To support these formulas dynamically, the data model should preserve:

-   Year
-   Month
-   Fuel / energy type
-   Consumption
-   Consumption unit
-   Emission factor
-   Emission factor unit
-   Emission factor source/version
-   Department/source
-   Data status
-   Submission date
-   Verification/approval status, if applicable

The dashboard should receive raw official consumption values and
approved factors; calculated values should be generated by the
calculation layer.

------------------------------------------------------------------------

## Final Calculation Flow

``` text
RAW OFFICIAL CONSUMPTION
        │
        ├── Petrol ────────→ Petrol EF ───────→ Petrol CO₂e
        │
        ├── Transport Diesel → Diesel EF ─────→ Diesel CO₂e
        │
        ├── DG Diesel ─────→ DG EF ───────────→ DG CO₂e
        │
        └── Grid Electricity → Grid EF ───────→ Scope 2
                                                  │
Petrol CO₂e + Diesel CO₂e + DG CO₂e ────────────┐ │
                                                ↓ ↓
                                             SCOPE 1 + SCOPE 2
                                                    │
                                                    ↓
                                             GROSS EMISSIONS
                                                    │
Renewable Energy ──→ Grid EF ──→ EMISSIONS AVOIDED
                                                    │
                                                    ↓
                                      NET CARBON INDICATOR
```

**Important implementation rule:** keep emission factors in a separate
`emission_factors` master table with factor value, unit, source,
geography, and effective year/version. This prevents the dashboard from
silently using the wrong factor when your reporting methodology changes.
