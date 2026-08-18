# AWS Local Cloud Lab POC

Local-first AWS learning lab based on FastAPI, Terraform, Podman, Floci, S3, DynamoDB, SQS, and Lambda-style asynchronous processing.

The goal is to build a reproducible local platform that exercises the same development cycle used in AWS projects:

```text
develop -> containerize -> provision -> run -> test -> observe -> destroy -> rebuild
```

## Implementation Phases

| Phase | Scope | Review gate |
| --- | --- | --- |
| 0 | Project preparation, repository structure, tool checks, baseline docs | Manual review and Gitflow-style commit |
| 1 | Floci container on port 4566 | Smoke test with local endpoint |
| 2 | Terraform modules for S3, DynamoDB, SQS, and DLQ | `terraform plan` and `terraform apply` |
| 3 | FastAPI backend skeleton and REST endpoints | Unit tests and API smoke tests |
| 4 | Backend integration with S3, DynamoDB, and SQS | Integration tests against Floci |
| 5 | Lambda worker or local Lambda-compatible processor | Document status reaches `PROCESSED` |
| 6 | Unit, integration, and end-to-end test suites | Full test suite |
| 7 | Rake tasks and CI | Reproducible command workflow |
| 8 | Hardening: errors, idempotency, logs, docs, memory review | Final acceptance checklist |

## Local Requirements

- Podman
- Terraform
- AWS CLI
- Python
- Git

See [docs/runbook.md](docs/runbook.md) for the current local readiness check and operational notes.

## Current Status

Phase 1 is implemented and pending review. The repository has baseline documentation, safe ignore rules, and a validated Floci Compose service definition. Terraform and AWS CLI still need to be installed or added to `PATH` before infrastructure phases can be fully validated.

## Quick Start

Start the local AWS emulator:

```powershell
rake floci:start
```

Stop it:

```powershell
rake floci:down
```

Provision local AWS-compatible infrastructure:

```powershell
rake infra:plan
rake infra:apply
```

Run backend tests:

```powershell
rake backend:test
```

Start the backend container:

```powershell
rake backend:start
```

Process pending document events once:

```powershell
rake worker:run_once
```

Run all automated tests:

```powershell
rake test
```

Run the same validation used by CI:

```powershell
rake ci
```

Check required local tools:

```powershell
rake doctor
```

Run final hardening verification:

```powershell
rake verify
```

Run acceptance checks:

```powershell
rake acceptance
```

See [docs/acceptance-report.md](docs/acceptance-report.md) for the current acceptance status and remaining tooling gaps.
