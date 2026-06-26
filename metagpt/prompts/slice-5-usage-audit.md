Extend the existing orchestration backend with usage metering, per-tenant quotas, and an audit trail, plus an admin dashboard. Reuse the UsageRecord/AuditEvent hooks already emitted by generation and admin actions. Do NOT touch the engines beyond existing clients.

Goal: tenant admins can see who generated what and the cost, and quotas are enforced.

Deliver:
1. Metering: aggregate tokens_in/tokens_out and cost_estimate per generation and roll up per user and per tenant for a date range. Cost estimate derived from the tenant's provider/model pricing config.
2. Quotas: tenant.quota_monthly_generations enforced — block or flag generation per policy when exceeded; record the event; emit an alert hook.
3. Audit: ensure every mutating/admin action and every generation writes an AuditEvent (actor, tenant, action, resource + versions, timestamp); expose GET /api/v1/audit?from=&to=.
4. APIs (admin): GET /api/v1/usage?from=&to= (counts, tokens, estimated cost per user and tenant).
5. Frontend (admin): usage dashboard (counts, tokens, cost by user/period) and an audit log view; quota status indicator.
6. Tests (write first): generating several decks produces correct per-user/per-tenant rollups; a tenant at quota is blocked/flagged and the event is recorded.

Constraints: all tenant-scoped; no cross-tenant aggregation; secrets/keys never logged in audit.
