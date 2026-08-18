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
- Terraform (>= 1.8.0)
- AWS CLI
- Python
- Git

## Current Status

**All phases completed.** The repository implements a full local AWS development lifecycle with document management workflow. Terraform provisions local AWS-compatible infrastructure (S3, DynamoDB, SQS) via Floci.

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

## Local Tool Check

| Tool | Status | Notes |
| --- | --- | --- |
| Podman | OK | `podman version 5.8.2` |
| Podman Compose | OK | Validated with `podman-compose -f compose.yaml config` and `up -d floci` |
| Python | OK | `Python 3.14.5` |
| Terraform | Required | >= 1.8.0 |
| AWS CLI | Required | For diagnostics |

All tools must be installed or added to `PATH` before running the full workflow.

## Local AWS Environment

Use dummy credentials only:

```powershell
$env:AWS_ENDPOINT_URL = "http://localhost:4566"
$env:AWS_DEFAULT_REGION = "eu-west-1"
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
```

When services run inside Compose, application containers should use:

```text
AWS_ENDPOINT_URL=http://floci:4566
```

The host should use:

```text
AWS_ENDPOINT_URL=http://localhost:4566
```

## Local Console (UI)

A visual web console for browsing and managing AWS resources:

| Component | URL | Description |
|-----------|-----|-------------|
| Floci UI | http://localhost:4500 | Console Home, Cloud Explorer |

Start the UI:

```powershell
rake ui:start
```

Stop it:

```powershell
rake ui:down
```

Features:
- S3 bucket browser (upload/download/delete objects)
- DynamoDB table viewer (create/scan/delete items)
- SQS queue manager (send/receive/delete messages)
- Lambda function inspector
- CloudWatch log viewer

## Repository Safety

The repository ignores:

- Local environment files.
- Python caches.
- Terraform state.
- Local emulator data.
- Logs and temporary files.

Real AWS credentials must never be committed.

## Architecture

### Services

| Service | Description |
| --- | --- |
| Floci | Local AWS emulator on port 4566 |
| Floci UI | Web console for browsing AWS resources on port 4500 |
| Backend | FastAPI REST API for document management |
| Lambda Worker | SQS polling worker for async processing |
| E2E Tests | End-to-end workflow validation |

### API Endpoints

```text
GET  /health
POST /documents
GET  /documents/{document_id}
GET  /documents/{document_id}/content
```

### AWS Resources (Local)

```text
S3 bucket:      poc-local-documents
DynamoDB table: documents
SQS queue:      document-events
SQS DLQ:        document-events-dlq
```

### Document Workflow

```text
POST /documents
  -> S3 object
  -> DynamoDB metadata
  -> SQS DocumentCreated event
  -> worker processing
  -> DynamoDB status PROCESSED
```

## Testing

Run backend and worker unit/API tests:

```powershell
rake test:unit
```

Run the end-to-end document workflow:

```powershell
rake test:e2e
```

Run all tests:

```powershell
rake test
```

The e2e suite starts Floci, backend, and the polling worker through Rake and verifies that a document reaches `processed`.

## Automation

Rake is the single task entry point for local development and CI.

Check tools:

```powershell
rake doctor
```

Validate Compose:

```powershell
rake compose:config
```

Build all images:

```powershell
rake build
```

Run CI-equivalent validation locally:

```powershell
rake ci
```

## Hardening

Run final verification:

```powershell
rake verify
```

Backend infrastructure failures are returned as explicit HTTP 500 responses and logged as structured JSON events.

Worker logs are structured JSON events and the worker:

- skips already `PROCESSED` documents;
- deletes invalid JSON messages;
- marks failed processing as `FAILED`;
- tolerates the queue not being ready yet during local startup.

## Acceptance

Run acceptance checks:

```powershell
rake acceptance
```

### Acceptance Result

| Area | Status |
| --- | --- |
| Local AWS emulator with Floci | OK |
| Podman Compose topology | OK |
| FastAPI backend | OK |
| S3-compatible document storage | OK |
| DynamoDB-compatible metadata store | OK |
| SQS-compatible event publication | OK |
| Lambda-style worker | OK |
| Unit/API tests | OK |
| End-to-end workflow test | OK |
| Rake automation | OK |
| Structured logs | OK |
| Error handling hardening | OK |
| Worker idempotency | OK |

## License

MIT
