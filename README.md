# FinOps Project — CloudSweep & Cost Detective Audit

This repository hosts two related deliverables:

1. **CloudSweep** — a production-grade, event-driven AWS cloud-waste auto-remediator (scanners, Step Functions orchestration, Slack approval, anomaly detection, Terraform-managed infrastructure).
2. **Cost Detective Audit** — a sandbox-scoped FinOps lab that uses CloudSweep plus additional opt-in modules to demonstrate identification of waste, active cost controls, tagging governance, and a Spot-based optimization architecture.

CloudSweep is the engineering implementation. Cost Detective is the lab scenario presented for submission and live walkthrough.

---

## Documentation Entry Points

| Document | Purpose |
|---|---|
| [docs/COST_DETECTIVE_AUDIT.md](docs/COST_DETECTIVE_AUDIT.md) | **Primary submission document.** Scenario, findings, screenshots, savings plan. |
| [docs/lab/WALKTHROUGH.md](docs/lab/WALKTHROUGH.md) | Live demo script for the audit walkthrough. |
| [docs/lab/evidence-checklist.md](docs/lab/evidence-checklist.md) | Screenshot and evidence capture checklist. |
| [docs/lab/manual-test-plan.md](docs/lab/manual-test-plan.md) | Per-feature manual AWS verification checklist (CS + LAB). |
| [docs/PRD.md](docs/PRD.md) | CloudSweep product requirements. |
| [docs/MVP_SPEC.md](docs/MVP_SPEC.md) | CloudSweep MVP scope boundary. |
| [docs/implementation_plan.md](docs/implementation_plan.md) | CloudSweep phased delivery plan. |

---

## Repository Layout

```
src/python/              CloudSweep Lambda code (scanners, evaluator, remediator, notifier, approval)
terraform/modules/       Reusable Terraform modules (lambda, step-functions, scheduler, state-tracker,
                         approval-api, anomaly-detection)
terraform/environments/  dev and prod root modules
tests/                   pytest suite (unit + integration via moto)
scripts/                 Standalone operational scripts (lab garbage collector lives here)
docs/                    Product, implementation, and audit documentation
docs/lab/                Cost Detective lab-specific docs and walkthrough material
```

Modules planned for the Cost Detective lab (added in Phases 2–6):

- `terraform/modules/lab-seed/` — opt-in waste resources (EBS, EIP, idle EC2)
- `terraform/modules/budgets-sns/` — AWS Budgets + SNS/email alerts
- `terraform/modules/tag-governance/` — `CostCenter` tag enforcement
- `terraform/modules/compute-lab/` — Mixed Instances (On-Demand + Spot) ASG
- `scripts/garbage_collect_ebs.py` — standalone dry-run-first EBS cleanup

---

## Quick Start

CloudSweep dev environment deployment is covered in [docs/implementation_plan.md](docs/implementation_plan.md). The Cost Detective lab deploys on top of it via the opt-in `enable_lab_seed`, `enable_compute_lab`, and budget/governance variables documented in [docs/COST_DETECTIVE_AUDIT.md](docs/COST_DETECTIVE_AUDIT.md).

> **Safety:** all lab-seeded resources carry `CostCenter=Lab` and `Owner` tags. Destructive scripts default to dry-run. Always run `terraform plan` before apply and follow the teardown checklist in the walkthrough doc.
