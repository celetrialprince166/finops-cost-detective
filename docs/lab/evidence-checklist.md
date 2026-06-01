# Evidence Capture Checklist

Every screenshot / artifact required for the Cost Detective Audit submission. File names follow `phase<N>-<slug>.png` and live in `images/lab/`.

> Convention: **CS** = CloudSweep engineering, **LAB** = Cost Detective lab artifact.

---

## Phase 1 — Audit Baseline

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 1.1 | Repo layout (CS vs LAB) | File tree screenshot | `phase1-repo-layout.png` | [ ] |
| 1.2 | Traceability matrix view | `docs/COST_DETECTIVE_AUDIT.md` § 3 rendered | `phase1-traceability.png` | [ ] |

---

## Phase 2 — Sandbox Waste

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 2.1 | Terraform plan output (lab-seed) | terminal | `phase2-tf-plan.png` | [ ] |
| 2.2 | Terraform apply output (lab-seed) | terminal | `phase2-tf-apply.png` | [ ] |
| 2.3 | Unattached EBS volume — `CostCenter=Lab` | EC2 → Volumes | `phase2-ebs-unattached.png` | [ ] |
| 2.4 | Unassociated EIP — `CostCenter=Lab` | EC2 → Elastic IPs | `phase2-eip-unassociated.png` | [ ] |
| 2.5 | Idle EC2 instance — `CostCenter=Lab` | EC2 → Instances | `phase2-ec2-idle.png` | [ ] |
| 2.6 | CloudWatch metric for idle EC2 (low CPU) | CloudWatch → Metrics → EC2 | `phase2-cw-idle-cpu.png` | [ ] |

---

## Phase 3 — Detection

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 3.1 | Cost Explorer — daily cost by service | Billing → Cost Explorer | `phase3-cost-explorer-service.png` | [ ] |
| 3.2 | Cost Explorer — cost by `CostCenter` tag | Billing → Cost Explorer | `phase3-cost-explorer-tag.png` | [ ] |
| 3.3 | Trusted Advisor — Idle/Underutilized | Trusted Advisor (note: requires Business/Enterprise support) | `phase3-trusted-advisor.png` | [ ] |
| 3.4 | **CS** Step Functions execution success | Step Functions → executions | `phase3-cs-sfn-execution.png` | [ ] |
| 3.5 | **CS** Step Functions graph view | Step Functions → graph | `phase3-cs-sfn-graph.png` | [ ] |
| 3.6 | **CS** DynamoDB finding row | DynamoDB → `cloudsweep-dev-findings` | `phase3-cs-dynamo-finding.png` | [ ] |
| 3.7 | **CS** Scanner log (structured JSON) | CloudWatch Logs → scanner Lambda | `phase3-cs-scanner-log.png` | [ ] |
| 3.8 | **LAB** EBS GC dry-run output | terminal | `phase3-lab-gc-dryrun.png` | [ ] |
| 3.9 | **LAB** EBS GC delete output | terminal | `phase3-lab-gc-delete.png` | [ ] |
| 3.10 | **LAB** Safety snapshot created by GC | EC2 → Snapshots | `phase3-lab-gc-snapshot.png` | [ ] |

---

## Phase 4 — Budgets and Alerts

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 4.1 | Budget configuration | Billing → Budgets → `cs-lab-monthly-budget` | `phase4-budget-config.png` | [ ] |
| 4.2 | SNS topic | SNS → `cs-lab-cost-alerts` | `phase4-sns-topic.png` | [ ] |
| 4.3 | SNS subscription (confirmed) | SNS → Subscriptions | `phase4-sns-subscribed.png` | [ ] |
| 4.4 | Subscription confirmation email | inbox | `phase4-email-confirm.png` | [ ] |
| 4.5 | Forecasted-spend alert email | inbox (live or staged) | `phase4-email-alert.png` | [ ] |

---

## Phase 5 — Tag Governance

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 5.1 | IAM deny policy JSON | IAM → Policies → `cs-lab-require-costcenter` | `phase5-iam-policy.png` | [ ] |
| 5.2 | Failed `RunInstances` (no tag) | terminal — CLI error | `phase5-run-denied.png` | [ ] |
| 5.3 | Successful `RunInstances` (with tag) | terminal | `phase5-run-allowed.png` | [ ] |
| 5.4 | AWS Config rule | Config → `required-tags-ec2` | `phase5-config-rule.png` | [ ] |
| 5.5 | AWS Config compliance view | Config → Compliance | `phase5-config-compliance.png` | [ ] |

---

## Phase 6 — Spot ASG

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 6.1 | Launch template | EC2 → Launch templates | `phase6-launch-template.png` | [ ] |
| 6.2 | ASG with Mixed Instances Policy | EC2 → Auto Scaling → details | `phase6-asg-mixed.png` | [ ] |
| 6.3 | Instances: OD + Spot mix | EC2 → Instances filtered | `phase6-instances-mix.png` | [ ] |
| 6.4 | Spot lifecycle field visible | EC2 → Instance → Lifecycle column | `phase6-spot-lifecycle.png` | [ ] |
| 6.5 | Scale-out activity log | ASG → Activity | `phase6-asg-activity.png` | [ ] |
| 6.6 | Cost comparison table | `docs/lab/spot-asg-walkthrough.md` rendered | `phase6-cost-compare.png` | [ ] |

---

## Phase 7 — Wrap-up

| # | Artifact | Source | Filename | Captured? |
|---|---|---|---|---|
| 7.1 | Walkthrough recording | screen recording | `phase7-walkthrough.mp4` | [ ] |
| 7.2 | Final audit doc rendered | `docs/COST_DETECTIVE_AUDIT.md` | `phase7-audit-doc.pdf` | [ ] |
| 7.3 | Teardown verification (empty queries) | terminal — 3x `describe-*` returning `[]` | `phase7-teardown-empty.png` | [ ] |

---

## Notes

- All screenshots redact account ID where visible (top-right of console).
- Slack webhook URL must never appear in any screenshot; mask if a CloudWatch log shows the constructed payload.
- Cost Explorer data lags ~24h — capture screenshots the day after deploying lab-seed for accurate spike visibility.
- Trusted Advisor "Idle Load Balancers" / "Underutilized EC2" checks require Business or Enterprise Support; if absent, note this and rely on CloudSweep scan output as the detection evidence.
