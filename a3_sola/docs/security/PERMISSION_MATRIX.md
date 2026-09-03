# Permission matrix

Generated from the doctypes by `a3_sola.api.security.matrix`. It describes what is true, not what was intended.

- Doctypes: **127**
- Roles appearing in them: **29**

## Findings

None. Every rule below holds.

The rules checked:

1. Guest holds nothing outside the published-content allowlist, and cannot write.
2. No customer-facing role has any right on a platform-private doctype.
3. No actual user carries both a tenant stamp and an internal Platform role.
4. Cost and margin fields stay at permlevel 1.
5. Billing, provisioning, lifecycle and admin are separate roles.

## The matrix

| Doctype | Role | Level | Rights |
|---|---|---|---|
| A3 Sola Settings | Platform Admin | permlevel_1 | read, write |
| A3 Sola Settings | System Manager | base | read, write, create, report, export, share, print, email |
| A3 Sola Settings | System Manager | permlevel_1 | read, write |
| Access Suspension | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Access Suspension | Platform Billing Manager | base | read, report, export, share, print, email |
| Access Suspension | Platform Lifecycle Operator | base | read, write, create, submit, cancel, report, export, share, print, email |
| Access Suspension | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Billing Milestone Template | Accounts Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Billing Milestone Template | Solar Accounts Executive | base | read, write, create, submit, report, export, share, print, email |
| Billing Milestone Template | Solar O&M Manager | base | read, report, export, share, print, email |
| Billing Milestone Template | Solar Project Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Billing Milestone Template | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Cancellation Request | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Cancellation Request | Platform Billing Manager | base | read, report, export, share, print, email |
| Cancellation Request | Platform Retention Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Cancellation Request | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Commissioning Report | Accounts Manager | permlevel_2 | read, write |
| Commissioning Report | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Commissioning Report | Solar Documentation Officer | permlevel_2 | read, write |
| Commissioning Report | Solar Liaison Officer | base | read, report, export, share, print, email |
| Commissioning Report | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Commissioning Report | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Commissioning Report | Solar Operations Manager | permlevel_2 | read, write |
| Commissioning Report | Solar QC Inspector | base | read, report, export, share, print, email |
| Commissioning Report | Solar Site Engineer | base | read, report, export, share, print, email |
| Commissioning Report | Solar Technician | base | read, report, export, share, print, email |
| Commissioning Report | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Commissioning Report | System Manager | permlevel_2 | read, write |
| Component Make | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Component Make | Solar Design Engineer | base | read, report, export, share, print, email |
| Component Make | Solar Sales Executive | base | read, report, export, share, print, email |
| Component Make | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Component Make | Solar Survey Engineer | base | read, report, export, share, print, email |
| Component Make | System Manager | base | read, write, create, delete, report, export, share, print, email |
| DISCOM | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| DISCOM | Solar Design Engineer | base | read, report, export, share, print, email |
| DISCOM | Solar Sales Executive | base | read, report, export, share, print, email |
| DISCOM | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| DISCOM | Solar Survey Engineer | base | read, report, export, share, print, email |
| DISCOM | System Manager | base | read, write, create, delete, report, export, share, print, email |
| DISCOM Section | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| DISCOM Section | Solar Design Engineer | base | read, report, export, share, print, email |
| DISCOM Section | Solar Sales Executive | base | read, report, export, share, print, email |
| DISCOM Section | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| DISCOM Section | Solar Survey Engineer | base | read, report, export, share, print, email |
| DISCOM Section | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Demo Request | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Demo Request | Platform Admin | permlevel_1 | read, write |
| Demo Request | Platform Sales | base | read, write, create, submit, report, export, share, print, email |
| Demo Request | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Demo Request | System Manager | permlevel_1 | read, write |
| Document Checklist Template | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Document Checklist Template | Solar Liaison Officer | base | read, report, export, share, print, email |
| Document Checklist Template | Solar Operations Executive | base | read, report, export, share, print, email |
| Document Checklist Template | Solar Operations Manager | base | read, write, create, delete, report, export, share, print, email |
| Document Checklist Template | Solar Site Engineer | base | read, report, export, share, print, email |
| Document Checklist Template | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Document Template Set | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Document Template Set | Solar Liaison Officer | base | read, report, export, share, print, email |
| Document Template Set | Solar Operations Executive | base | read, report, export, share, print, email |
| Document Template Set | Solar Operations Manager | base | read, write, create, delete, report, export, share, print, email |
| Document Template Set | Solar Site Engineer | base | read, report, export, share, print, email |
| Document Template Set | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Dunning Policy | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Dunning Policy | Platform Billing Executive | base | read, report, export, share, print, email |
| Dunning Policy | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Dunning Policy | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Electricity Tariff | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Electricity Tariff | Solar Design Engineer | base | read, report, export, share, print, email |
| Electricity Tariff | Solar Sales Executive | base | read, report, export, share, print, email |
| Electricity Tariff | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Electricity Tariff | Solar Survey Engineer | base | read, report, export, share, print, email |
| Electricity Tariff | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Generation Reading | Solar Accounts Executive | base | read, report, export, share, print, email |
| Generation Reading | Solar O&M Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Generation Reading | Solar Project Manager | base | read, report, export, share, print, email |
| Generation Reading | Solar Service Coordinator | base | read, write, create, submit, report, export, share, print, email |
| Generation Reading | Solar Service Technician | base | read, write, create, submit, report, export, share, print, email |
| Generation Reading | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Grid Regulation Rule | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Grid Regulation Rule | Solar Design Engineer | base | read, report, export, share, print, email |
| Grid Regulation Rule | Solar Sales Executive | base | read, report, export, share, print, email |
| Grid Regulation Rule | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Grid Regulation Rule | Solar Survey Engineer | base | read, report, export, share, print, email |
| Grid Regulation Rule | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Installation Snag | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Installation Snag | Solar Liaison Officer | base | read, report, export, share, print, email |
| Installation Snag | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Installation Snag | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Installation Snag | Solar QC Inspector | base | read, write, create, submit, report, export, share, print, email |
| Installation Snag | Solar Site Engineer | base | read, report, export, share, print, email |
| Installation Snag | Solar Technician | base | read, report, export, share, print, email |
| Installation Snag | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Installation Stage Template | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Installation Stage Template | Solar Liaison Officer | base | read, report, export, share, print, email |
| Installation Stage Template | Solar Operations Executive | base | read, report, export, share, print, email |
| Installation Stage Template | Solar Operations Manager | base | read, write, create, delete, report, export, share, print, email |
| Installation Stage Template | Solar Site Engineer | base | read, report, export, share, print, email |
| Installation Stage Template | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Installation Work Order | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Installation Work Order | Solar Liaison Officer | base | read, report, export, share, print, email |
| Installation Work Order | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Installation Work Order | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Installation Work Order | Solar QC Inspector | base | read, report, export, share, print, email |
| Installation Work Order | Solar Site Engineer | base | read, report, export, share, print, email |
| Installation Work Order | Solar Technician | base | read, write, create, submit, report, export, share, print, email |
| Installation Work Order | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Loan Application | Accounts Manager | permlevel_1 | read, write |
| Loan Application | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Loan Application | Solar Liaison Officer | base | read, report, export, share, print, email |
| Loan Application | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Loan Application | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Loan Application | Solar Operations Manager | permlevel_1 | read, write |
| Loan Application | Solar QC Inspector | base | read, report, export, share, print, email |
| Loan Application | Solar Site Engineer | base | read, report, export, share, print, email |
| Loan Application | Solar Technician | base | read, report, export, share, print, email |
| Loan Application | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Loan Application | System Manager | permlevel_1 | read, write |
| Net Metering Agreement | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Net Metering Agreement | Solar Liaison Officer | base | read, report, export, share, print, email |
| Net Metering Agreement | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Net Metering Agreement | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Net Metering Agreement | Solar QC Inspector | base | read, report, export, share, print, email |
| Net Metering Agreement | Solar Site Engineer | base | read, report, export, share, print, email |
| Net Metering Agreement | Solar Technician | base | read, report, export, share, print, email |
| Net Metering Agreement | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Outreach Message Template | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Outreach Message Template | Solar Sales Executive | base | read, report, export, share, print, email |
| Outreach Message Template | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Outreach Message Template | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Payment Mandate | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Mandate | Platform Billing Executive | base | read, report, export, share, print, email |
| Payment Mandate | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Payment Mandate | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Order | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Order | Platform Billing Executive | base | read, report, export, share, print, email |
| Payment Order | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Payment Order | Platform Sales | base | read, report, export, share, print, email |
| Payment Order | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Refund | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Refund | Platform Billing Executive | base | read, report, export, share, print, email |
| Payment Refund | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Payment Refund | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Transaction | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Transaction | Platform Billing Executive | base | read, report, export, share, print, email |
| Payment Transaction | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Payment Transaction | Platform Sales | base | read, report, export, share, print, email |
| Payment Transaction | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Payment Webhook Log | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Payment Webhook Log | Platform Billing Executive | base | read, report, export, share, print, email |
| Payment Webhook Log | Platform Billing Manager | base | read, write, report, export, share, print, email |
| Payment Webhook Log | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Plan Change Request | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Plan Change Request | Platform Billing Manager | base | read, report, export, share, print, email |
| Plan Change Request | Platform Retention Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Plan Change Request | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Platform Audit Entry | Platform Admin | base | read, report, export, share, print, email |
| Platform Audit Entry | System Manager | base | read, report, export, share, print, email |
| Platform FAQ | Guest | base | read, report, export, share, print, email |
| Platform FAQ | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform FAQ | Platform Marketing Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform FAQ | Platform Sales | base | read, report, export, share, print, email |
| Platform FAQ | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Feature | Guest | base | read, report, export, share, print, email |
| Platform Feature | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform Feature | Platform Marketing Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Feature | Platform Sales | base | read, report, export, share, print, email |
| Platform Feature | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Integration | Guest | base | read, report, export, share, print, email |
| Platform Integration | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform Integration | Platform Marketing Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Integration | Platform Sales | base | read, report, export, share, print, email |
| Platform Integration | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Legal Page | Guest | base | read, report, export, share, print, email |
| Platform Legal Page | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform Legal Page | Platform Marketing Manager | base | read, report, export, share, print, email |
| Platform Legal Page | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Solution | Guest | base | read, report, export, share, print, email |
| Platform Solution | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform Solution | Platform Marketing Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Solution | Platform Sales | base | read, report, export, share, print, email |
| Platform Solution | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Stat | Guest | base | read, report, export, share, print, email |
| Platform Stat | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Platform Stat | Platform Marketing Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Stat | Platform Sales | base | read, report, export, share, print, email |
| Platform Stat | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Platform Subscription | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Platform Subscription | Platform Billing Executive | base | read, report, export, share, print, email |
| Platform Subscription | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Platform Subscription | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Portal Application | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Portal Application | Solar Liaison Officer | base | read, report, export, share, print, email |
| Portal Application | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Portal Application | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Portal Application | Solar QC Inspector | base | read, report, export, share, print, email |
| Portal Application | Solar Site Engineer | base | read, report, export, share, print, email |
| Portal Application | Solar Technician | base | read, report, export, share, print, email |
| Portal Application | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Provisioning Job | Platform Admin | base | read, write, create, submit, cancel, report, export, share, print, email |
| Provisioning Job | Platform Provisioning Operator | base | read, write, submit, report, export, share, print, email |
| Provisioning Job | Platform Tenant Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Provisioning Job | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Roof Type | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Roof Type | Solar Design Engineer | base | read, report, export, share, print, email |
| Roof Type | Solar Sales Executive | base | read, report, export, share, print, email |
| Roof Type | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Roof Type | Solar Survey Engineer | base | read, report, export, share, print, email |
| Roof Type | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Seat Change Request | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Seat Change Request | Platform Billing Manager | base | read, report, export, share, print, email |
| Seat Change Request | Platform Retention Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Seat Change Request | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Service Ticket | Accounts Manager | permlevel_1 | read, write |
| Service Ticket | Solar Accounts Executive | base | read, report, export, share, print, email |
| Service Ticket | Solar Accounts Executive | permlevel_1 | read, write |
| Service Ticket | Solar O&M Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Service Ticket | Solar O&M Manager | permlevel_1 | read, write |
| Service Ticket | Solar Project Manager | base | read, report, export, share, print, email |
| Service Ticket | Solar Project Manager | permlevel_1 | read, write |
| Service Ticket | Solar Service Coordinator | base | read, write, create, submit, report, export, share, print, email |
| Service Ticket | Solar Service Technician | base | read, write, create, submit, report, export, share, print, email |
| Service Ticket | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Service Ticket | System Manager | permlevel_1 | read, write |
| Settlement Reconciliation | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Settlement Reconciliation | Platform Billing Executive | base | read, report, export, share, print, email |
| Settlement Reconciliation | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Settlement Reconciliation | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Site Survey | Solar CRM Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Site Survey | Solar Design Engineer | base | read, report, export, share, print, email |
| Site Survey | Solar Sales Executive | base | read, report, export, share, print, email |
| Site Survey | Solar Sales Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Site Survey | Solar Survey Engineer | base | read, write, create, submit, report, export, share, print, email |
| Site Survey | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Billing Plan | Accounts Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Billing Plan | Accounts Manager | permlevel_1 | read, write |
| Solar Billing Plan | Solar Accounts Executive | base | read, write, create, submit, report, export, share, print, email |
| Solar Billing Plan | Solar Accounts Executive | permlevel_1 | read, write |
| Solar Billing Plan | Solar O&M Manager | base | read, report, export, share, print, email |
| Solar Billing Plan | Solar O&M Manager | permlevel_1 | read, write |
| Solar Billing Plan | Solar Project Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Billing Plan | Solar Project Manager | permlevel_1 | read, write |
| Solar Billing Plan | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Billing Plan | System Manager | permlevel_1 | read, write |
| Solar Consumer | Solar CRM Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Consumer | Solar Design Engineer | base | read, report, export, share, print, email |
| Solar Consumer | Solar Sales Executive | base | read, write, create, submit, report, export, share, print, email |
| Solar Consumer | Solar Sales Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Consumer | Solar Survey Engineer | base | read, report, export, share, print, email |
| Solar Consumer | System Manager | base | read, write, create, delete, cancel, report, export, share, print, email |
| Solar Design Estimate | Solar CRM Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Design Estimate | Solar CRM Manager | permlevel_1 | read, write |
| Solar Design Estimate | Solar Design Engineer | base | read, write, create, submit, report, export, share, print, email |
| Solar Design Estimate | Solar Sales Executive | base | read, report, export, share, print, email |
| Solar Design Estimate | Solar Sales Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Design Estimate | Solar Sales Manager | permlevel_1 | read, write |
| Solar Design Estimate | Solar Survey Engineer | base | read, report, export, share, print, email |
| Solar Design Estimate | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Design Estimate | System Manager | permlevel_1 | read, write |
| Solar Document Template | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Solar Document Template | Solar Liaison Officer | base | read, report, export, share, print, email |
| Solar Document Template | Solar Operations Executive | base | read, report, export, share, print, email |
| Solar Document Template | Solar Operations Manager | base | read, write, create, delete, report, export, share, print, email |
| Solar Document Template | Solar Site Engineer | base | read, report, export, share, print, email |
| Solar Document Template | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Solar GST Valuation Rule | Accounts Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar GST Valuation Rule | Solar Accounts Executive | base | read, write, create, submit, report, export, share, print, email |
| Solar GST Valuation Rule | Solar O&M Manager | base | read, report, export, share, print, email |
| Solar GST Valuation Rule | Solar Project Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar GST Valuation Rule | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Installation | Accounts Manager | permlevel_1 | read, write |
| Solar Installation | Accounts Manager | permlevel_2 | read, write |
| Solar Installation | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Solar Installation | Solar Documentation Officer | permlevel_2 | read, write |
| Solar Installation | Solar Liaison Officer | base | read, report, export, share, print, email |
| Solar Installation | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Solar Installation | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Installation | Solar Operations Manager | permlevel_1 | read, write |
| Solar Installation | Solar Operations Manager | permlevel_2 | read, write |
| Solar Installation | Solar QC Inspector | base | read, report, export, share, print, email |
| Solar Installation | Solar Site Engineer | base | read, report, export, share, print, email |
| Solar Installation | Solar Technician | base | read, report, export, share, print, email |
| Solar Installation | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Installation | System Manager | permlevel_1 | read, write |
| Solar Installation | System Manager | permlevel_2 | read, write |
| Solar OM Contract | Accounts Manager | permlevel_1 | read, write |
| Solar OM Contract | Solar Accounts Executive | base | read, report, export, share, print, email |
| Solar OM Contract | Solar Accounts Executive | permlevel_1 | read, write |
| Solar OM Contract | Solar O&M Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar OM Contract | Solar O&M Manager | permlevel_1 | read, write |
| Solar OM Contract | Solar Project Manager | base | read, report, export, share, print, email |
| Solar OM Contract | Solar Project Manager | permlevel_1 | read, write |
| Solar OM Contract | Solar Service Coordinator | base | read, write, create, submit, report, export, share, print, email |
| Solar OM Contract | Solar Service Technician | base | read, report, export, share, print, email |
| Solar OM Contract | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar OM Contract | System Manager | permlevel_1 | read, write |
| Solar OM Visit | Accounts Manager | permlevel_1 | read, write |
| Solar OM Visit | Solar Accounts Executive | base | read, report, export, share, print, email |
| Solar OM Visit | Solar Accounts Executive | permlevel_1 | read, write |
| Solar OM Visit | Solar O&M Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar OM Visit | Solar O&M Manager | permlevel_1 | read, write |
| Solar OM Visit | Solar Project Manager | base | read, report, export, share, print, email |
| Solar OM Visit | Solar Project Manager | permlevel_1 | read, write |
| Solar OM Visit | Solar Service Coordinator | base | read, write, create, submit, report, export, share, print, email |
| Solar OM Visit | Solar Service Technician | base | read, write, create, submit, report, export, share, print, email |
| Solar OM Visit | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar OM Visit | System Manager | permlevel_1 | read, write |
| Solar Package | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Solar Package | Solar Design Engineer | base | read, report, export, share, print, email |
| Solar Package | Solar Sales Executive | base | read, report, export, share, print, email |
| Solar Package | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Solar Package | Solar Survey Engineer | base | read, report, export, share, print, email |
| Solar Package | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Solar Proposal | Solar CRM Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Proposal | Solar Design Engineer | base | read, report, export, share, print, email |
| Solar Proposal | Solar Sales Executive | base | read, write, create, submit, report, export, share, print, email |
| Solar Proposal | Solar Sales Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Proposal | Solar Survey Engineer | base | read, report, export, share, print, email |
| Solar Proposal | System Manager | base | read, write, create, delete, cancel, report, export, share, print, email |
| Solar Warranty Claim | Accounts Manager | permlevel_1 | read, write |
| Solar Warranty Claim | Solar Accounts Executive | base | read, report, export, share, print, email |
| Solar Warranty Claim | Solar Accounts Executive | permlevel_1 | read, write |
| Solar Warranty Claim | Solar O&M Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Warranty Claim | Solar O&M Manager | permlevel_1 | read, write |
| Solar Warranty Claim | Solar Project Manager | base | read, report, export, share, print, email |
| Solar Warranty Claim | Solar Project Manager | permlevel_1 | read, write |
| Solar Warranty Claim | Solar Service Coordinator | base | read, write, create, submit, report, export, share, print, email |
| Solar Warranty Claim | Solar Service Technician | base | read, report, export, share, print, email |
| Solar Warranty Claim | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Solar Warranty Claim | System Manager | permlevel_1 | read, write |
| Statutory Fee Payment | Accounts Manager | permlevel_1 | read, write |
| Statutory Fee Payment | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Statutory Fee Payment | Solar Liaison Officer | base | read, report, export, share, print, email |
| Statutory Fee Payment | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Statutory Fee Payment | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Statutory Fee Payment | Solar Operations Manager | permlevel_1 | read, write |
| Statutory Fee Payment | Solar QC Inspector | base | read, report, export, share, print, email |
| Statutory Fee Payment | Solar Site Engineer | base | read, report, export, share, print, email |
| Statutory Fee Payment | Solar Technician | base | read, report, export, share, print, email |
| Statutory Fee Payment | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Statutory Fee Payment | System Manager | permlevel_1 | read, write |
| Statutory Fee Recovery | Accounts Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Statutory Fee Recovery | Accounts Manager | permlevel_1 | read, write |
| Statutory Fee Recovery | Solar Accounts Executive | base | read, write, create, submit, report, export, share, print, email |
| Statutory Fee Recovery | Solar Accounts Executive | permlevel_1 | read, write |
| Statutory Fee Recovery | Solar O&M Manager | base | read, report, export, share, print, email |
| Statutory Fee Recovery | Solar O&M Manager | permlevel_1 | read, write |
| Statutory Fee Recovery | Solar Project Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Statutory Fee Recovery | Solar Project Manager | permlevel_1 | read, write |
| Statutory Fee Recovery | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Statutory Fee Recovery | System Manager | permlevel_1 | read, write |
| Statutory Fee Schedule | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Statutory Fee Schedule | Solar Design Engineer | base | read, report, export, share, print, email |
| Statutory Fee Schedule | Solar Sales Executive | base | read, report, export, share, print, email |
| Statutory Fee Schedule | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Statutory Fee Schedule | Solar Survey Engineer | base | read, report, export, share, print, email |
| Statutory Fee Schedule | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Subscription Event | Platform Admin | base | read, create, report, export, share, print, email |
| Subscription Event | Platform Billing Manager | base | read, report, export, print |
| Subscription Event | Platform Lifecycle Operator | base | read, report, export, print |
| Subscription Event | System Manager | base | read, create, report, export, share, print, email |
| Subscription Invoice | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subscription Invoice | Platform Billing Executive | base | read, report, export, share, print, email |
| Subscription Invoice | Platform Billing Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Subscription Invoice | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subscription Plan | Guest | base | read, report, export, share, print, email |
| Subscription Plan | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Subscription Plan | Platform Marketing Manager | base | read, report, export, share, print, email |
| Subscription Plan | Platform Sales | base | read, report, export, share, print, email |
| Subscription Plan | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Subscription Policy | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subscription Policy | Platform Billing Manager | base | read, report, export, share, print, email |
| Subscription Policy | Platform Lifecycle Operator | base | read, report, export, share, print, email |
| Subscription Policy | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subscription Signup | Platform Admin | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subscription Signup | Platform Admin | permlevel_1 | read, write |
| Subscription Signup | Platform Sales | base | read, write, create, submit, report, export, share, print, email |
| Subscription Signup | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Subscription Signup | System Manager | permlevel_1 | read, write |
| Subsidy Claim | Accounts Manager | permlevel_1 | read, write |
| Subsidy Claim | Solar Documentation Officer | base | read, write, create, report, export, share, print, email |
| Subsidy Claim | Solar Liaison Officer | base | read, report, export, share, print, email |
| Subsidy Claim | Solar Operations Executive | base | read, write, create, submit, report, export, share, print, email |
| Subsidy Claim | Solar Operations Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subsidy Claim | Solar Operations Manager | permlevel_1 | read, write |
| Subsidy Claim | Solar QC Inspector | base | read, report, export, share, print, email |
| Subsidy Claim | Solar Site Engineer | base | read, report, export, share, print, email |
| Subsidy Claim | Solar Technician | base | read, report, export, share, print, email |
| Subsidy Claim | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subsidy Claim | System Manager | permlevel_1 | read, write |
| Subsidy Eligibility Check | Solar CRM Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subsidy Eligibility Check | Solar Design Engineer | base | read, write, create, submit, report, export, share, print, email |
| Subsidy Eligibility Check | Solar Sales Executive | base | read, report, export, share, print, email |
| Subsidy Eligibility Check | Solar Sales Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subsidy Eligibility Check | Solar Survey Engineer | base | read, report, export, share, print, email |
| Subsidy Eligibility Check | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Subsidy Scheme | Solar CRM Manager | base | read, write, create, delete, report, export, share, print, email |
| Subsidy Scheme | Solar Design Engineer | base | read, report, export, share, print, email |
| Subsidy Scheme | Solar Sales Executive | base | read, report, export, share, print, email |
| Subsidy Scheme | Solar Sales Manager | base | read, write, create, report, export, share, print, email |
| Subsidy Scheme | Solar Survey Engineer | base | read, report, export, share, print, email |
| Subsidy Scheme | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Tenant | Platform Admin | base | read, write, create, submit, cancel, report, export, share, print, email |
| Tenant | Platform Billing Manager | base | read, report, export, share, print, email |
| Tenant | Platform Provisioning Operator | base | read, report, export, share, print, email |
| Tenant | Platform Tenant Manager | base | read, write, create, submit, cancel, report, export, share, print, email |
| Tenant | System Manager | base | read, write, create, delete, submit, cancel, report, export, share, print, email |
| Tenant Blueprint | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Tenant Blueprint | Platform Tenant Manager | base | read, report, export, share, print, email |
| Tenant Blueprint | System Manager | base | read, write, create, delete, report, export, share, print, email |
| Tenant Invitation | Platform Admin | base | read, write, create, delete, report, export, share, print, email |
| Tenant Invitation | Platform Provisioning Operator | base | read, report, export, share, print, email |
| Tenant Invitation | Platform Tenant Manager | base | read, write, create, delete, report, export, share, print, email |
| Tenant Invitation | System Manager | base | read, write, create, delete, report, export, share, print, email |
