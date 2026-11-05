## What and why

<!-- One paragraph: what was wrong or missing, and how this change fixes it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test`
- [ ] `make test-integration` (if the API, the worker, a cache or database code changed)
- [ ] `make test-matrix` (if storage, sealing or Redis code changed)
- [ ] `make e2e` (if a user flow or infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security tf-aws-on-floci` (if Terraform changed)

## Checklist

- [ ] Docs updated (README, `docs/`, configuration reference) for any behavior or config change
- [ ] New Alembic revision instead of editing an applied one
- [ ] Every query stays scoped to the caller's organisation (no cross-tenant read or write)
- [ ] The AI still answers only from the organisation's knowledge, with sources, and escalates otherwise; no sensitive action without a human
- [ ] No new place where customer conversations are sent outside the deployment without the operator choosing a provider
- [ ] `make openapi` run if the API changed
- [ ] No secrets, account ids, real hostnames or em/en dashes (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above
