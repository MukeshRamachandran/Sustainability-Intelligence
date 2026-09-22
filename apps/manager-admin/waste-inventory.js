(function () {
  'use strict';

  /* Waste dry-material inventory editor.

     The category/material catalog is fetched from the backend and never
     hardcoded here. The table below is an editing buffer only: the governed
     dry and total quantities always come back from the server after a save,
     rendered by calculation-preview.js. */

  if (document.body.dataset.authDomain !== 'waste') return;

  let catalog = { categories: [], materials: [] };
  const items = new Map(); // material_code -> { quantity, material, category }

  const byId = id => document.getElementById(id);
  const notify = (message, type = 'info') =>
    window.KCosmosUI?.notify?.(message, type, { operation: 'Waste inventory' });

  function materialsFor(categoryCode) {
    return catalog.materials.filter(item => item.category_code === categoryCode);
  }

  function categoryOf(materialCode) {
    const material = catalog.materials.find(item => item.code === materialCode);
    if (!material) return null;
    return catalog.categories.find(item => item.code === material.category_code) || null;
  }

  function option(value, label) {
    const node = document.createElement('option');
    node.value = value;
    node.textContent = label;
    return node;
  }

  function renderCategories() {
    const select = byId('waste-category');
    select.replaceChildren(
      option('', 'Select category'),
      ...catalog.categories.map(item => option(item.code, item.display_name))
    );
  }

  function renderMaterials() {
    const categoryCode = byId('waste-category').value;
    const select = byId('waste-material');
    if (!categoryCode) {
      select.replaceChildren(option('', 'Select category first'));
      select.disabled = true;
      return;
    }
    // Cascading: only materials belonging to the chosen category are offered.
    select.replaceChildren(
      option('', 'Select material'),
      ...materialsFor(categoryCode).map(item => option(item.code, item.display_name))
    );
    select.disabled = false;
  }

  function renderItems() {
    const body = byId('waste-items-body');
    if (!items.size) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.className = 'text-muted';
      cell.textContent = 'No dry waste materials added.';
      row.append(cell);
      body.replaceChildren(row);
      return;
    }
    const ordered = [...items.values()].sort((a, b) =>
      (a.category.display_name || '').localeCompare(b.category.display_name || '')
      || (a.material.display_name || '').localeCompare(b.material.display_name || ''));
    body.replaceChildren(...ordered.map(entry => {
      const row = document.createElement('tr');
      const category = document.createElement('td');
      category.textContent = entry.category.display_name;
      const material = document.createElement('td');
      material.textContent = entry.material.display_name;
      const quantity = document.createElement('td');
      quantity.style.textAlign = 'right';
      quantity.textContent = `${Number(entry.quantity).toFixed(2)} kg`;
      const action = document.createElement('td');
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-outline';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => {
        items.delete(entry.material.code);
        renderItems();
        window.KCosmosPreview?.markStale();
      });
      action.append(remove);
      row.append(category, material, quantity, action);
      return row;
    }));
  }

  function addMaterial() {
    const materialCode = byId('waste-material').value;
    const quantityInput = byId('waste-quantity');
    const quantity = Number(quantityInput.value);
    if (!materialCode) {
      notify('Select a category and material first.', 'error');
      return;
    }
    if (!Number.isFinite(quantity) || quantity <= 0) {
      notify('Enter a quantity greater than zero.', 'error');
      return;
    }
    const material = catalog.materials.find(item => item.code === materialCode);
    if (items.has(materialCode)) {
      // Never silently create a second row; the database enforces this too.
      notify(`${material.display_name} has already been added. Edit the existing quantity instead.`, 'error');
      return;
    }
    items.set(materialCode, { quantity, material, category: categoryOf(materialCode) });
    quantityInput.value = '';
    byId('waste-material').value = '';
    renderItems();
    window.KCosmosPreview?.markStale();
  }

  function applyServerItems(submission) {
    items.clear();
    for (const row of submission?.waste?.items || []) {
      items.set(row.material_code, {
        quantity: Number(row.quantity_kg),
        material: { code: row.material_code, display_name: row.material_display_name },
        category: { code: row.category_code, display_name: row.category_display_name }
      });
    }
    renderItems();
  }

  async function loadCatalog() {
    try {
      catalog = await apiRequest('/api/manager/waste/catalog');
      renderCategories();
      renderMaterials();
    } catch (error) {
      notify('Unable to load the waste catalog. Please verify session/API connection.', 'error');
      console.error('[K-COSMOS] Waste catalog failed to load.', {
        status: error?.status ?? null,
        code: error?.code ?? null,
        requestId: error?.requestId ?? null,
        message: error?.message || String(error)
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    byId('waste-category').addEventListener('change', renderMaterials);
    byId('add-material-btn').addEventListener('click', addMaterial);
    byId('wet-waste').addEventListener('input', () => window.KCosmosPreview?.markStale());
    byId('reset-btn')?.addEventListener('click', () => {
      items.clear();
      renderItems();
      window.KCosmosPreview?.markStale();
    });
    renderItems();
    void loadCatalog();
  });

  // The saved server state replaces the editing buffer, so what the Manager
  // sees after a save is exactly what the database holds.
  document.addEventListener('kcosmos:submission-loaded', event => {
    applyServerItems(event.detail.submission);
  });

  window.KCosmosWasteInventory = {
    items: () => [...items.entries()].map(([material_code, entry]) => ({
      material_code,
      quantity_kg: String(entry.quantity)
    })),
    count: () => items.size
  };
})();
