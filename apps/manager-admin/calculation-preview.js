(function () {
  'use strict';

  function resultMap(submission) {
    return new Map((submission?.calculations || []).map(item => [item.calculation_code, item]));
  }

  function display(item) {
    if (!item || item.status !== 'available') return `Unavailable — ${(item?.reason || 'not calculated').replaceAll('_', ' ')}`;
    return `${Number(item.result_value).toFixed(2)} ${item.result_unit}`;
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
      for (const [elementId, calculationCode] of Object.entries(mapping)) {
        const item = results.get(calculationCode);
        document.getElementById(elementId).textContent = display(item);
        if (item?.status === 'available') total += Number(item.result_value); else complete = false;
      }
      document.getElementById('prev-total').textContent = complete ? `${total.toFixed(2)} kgCO2e` : 'Incomplete — unavailable component';
    }
    if (domain === 'energy') {
      document.getElementById('prev-scope2').textContent = display(results.get('grid_electricity_emissions'));
      document.getElementById('prev-avoided').textContent = 'Methodology review required';
    }
    if (domain === 'lpg') {
      const item = results.get('lpg_emissions');
      document.getElementById('prev-factor').textContent = item?.factor_value != null
        ? `${item.factor_value} ${item.factor_unit || 'kgCO2e/kg'} · ${item.factor_set_version || 'governed set'}`
        : 'Not configured';
      document.getElementById('prev-emission').textContent = display(item);
    }
  }

  document.addEventListener('kcosmos:submission-loaded', render);
})();
