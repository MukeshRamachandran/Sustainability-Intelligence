(function () {
  'use strict';

  /* Sole owner of the Manager "Emission Preview" value nodes.

     Every figure shown here is the backend's governed result for the loaded
     submission.  Entry pages must never write these nodes: typing cannot
     produce an authoritative emission, so a keystroke may only mark the
     preview stale (see markStale), never replace a real server value with
     hardcoded text. */

  const STALE_ID = 'prev-stale';

  /* Fallback only.  The unit actually rendered always comes from the
     backend's result_unit - the API contract is the authority. */
  const DEFAULT_RESULT_UNIT = 'tCO2e';

  function staleNode() {
    return document.getElementById(STALE_ID);
  }

  function setStale(isStale) {
    const node = staleNode();
    if (node) node.hidden = !isStale;
  }

  function resultMap(submission) {
    return new Map((submission?.calculations || []).map(item => [item.calculation_code, item]));
  }

  function display(item) {
    if (!item || item.status !== 'available') return `Unavailable — ${(item?.reason || 'not calculated').replaceAll('_', ' ')}`;
    return `${Number(item.result_value).toFixed(2)} ${item.result_unit || DEFAULT_RESULT_UNIT}`;
  }

  function render(event) {
    const submission = event.detail.submission;
    const results = resultMap(submission);
    const domain = document.body.dataset.authDomain;
    if (domain === 'transport') {
      const mapping = {
        'prev-petrol': 'transport_petrol_emissions',
        'prev-diesel-t': 'transport_diesel_emissions',
        'prev-diesel-dg': 'dg_diesel_emissions'
      };
      let total = 0;
      let complete = true;
      const units = new Set();
      for (const [elementId, calculationCode] of Object.entries(mapping)) {
        const item = results.get(calculationCode);
        document.getElementById(elementId).textContent = display(item);
        if (item?.status === 'available') {
          total += Number(item.result_value);
          units.add(item.result_unit || DEFAULT_RESULT_UNIT);
        } else {
          complete = false;
        }
      }
      /* Components are summed exactly as the backend published them and
         labelled with the backend's own unit.  Nothing is rescaled to fit a
         label, and a mixed-unit payload is reported rather than added up. */
      let totalText;
      if (!complete) totalText = 'Incomplete — unavailable component';
      else if (units.size > 1) totalText = 'Unavailable — mixed result units';
      else totalText = `${total.toFixed(2)} ${units.values().next().value || DEFAULT_RESULT_UNIT}`;
      document.getElementById('prev-total').textContent = totalText;
    }
    if (domain === 'energy') {
      document.getElementById('prev-scope2').textContent = display(results.get('grid_electricity_emissions'));
      document.getElementById('prev-avoided').textContent = 'Methodology review required';
    }
    if (domain === 'waste') {
      /* Waste has no emission factor. These are the backend-calculated
         quantities read straight from the saved submission. */
      const waste = submission?.waste;
      const kg = value => (value === null || value === undefined
        ? 'Unavailable'
        : `${Number(value).toFixed(2)} kg`);
      document.getElementById('prev-dry').textContent = kg(waste?.dry_waste_generated_kg);
      document.getElementById('prev-wet').textContent = kg(waste?.wet_waste_generated_kg);
      document.getElementById('prev-total').textContent = kg(waste?.total_waste_generated_kg);
    }
    if (domain === 'lpg') {
      const item = results.get('lpg_emissions');
      document.getElementById('prev-factor').textContent = item?.factor_value != null
        ? `${item.factor_value} ${item.factor_unit || 'kgCO2e/L'} · ${item.factor_set_version || 'governed set'}`
        : 'Not configured';
      document.getElementById('prev-emission').textContent = display(item);
    }
    setStale(false);
  }

  document.addEventListener('kcosmos:submission-loaded', render);

  /* Entry pages call this when the Manager edits an input, so the preview can
     say it is out of date without destroying the last governed result. */
  window.KCosmosPreview = { markStale: () => setStale(true) };
})();
