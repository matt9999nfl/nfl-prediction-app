# Architecture Decision Records

Each ADR captures a non-trivial decision: what was decided, why, what was considered, and what would prompt revisiting it.

Format:
```
## ADR-NNN — Title
Status: Proposed | Accepted | Superseded by ADR-NNN
Date: YYYY-MM-DD

### Context
What problem are we solving? What constraints exist?

### Decision
What did we decide?

### Alternatives Considered
What else did we look at, and why didn't we pick it?

### Consequences
What follows from this — both positive and negative?

### Revisit If
What would change our minds?
```

---

## ADR-001 — Use existing GCP project `nfl-model-471509`
**Status:** Accepted
**Date:** 2026-05-02

### Context
Existing infrastructure already lives in this project: Cloud Functions, BigQuery datasets, Cloud Storage. Standing up a parallel project would mean migrating data, reissuing credentials, and rebuilding IAM.

### Decision
Build all new components in `nfl-model-471509`. Use dataset and bucket prefixes to keep new work organized.

### Alternatives Considered
- New project for cleanliness — rejected; the cost of migration outweighs the cleanliness benefit at this scale.
- Multi-project (dev/staging/prod) — rejected for v1; premature for a solo project pre-launch.

### Consequences
- Cleaner separation will require dataset-level conventions, not project-level
- IAM is shared, so least-privilege per service account becomes critical (DEVOPS owns)
- Easier to leverage existing pipelines

### Revisit If
- The project becomes a multi-tenant or multi-environment system
- IAM contention or quota issues emerge

---

## ADR-002 — nflfastR / nflverse as primary data spine
**Status:** Accepted
**Date:** 2026-05-02

### Context
PFF was the previously assumed primary source but has been deprioritized: ratings didn't match eye test last season, recent restructuring and negative sentiment make it an unreliable foundation. The project also has portfolio ambitions, which constrain anything `personal_use_only` from public surfaces.

### Decision
nflfastR / nflverse is the primary data source. It is free, open, comprehensive (PBP back to 1999), updated nightly, and carries no licensing constraints for public use. Other sources are evaluated as additive feature inputs.

### Alternatives Considered
- PFF-first — rejected (above)
- SIS-first — rejected; cost and license uncertainty, also commercial-only license tag would limit public surfaces
- Build proprietary data only — rejected; insufficient time budget and no edge in re-creating what nflfastR provides

### Consequences
- Initial backtest can run on a fully open dataset
- Anything in BACKEND-API is publishable by default
- Supplemental sources earn their place via measurable backtest contribution

### Revisit If
- nflfastR coverage degrades or the project goes dark
- A licensed source demonstrates a backtest improvement large enough to justify its cost and licensing constraints

---

## ADR-003 — Cloud Run for the API service
**Status:** Accepted
**Date:** 2026-05-02

### Context
Need to host a FastAPI service with low traffic, low budget, infrequent deploys.

### Decision
Single Cloud Run service, scale-to-zero, Docker container.

### Alternatives Considered
- Cloud Functions (single function per endpoint) — rejected; FastAPI's cohesion is lost
- App Engine — rejected; legacy, fewer Python ergonomics
- GKE — rejected; massive overkill
- VM — rejected; manual ops burden

### Consequences
- Cold start on first request after idle (acceptable for this use case)
- No need to manage infrastructure manually
- Pay only when traffic exists

### Revisit If
- Cold starts become user-visible and unacceptable
- Traffic grows enough that scale-to-zero is no longer the optimal cost shape

---

## ADR-004 — BigQuery as the only data store (no separate OLTP)
**Status:** Accepted
**Date:** 2026-05-02

### Context
The system has no high-frequency writes from end users. All writes are batch (ingest, modeling). Reads from the API are mostly aggregates or specific lookups by ID.

### Decision
BigQuery serves as both the warehouse and the read store for the API. No Postgres / Cloud SQL / Firestore for v1.

### Alternatives Considered
- Cloud SQL for serving + BigQuery for analytics — rejected; double the operational surface, sync complexity, and cost
- Firestore for fast reads — rejected; document model fits poorly, and the API is naturally relational

### Consequences
- API queries must be designed to be cheap — small result sets, partition-aware
- Cost limits per service account become important (DEVOPS owns)
- Materialized views may be needed if a hot query is too expensive

### Revisit If
- A user-facing endpoint needs sub-100ms tail latency that BigQuery can't reliably provide
- Real-time write requirements emerge (live odds, user accounts, etc.)

---

## ADR-005 — Project goal is a comprehensive NFL prediction platform, not an OL hypothesis validator
**Status:** Accepted
**Date:** 2026-05-03

### Context
Phase 1's first backtest (ol_xgb_v1) used only nflfastR-derived OL metrics and returned 48.7% ATS — no meaningful lift over baseline. Post-result review surfaced a more fundamental framing question: the project goal is to build an NFL prediction model app capable of running endless experiments on NFL data to predict future outcomes. The OL hypothesis is the first thesis to test, not the ceiling of what gets tested. A model using only OL features was never going to be the production model.

### Decision
The project is a **general NFL prediction platform**. Phase 1 validation is still required (≥54% ATS, ≥250 games) but the model tested must be a comprehensive predictor using the full available nflfastR feature space — QB efficiency, team offense/defense, situational context, rest/travel, form — with OL metrics as one component. Experiments are identified by `experiment_id`; the OL-only experiment (ol_xgb_v1) is one data point in the experiment log, not the final word on the hypothesis.

### Alternatives Considered
- Continue testing OL-only models with different formulations — rejected; if OL metrics alone aren't enough signal, adding more OL features is unlikely to clear the gate. The right move is a complete feature set.
- Abandon nflfastR and move to licensed data sources first — rejected; the data foundation is sound and nflfastR contains substantial signal beyond OL metrics that hasn't been tested yet.

### Consequences
- MODELING_SPEC_PHASE1.md is updated to specify a comprehensive nflfastR feature set
- The experiment log (`experiments.backtest_runs`) is the right place to track multiple model versions over time — the architecture supports this without changes
- OL features remain in the model; their importance relative to other features is now an output of the model, not a constraint going in
- Future supplemental sources (FTN, NGS, SIS) earn their place by improving on the comprehensive nflfastR baseline, not the OL-only baseline

### Revisit If
- The comprehensive nflfastR model also fails to clear the gate — at that point the question becomes whether nflfastR alone has enough signal, and licensed data sources become the next test

---

## ADR-007 — Self-service experimentation platform with form-based upload and future Claude API schema inference
**Status:** Accepted
**Date:** 2026-05-03

### Context
The project vision is a platform where new datasets can be uploaded through the dashboard, experiments configured through a UI form (target variable, features, evaluation criteria), run on demand, and results viewed in the dashboard — without writing code per experiment. Long-term, dataset schema mapping should be AI-assisted via the Claude API: upload a file, Claude infers column meanings and join keys, user confirms.

### Decision
The architecture is redesigned around a dataset registry, a config-driven experiment runner, and a read/write API. Phase 1 of data upload uses a form-based schema mapping flow. Phase 2 adds Claude API-assisted inference as an enhancement to the same upload endpoint. The API contracts are updated to include dataset upload, schema mapping, experiment creation, experiment triggering, and framework CRUD endpoints. ARCHITECTURE.md and API_CONTRACTS.md are the authoritative specs.

### Alternatives Considered
- Code-driven per-experiment (current approach) — rejected; requires dev work for every new dataset or experiment, does not match the platform vision
- Fully automated schema inference without user review — rejected; Claude inference has uncertainty, user confirmation prevents bad joins from corrupting experiments

### Consequences
- BACKEND-API scope expands significantly: now a read/write API with async job triggering
- MODELING layer must be refactored into a config-driven runner that accepts JSON configs, not hardcoded feature lists
- FRONTEND scope expands: upload flow, experiment builder UI, results viewer, framework manager
- Claude API integration is scoped to one place (upload schema inference) — clean extension point, no architectural sprawl

### Revisit If
- Multi-user requirements emerge (accounts, permissions, dataset sharing)
- Experiment complexity grows beyond what JSON config can express (custom loss functions, complex feature transforms)

---

## ADR-009 — model.type uses abstract type names in the API contract; runner resolves to concrete implementations
**Status:** Accepted
**Date:** 2026-05-06

### Context
`platform.experiment_configs.model.type` is written by BACKEND-API and read by the Experiment Runner. BACKEND-API validates against abstract type names (`"xgboost"`, `"logistic_regression"`, `"random_forest"`) as specified in `API_CONTRACTS.md`. The runner's MODEL_REGISTRY was implemented using internal version identifiers (`"ol_xgb_v1"`, `"ol_xgb_v2"`). These can't both be the source of truth.

### Decision
The API contract type names are canonical. `model.type` in any stored config is always one of `"xgboost" | "logistic_regression" | "random_forest"`. The runner's MODEL_REGISTRY maps abstract names to concrete implementations: `"xgboost"` → `OLXGBModelV2` (current best). Internal version identifiers (`"ol_xgb_v1"`, `"ol_xgb_v2"`) are kept in the registry only for backward compat with Phase 1 historical configs already in BigQuery. No new configs should use them.

### Alternatives Considered
- Use internal version IDs in the API contract — rejected; leaks implementation details into the public-facing schema, couples FRONTEND to MODELING's internal versioning.
- Map abstract → concrete in BACKEND-API before storing — rejected; the runner owns model selection; the API should not know which concrete implementation corresponds to "xgboost".

### Consequences
- MODELING must add `"xgboost"` (and future `"logistic_regression"`, `"random_forest"`) to MODEL_REGISTRY before `run_experiment.py` is used with a FRONTEND-created config.
- When MODELING ships a better XGBoost implementation, they update the `"xgboost"` entry in MODEL_REGISTRY — no API or frontend changes needed.
- BACKEND-API validates `model.type` against the abstract enum at `POST /api/v1/experiments` time.

### Revisit If
- Different users need to pin to a specific model version — at that point, version selection belongs in the config schema.

---

## ADR-008 — FastAPI BackgroundTasks for async processing in Phase 2 (swap to Cloud Run Jobs in Phase 3)
**Status:** Accepted
**Date:** 2026-05-04

### Context
Two Phase 2 BACKEND-API flows need async processing: dataset upload (parse file → load to BigQuery → compute stats) and experiment run triggering. The original spec mentioned "Cloud Run Job or async task" as options. DEVOPS infrastructure for Cloud Run Jobs is explicitly out of scope until Phase 3.

### Decision
Use FastAPI `BackgroundTasks` for all async work in Phase 2. The async logic is isolated in plain functions (`process_upload_background`, `trigger_experiment_runner_stub`) that are called from routers but have no FastAPI coupling. Swapping them for Cloud Run Job triggers in Phase 3 requires changing one call site per function — no router changes, no schema changes.

### Alternatives Considered
- Cloud Run Jobs now — rejected; DEVOPS infra not available in Phase 2, and the added complexity isn't justified for a single-user tool pre-deployment.
- Celery / task queue — rejected; overkill for this scale, adds an external dependency.

### Consequences
- During Phase 2, async tasks run in-process and die if the API pod restarts mid-task. Acceptable for a single-user dev tool; not acceptable in production.
- DEVOPS must swap `process_upload_background` for a Cloud Run Job trigger in Phase 3. The function signature and behavior are the contract — the job receives `dataset_id` and handles the rest.
- MODELING's experiment runner is already designed as a Cloud Run Job that reads `experiment_id` from an env var — the trigger stub just needs to fire that job.

### Revisit If
- A dataset upload fails silently due to a pod restart before Phase 3 — if this happens in dev, move the swap earlier.

---

## ADR-010 — Terraform for infrastructure-as-code
**Status:** Accepted
**Date:** 2026-05-06

### Context
DEVOPS must provision Cloud Run services, Cloud Run Jobs, Cloud Scheduler entries, Secret Manager secrets, IAM service accounts, Cloud Storage buckets, Cloud CDN, Cloud Monitoring alert policies, and a billing budget. The instructions require this to be in version control and reproducible. The two options on the table are Terraform (declarative, stateful) and gcloud CLI scripts (imperative, stateless).

### Decision
Use **Terraform** with the `hashicorp/google` provider. All infrastructure is declared in `05-DEVOPS/infra/terraform/`. A `terraform apply` from a clean checkout must be able to recreate the full production environment from scratch. State is stored in a GCS backend (`gs://nfl-model-471509-tfstate/`).

### Alternatives Considered
- **gcloud CLI scripts** — faster to write the first time, but stateless. There is no drift detection: if a resource is manually changed or deleted, scripts won't catch it. Re-running a script requires careful idempotency engineering (checking existence before every `gcloud` call). For a growing set of resources, this becomes fragile.
- **Terraform** — adds a one-time setup cost (GCS backend, service account for CI) and requires learning HCL if not already known. But drift detection, plan/apply workflow, and a single `terraform destroy` for full teardown are worth it for a system with scheduled jobs, IAM bindings, and budget alerts that must stay consistent.
- **Pulumi** — rejected; no meaningful advantage over Terraform here and adds a runtime dependency.

### Consequences
- `05-DEVOPS/infra/terraform/` is the single source of truth for all provisioned resources
- A `terraform plan` in CI on every PR will catch unplanned drift
- No manual `gcloud` changes in production without a corresponding `.tf` commit
- GCS backend bucket (`nfl-model-471509-tfstate`) must be created once manually before `terraform init` can run — document in `05-DEVOPS/runbooks/terraform-bootstrap.md`
- CI (GitHub Actions) needs a Workload Identity Federation binding or a service account key in Secret Manager to run `terraform apply`

### Revisit If
- The infrastructure grows complex enough that Terraform state becomes a bottleneck (multiple engineers, frequent parallel changes) — at that point, Terragrunt or a workspace split would be evaluated

---

## ADR-011 — The platform is the product: no hypothesis testing in Claude
**Status:** Accepted  
**Date:** 2026-05-17

### Context
During Phase 4, a result from the app (58–61% ATS hit rate on rushing features) was brought to PROJECT-LEAD for investigation. The correct investigation — verifying whether the platform was producing correct results — was valid and necessary. However, after confirming the platform had a data bug (INC-001) and fixing it, the session continued into running new experiments directly in Claude (situational filtering: divisional games, late-season games) using standalone Python scripts outside the platform. This consumed significant effort and produced results with no lasting value — the experiments can't be viewed in the app, can't be shared, can't be reproduced by the user, and don't contribute to the platform. The project owner correctly identified this as a scope failure.

### Decision
**Experiments are run through the platform. Claude is used to build the platform, not to run experiments on it.**

When the project owner brings an app result, there are exactly two questions:
1. Is this a genuine edge?
2. Is the app malfunctioning?

Question 2 is always answered first. If the app is malfunctioning, the fix goes into the platform — the corrected code, the rebuilt data, the new validation gate. Question 1 is then answered by the project owner running the corrected experiment through the app themselves.

Claude agents must not: run backtests via standalone Python scripts, engage MODELING to test hypotheses in chat, or produce experiment results that exist only in the conversation and not in the platform. The only exceptions are infrastructure validation runs (faithfulness checks, shuffle-label tests) that are specifically testing whether the runner itself is working — these are platform validation, not hypothesis testing.

### Alternatives Considered
- **Continue running experiments in Claude for speed** — rejected. Speed is illusory: the results can't be used, shared, or reproduced. Every experiment run in Claude is work that didn't contribute to the platform and will need to be re-run through the app anyway.
- **Use Claude for experiments, build the display later** — rejected. This separates the investigation from the tool the user is building and reinforces a workflow where the platform is optional rather than central.

### Consequences
- When a user brings an implausible result, PROJECT-LEAD investigates the platform's correctness (data, labels, runner faithfulness) — not the hypothesis.
- If investigation tooling doesn't exist in the platform to diagnose a result (e.g., no spread-bin diagnostic endpoint, no per-fold UI), the next build task is to add that tooling to the platform.
- MODELING's instruction file is updated: all experiments go through the platform; standalone runners are for infrastructure validation only.
- PROJECT-LEAD's SOP is updated: when reviewing a result, spec the platform feature that enables investigation before running any investigation in Claude.

### Revisit If
- A specific technical investigation requires data manipulation that the platform genuinely cannot support even after reasonable build effort — in that case, file an explicit exception with PROJECT-LEAD sign-off and document it as a one-time diagnostic, not a workflow.

---

## ADR-006 — Experiment gates are per-experiment, not project-level gates
**Status:** Accepted
**Date:** 2026-05-03

### Context
Phase 1 was originally designed around a single hard gate (≥54% ATS on ≥250 games) that had to be cleared before Phase 2 could begin. After two clean experiments, it became clear this was the wrong framing for a platform project. The project goal is a scalable modeling platform for running endless experiments — different experiments will have different success criteria (ATS threshold, log-loss, sample size, specific subset hit rate, etc.). A single hardcoded project-level gate does not fit this model.

### Decision
Experiment gates are defined per experiment, not per project phase. When an experiment is registered in `experiments.backtest_runs`, it carries its own success criteria as metadata. The platform infrastructure being functional and validated is what completes Phase 1 — not any individual model result. Phase 2 (service layer) proceeds when the foundation is working, which it is.

### Alternatives Considered
- Keep the 54% gate and keep iterating models until it clears — rejected; this blocks platform development indefinitely and conflates infrastructure validation with model performance, which are separate concerns.
- No gates at all — rejected; experiment-level gates still make sense for deciding when to surface predictions to users or act on them. They just belong on the experiment, not on the project phase.

### Consequences
- `experiments.backtest_runs` should include a `success_criteria` JSON field (threshold type, threshold value, minimum sample) so each experiment is self-describing
- Phase 1 is complete as of 2026-05-03 — data pipeline validated, experiment framework running, two baseline experiments logged
- Phase 2 is unlocked — BACKEND-API and FRONTEND proceed
- Model iteration continues in parallel with Phase 2 as the platform evolves; a model clearing its own defined gate is what makes predictions suitable for public surfacing
