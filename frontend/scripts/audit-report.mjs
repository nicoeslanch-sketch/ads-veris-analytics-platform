// npm exits with 1 for both advisory findings and registry failures.
export function isCompleteAudit(report, status) {
  const findings = report?.vulnerabilities
  const total = report?.metadata?.vulnerabilities?.total
  return report?.auditReportVersion === 2 && !report.error
    && findings !== null && typeof findings === 'object' && !Array.isArray(findings)
    && Number.isSafeInteger(total) && total >= 0 && total === Object.keys(findings).length
    && Object.values(findings).every(item =>
      ['info', 'low', 'moderate', 'high', 'critical'].includes(item?.severity) && Array.isArray(item.via))
    && (status === 0 || (status === 1 && total > 0))
}
