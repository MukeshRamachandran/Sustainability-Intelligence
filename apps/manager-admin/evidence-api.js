(function () {
  async function request(path, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    return apiRequest(path, {
      ...options,
      method,
      csrf: !['GET', 'HEAD', 'OPTIONS'].includes(method)
    });
  }

  function managerBase(domain, submissionId) {
    return `/api/manager/${encodeURIComponent(domain)}/submissions/${encodeURIComponent(submissionId)}/evidence`;
  }

  async function uploadManager(domain, submissionId, file, attachment, replacesEvidenceId) {
    const body = new FormData();
    body.append('file', file);
    if (attachment.metricCode) body.append('metric_code', attachment.metricCode);
    if (attachment.category) body.append('evidence_category', attachment.category);
    if (replacesEvidenceId) body.append('replaces_evidence_id', replacesEvidenceId);
    return request(managerBase(domain, submissionId), { method: 'POST', body });
  }

  const listManager = (domain, submissionId) => request(managerBase(domain, submissionId));
  const removeManager = (domain, submissionId, evidenceId) => request(
    `${managerBase(domain, submissionId)}/${encodeURIComponent(evidenceId)}`,
    { method: 'DELETE' }
  );
  const listAdmin = submissionId => request(`/api/admin/submissions/${encodeURIComponent(submissionId)}/evidence`);

  function contentUrl(role, domain, evidenceId, download = false) {
    const path = role === 'admin'
      ? `/api/admin/evidence/${encodeURIComponent(evidenceId)}/content`
      : `/api/manager/${encodeURIComponent(domain)}/evidence/${encodeURIComponent(evidenceId)}/content`;
    return window.KCOSMOS_API_URL(`${path}${download ? '?download=true' : ''}`);
  }

  window.KCosmosEvidence = { uploadManager, listManager, removeManager, listAdmin, contentUrl };
})();
