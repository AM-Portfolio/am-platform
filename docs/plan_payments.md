# AM Payments — Implementation Plan

## Background
The `am-payments` service abstracts payment processing for the platform, targeting an enterprise-level B2B and B2C billing engine.

## Repo Location
`am-platform/am-payments`

## Tech Stack
Python 3.11+, FastAPI, SQLAlchemy (PostgreSQL), aiokafka, Stripe Python SDK.

## Responsibilities & Features (Enterprise Level)
- **Multi-Gateway Abstraction:** Anti-Corruption Layer using an `IPaymentGateway` interface (e.g., Stripe, PayPal, Manual Wire Transfer).
- **Enterprise Invoicing (B2B):** Support for generating enterprise invoices, handling Net-30/Net-60 payment terms, and manual reconciliation for institutional wire transfers.
- **Proration & Metered Billing:** Handle complex billing scenarios including prorated charges for mid-cycle upgrades, seat additions, and end-of-month overage billing (integrating with `am-subscription` meters).
- **Tax & Compliance:** Integration with tax calculation engines (e.g., Stripe Tax) for VAT/Sales Tax handling across different geographic jurisdictions.
- **Payment Methods Vault:** Securely tokenize and store payment methods (Credit Cards, ACH/SEPA direct debits).
- **Dunning & Retry Logic:** Smart automated retries for failed payments and dunning management (triggering reminder emails via `am-notification` before suspending service).
- **Audit Logging:** Strict financial audit trails and immutable ledger of all financial transactions for accounting reconciliation.

## API Endpoints
```
POST   /payments/checkout               — Create Stripe checkout session for B2C/self-serve
POST   /payments/invoices               — Generate an enterprise B2B invoice manually
GET    /payments/invoices               — List all invoices (filtered by user/org)
POST   /payments/invoices/{id}/pay      — Pay a specific invoice
POST   /payments/webhook/stripe         — Stripe webhook receiver (e.g., invoice.paid, charge.failed)
GET    /payments/methods                — List saved payment methods
POST   /payments/methods/setup          — Setup intent for adding a new card/bank account
GET    /payments/ledger/me              — User's immutable financial transaction history
```
