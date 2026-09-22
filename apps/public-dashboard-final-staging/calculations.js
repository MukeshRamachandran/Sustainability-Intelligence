/* =====================================================================
   MICROCOSM - DASHBOARD CALCULATION ENGINE (calculations.js)
   Single source of truth for every formula used by the dashboard.
   Every function here is a direct, literal implementation of a formula
   from Kumaraguru_Institution_Sustainability_Dashboard_Calculation_Formulas.md - the
   section number is noted on each one so it can be diffed against that
   doc directly. Pure functions only (no fetch, no DOM, no globals):
   given the same inputs they always return the same output.

   Consumers:
   - data-loader.js calls the "activity -> emissions" and "rollup"
     functions while building the per-year monthly arrays.
   - app.js calls the "derived KPI" functions (gross/net/contribution/
     comparison/etc.) when it renders KPI cards, the hero balance card
     and the charts, instead of recomputing the arithmetic inline.

   Must be loaded BEFORE data-loader.js and app.js (see index.html).
   ===================================================================== */
(function(){

  /* ---------------------------------------------------------------
     1. General emission formula - Doc §2
     CO2e (tCO2e) = Activity Data x Emission Factor / 1000
     Used for petrol (§3), transport diesel (§4), DG diesel (§5),
     grid electricity (§7) and renewable-avoided emissions (§10) -
     they all share this one shape, just with a different activity
     quantity and a different emission factor.
     Null activity (no reading for that month) passes through as null
     rather than being treated as a zero reading.
     --------------------------------------------------------------- */
  function co2e(activityQty, emissionFactor){
    return activityQty == null ? null : activityQty * emissionFactor / 1000;
  }

  /* ---------------------------------------------------------------
     2. Scope 1 total - Doc §6
     Scope 1 = Petrol Emissions + Transport Diesel Emissions + DG Emissions
     --------------------------------------------------------------- */
  function scope1Total(petrolEmissions, transportDieselEmissions, dgEmissions, lpgEmissions){
    return n(petrolEmissions) + n(transportDieselEmissions) + n(dgEmissions) + n(lpgEmissions);
  }

  /* ---------------------------------------------------------------
     3. Scope 2 - Doc §7
     Total Grid Electricity = Electricity_1 + Electricity_2 + ... + Electricity_n
     Scope 2 (tCO2e) = Grid Electricity (kWh) x Grid EF (kgCO2e/kWh) / 1000
     The dashboard has three connections (HT / Commercial / Temporary).
     Summing their individually-converted emissions is equivalent to
     converting the summed kWh once (same EF applies to all three), and
     keeping them separate lets the KPI cards/charts show each
     connection's own emissions too.
     --------------------------------------------------------------- */
  function totalGridElectricity(...connectionKwh){
    return connectionKwh.reduce((a, v) => a + n(v), 0);
  }
  function scope2Total(...connectionEmissions){
    return connectionEmissions.reduce((a, v) => a + n(v), 0);
  }

  /* ---------------------------------------------------------------
     4. Gross GHG emissions - Doc §8
     Gross Emissions = Scope 1 + Scope 2
     --------------------------------------------------------------- */
  function grossEmissions(scope1, scope2){
    return n(scope1) + n(scope2);
  }

  /* ---------------------------------------------------------------
     5. Renewable energy generation - Doc §9
     Renewable Energy = Sum of Renewable Energy Generation (kWh)
     --------------------------------------------------------------- */
  function totalRenewableEnergy(...renewableKwh){
    return renewableKwh.reduce((a, v) => a + n(v), 0);
  }

  /* ---------------------------------------------------------------
     6. Renewable energy - emissions avoided - Doc §10
     Emissions Avoided (tCO2e) = Renewable Energy (kWh) x Grid EF (kgCO2e/kWh) / 1000
     Same shape as co2e(), named separately so it reads as its own
     line item wherever it's used (per the doc's labeling note: this is
     "Emissions Avoided by Renewable Energy", not a formal Scope 2 cut).
     --------------------------------------------------------------- */
  function renewableAvoidedEmissions(renewableKwh, gridEmissionFactor){
    return co2e(renewableKwh, gridEmissionFactor);
  }

  /* ---------------------------------------------------------------
     7. Net carbon indicator - Doc §11
     Net Carbon Indicator = Gross Emissions - Renewable Emissions Avoided
     A derived dashboard indicator, not the official GHG inventory total.
     --------------------------------------------------------------- */
  function netCarbonIndicator(grossEmissionsVal, renewableEmissionsAvoided){
    return n(grossEmissionsVal) - n(renewableEmissionsAvoided);
  }

  /* ---------------------------------------------------------------
     8. Renewable energy share - Doc §12
     Renewable Share (%) = Renewable Energy / (Renewable Energy + Grid Electricity) x 100
     Returns null (not 0) when there is no electricity demand at all,
     since a 0% share would misleadingly imply "100% grid".
     --------------------------------------------------------------- */
  function renewableShare(renewableEnergyKwh, gridElectricityKwh){
    const total = n(renewableEnergyKwh) + n(gridElectricityKwh);
    return total ? (n(renewableEnergyKwh) / total * 100) : null;
  }

  /* ---------------------------------------------------------------
     9. Total energy consumption - Doc §13
     Fuel Energy (kWh) = Fuel Consumption (L) x Energy Content Factor (kWh/L)
     Total Energy = Petrol Energy + Transport Diesel Energy + DG Energy + Electricity Energy
     NOT currently wired into the dashboard: no approved energy-content
     factor (kWh per litre of petrol/diesel) exists yet in
     data/emission_factors.csv, so fuel litres are never folded into an
     energy total today (data-loader.js's totalEnergy is grid+RE kWh
     only). These two functions are here ready to use once that factor
     is added to the master data - do not guess a factor value.
     --------------------------------------------------------------- */
  function fuelEnergy(fuelLitres, energyContentFactorKwhPerLitre){
    return (fuelLitres == null || energyContentFactorKwhPerLitre == null)
      ? null : fuelLitres * energyContentFactorKwhPerLitre;
  }
  function totalEnergy(electricityEnergyKwh, fuelEnergyKwh){
    return n(electricityEnergyKwh) + n(fuelEnergyKwh);
  }

  /* ---------------------------------------------------------------
     10. Annual / YTD consumption rollups - Doc §15, §19
     Annual Consumption = Sum of Monthly Consumption (Jan..Dec)
     YTD = Sum of Monthly Value from January through the selected month
     Both are the same "sum a monthly array up to some month" operation;
     annualConsumption is just ytdSum with throughMonthIndex = 11 (Dec).
     Null months (no reading yet) count as 0, matching how the
     dashboard treats a missing reading as "nothing recorded so far".
     --------------------------------------------------------------- */
  function ytdSum(monthlyArr, throughMonthIndex = 11){
    return monthlyArr.slice(0, throughMonthIndex + 1).reduce((a, v) => a + n(v), 0);
  }
  function annualConsumption(monthlyArr){
    return ytdSum(monthlyArr, 11);
  }

  /* ---------------------------------------------------------------
     11. Comparisons - Doc §17 (YoY), §18 (MoM), §20 (YTD vs prev YTD),
     §27 (general consumption comparison). All four sections define the
     exact same pair of formulas, just against a different baseline
     period (previous year same month / previous month / previous
     year's YTD / an arbitrary comparison value):
     Absolute Change = Current Value - Comparison Value
     Change (%) = (Current Value - Comparison Value) / Comparison Value x 100
     percentageChange returns 0 (not null/NaN) when there is no usable
     baseline, matching the dashboard's existing "no comparison yet"
     behaviour for a brand new metric/period.
     --------------------------------------------------------------- */
  function absoluteChange(currentValue, comparisonValue){
    return n(currentValue) - n(comparisonValue);
  }
  function percentageChange(currentValue, comparisonValue){
    return comparisonValue ? ((currentValue - comparisonValue) / comparisonValue * 100) : 0;
  }

  /* ---------------------------------------------------------------
     12. Per-person carbon footprint - Doc §21
     Carbon Footprint per Person (tCO2e/person) = Gross Emissions / Campus Population
     kgCO2e/person = Gross Emissions (tCO2e) x 1000 / Population
     Returns null with no population figure rather than 0/Infinity.
     --------------------------------------------------------------- */
  function perPersonFootprint(grossEmissionsVal, population){
    return population ? (n(grossEmissionsVal) / population) : null;
  }
  function perPersonFootprintKg(grossEmissionsVal, population){
    return population ? (n(grossEmissionsVal) * 1000 / population) : null;
  }

  /* ---------------------------------------------------------------
     13. Scope 1 source contribution - Doc §22
     Petrol/Transport Diesel/DG Contribution (%) = Source Emissions / Scope 1 x 100
     Feeds the Scope 1 emission-profile donut chart described in the doc.
     Not currently rendered as its own KPI in app.js (only the absolute
     tCO2e values are shown) - ready to use once/if that KPI is added.
     --------------------------------------------------------------- */
  function scope1SourceContributionPct(sourceEmissions, scope1Emissions){
    return scope1Emissions ? (n(sourceEmissions) / scope1Emissions * 100) : 0;
  }

  /* ---------------------------------------------------------------
     14. Scope contribution to gross emissions - Doc §23
     Scope 1/2 Contribution (%) = Scope 1/2 / Gross Emissions x 100
     (With only Scope 1 + Scope 2 in gross, the two contributions sum
     to 100% by construction.)
     --------------------------------------------------------------- */
  function scopeContributionPct(scopeEmissions, grossEmissionsVal){
    return grossEmissionsVal ? (n(scopeEmissions) / grossEmissionsVal * 100) : 0;
  }

  /* ---------------------------------------------------------------
     15. Emission intensity - Doc §24
     Emission Intensity (tCO2e/MWh) = Gross Emissions (tCO2e) / Total Energy (MWh)
     An advanced KPI, only meaningful once Total Energy (Doc §13) is
     computed on a consistent, documented fuel-conversion basis. Not
     wired into app.js yet - see the totalEnergy()/fuelEnergy() note above.
     --------------------------------------------------------------- */
  function emissionIntensity(grossEmissionsVal, totalEnergyMWh){
    return totalEnergyMWh ? (n(grossEmissionsVal) / totalEnergyMWh) : null;
  }

  /* ---------------------------------------------------------------
     16. Electricity consumption per person - Doc §25
     Electricity per Person (kWh/person) = Grid Electricity (kWh) / Campus Population
     Not currently rendered in app.js.
     --------------------------------------------------------------- */
  function electricityPerPerson(gridElectricityKwh, population){
    return population ? (n(gridElectricityKwh) / population) : null;
  }

  /* ---------------------------------------------------------------
     17. Electricity intensity by area - Doc §26
     Electricity Intensity (kWh/m^2) = Electricity Consumption (kWh) / Area (m^2)
     Not implemented anywhere in the dashboard today - no campus/
     building area master data exists yet. Ready to use once it does.
     --------------------------------------------------------------- */
  function electricityIntensityByArea(electricityKwh, areaM2){
    return areaM2 ? (n(electricityKwh) / areaM2) : null;
  }

  /* ---------------------------------------------------------------
     18. Renewable avoided emission ratio - Doc §28
     Avoided Emission Ratio (%) = Renewable Emissions Avoided / Gross Emissions x 100
     A derived dashboard indicator, not an official GHG accounting metric.
     --------------------------------------------------------------- */
  function renewableAvoidedRatio(renewableEmissionsAvoided, grossEmissionsVal){
    return grossEmissionsVal ? (n(renewableEmissionsAvoided) / grossEmissionsVal * 100) : 0;
  }

  /* ---------------------------------------------------------------
     19. Dynamic dashboard insight rule - Doc §30
     Change % < 0  -> "... decreased by X% ..."
     Change % > 0  -> "... increased by X% ..."
     Change % = 0  -> "... remained unchanged ..."
     Returns the direction only; app.js/walkthrough.js own the actual
     card copy and "good/bad" colour choice (which also depends on
     whether a decrease is desirable for that particular metric).
     --------------------------------------------------------------- */
  function insightDirection(changePct){
    if(changePct < 0) return 'decrease';
    if(changePct > 0) return 'increase';
    return 'no-change';
  }

  /* ---------------------------------------------------------------
     Dashboard-derived ratios that are NOT named formulas in the
     reference doc, but are still real calculations the dashboard
     performs (e.g. "Scope 2 offset", "Grid dependency", "RE vs grid
     ratio" on the Renewable page). Routed through the same two safe-
     division helpers so every piece of arithmetic in the app lives in
     this file, not just the ones the doc happens to name.
     --------------------------------------------------------------- */
  function safeRatioPct(numerator, denominator){
    return denominator ? (n(numerator) / denominator * 100) : 0;
  }
  function safeRatio(numerator, denominator){
    return denominator ? (n(numerator) / denominator) : 0;
  }

  /* Null/NaN-safe number coercion, mirroring the same helper every
     other file in this project defines locally (data-loader.js, app.js). */
  function n(v){ return v == null || Number.isNaN(+v) ? 0 : +v; }

  window.Calculations = {
    co2e,
    scope1Total,
    totalGridElectricity,
    scope2Total,
    grossEmissions,
    totalRenewableEnergy,
    renewableAvoidedEmissions,
    netCarbonIndicator,
    renewableShare,
    fuelEnergy,
    totalEnergy,
    ytdSum,
    annualConsumption,
    absoluteChange,
    percentageChange,
    perPersonFootprint,
    perPersonFootprintKg,
    scope1SourceContributionPct,
    scopeContributionPct,
    emissionIntensity,
    electricityPerPerson,
    electricityIntensityByArea,
    renewableAvoidedRatio,
    insightDirection,
    safeRatioPct,
    safeRatio
  };
})();
