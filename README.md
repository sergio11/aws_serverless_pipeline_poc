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
| 7 | Makefile, scripts, and optional CI | Reproducible command workflow |
| 8 | Hardening: errors, idempotency, logs, docs, memory review | Final acceptance checklist |

## Local Requirements

- Podman
- Terraform
- AWS CLI
- Python
- Git

See [docs/runbook.md](docs/runbook.md) for the current local readiness check and operational notes.

## Current Status

Phase 0 is in progress. The repository has baseline documentation and safe ignore rules. Terraform and AWS CLI still need to be installed or added to `PATH` before infrastructure phases can be fully validated.
