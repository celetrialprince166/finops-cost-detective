# AWS Cost Optimization Guide

> A practical, implementable end-to-end guide for engineering teams who have just inherited an AWS account (or want to stop their existing one bleeding money). Every step in this guide is backed by a reproducible artifact in this repository.

| Field | Value |
|---|---|
| **Audience** | Cloud engineers, SREs, platform leads, FinOps practitioners |
| **Scope** | AWS — single-account through multi-account (Organizations) |
| **Frameworks anchored to** | FinOps Foundation Framework (Inform → Optimize → Operate) · AWS Well-Architected — Cost Optimization Pillar |
| **Companion repo artifacts** | `terraform/modules/lab-*`, `scripts/lab/garbage_collect_ebs.py`, `src/python/scanners/*` |

---

## Table of Contents

1. [Why This Guide Exists](#1-why-this-guide-exists)
2. [The Mental Model: FinOps + Well-Architected](#2-the-mental-model-finops--well-architected)
3. [Step 1 — Inform: See What You Have](#3-step-1--inform-see-what-you-have)
4. [Step 2 — Operate: Stop the Bleeding (Budgets & Alerts)](#4-step-2--operate-stop-the-bleeding-budgets--alerts)
5. [Step 3 — Operate: Enforce Hygiene at Launch (Tagging Governance)](#5-step-3--operate-enforce-hygiene-at-launch-tagging-governance)
6. [Step 4 — Optimize: Right-Size the Steady State (Spot + Mixed Instances)](#6-step-4--optimize-right-size-the-steady-state-spot--mixed-instances)
7. [Step 5 — Optimize: Automate Cleanup (the Janitor Pattern)](#7-step-5--optimize-automate-cleanup-the-janitor-pattern)
8. [Step 6 — Manage: Measure and Iterate](#8-step-6--manage-measure-and-iterate)
9. [Anti-Patterns to Avoid](#9-anti-patterns-to-avoid)
10. [Appendix A — Copy-Pasteable Terraform Variables](#appendix-a--copy-pasteable-terraform-variables)
11. [Appendix B — IAM / SCP JSON](#appendix-b--iam--scp-json)
12. [Appendix C — AWS CLI Verification Queries](#appendix-c--aws-cli-verification-queries)
13. [Appendix D — Glossary](#appendix-d--glossary)
14. [References](#references)

---

<a id="1-why-this-guide-exists"></a>
## 1. Why This Guide Exists

Most AWS accounts that have been running for more than 12 months carry **15–35 %** invisible waste — orphaned EBS volumes, unassociated Elastic IPs, idle EC2 instances, oversized RDS, snapshots whose source volumes no longer exist, NAT Gateways routing nothing. The waste isn't malicious; it's the natural byproduct of fast-moving teams without active cost controls.

This guide gives a small team a 6-step path from *"we have no idea what we're spending money on"* to *"every dollar is attributable, automated, and reviewable."* It is deliberately opinionated: there is one recommended way to do each step, with an "enterprise variant" called out when relevant.

**You should not read this top-to-bottom.** Read § 2 (the mental model) once, then jump to the step that matches your current maturity. The order is the *direction of travel*, not a sequential gate.

---

<a id="2-the-mental-model-finops--well-architected"></a>
## 2. The Mental Model: FinOps + Well-Architected

Two industry frameworks underpin everything below. They overlap deliberately — using both gives you the *what* and the *how*.

### 2.1 FinOps Foundation Framework (the *what*)

Three cyclical phases, executed continuously per workload:

| Phase | Question it answers | Steps in this guide |
|---|---|---|
| **Inform** | What are we spending money on? Who owns it? | Step 1 |
| **Optimize** | Where is the waste, and what's the cheapest correct architecture? | Steps 4–5 |
| **Operate** | How do we keep it that way and react fast when it drifts? | Steps 2, 3, 6 |

Six principles cut across the phases (collaborate · business value drives decisions · everyone owns their usage · data is timely and accurate · enable FinOps centrally · use the cloud's variable-cost model).

### 2.2 AWS Well-Architected — Cost Optimization Pillar (the *how*)

Five design principles that act as a checklist for every architectural decision:

| WA principle | What it means in practice | Step in this guide |
|---|---|---|
| Implement Cloud Financial Management | Treat cost as a first-class engineering concern. | Steps 1, 6 |
| Adopt a consumption model | Pay only for what you use; turn things off when idle. | Step 4 |
| Measure overall efficiency | Cost per business outcome, not absolute spend. | Step 6 |
| Stop spending on undifferentiated heavy lifting | Use managed services where they reduce TCO. | Steps 4, 5 |
| Analyze and attribute expenditure | Every resource owned by a team via tags. | Steps 1, 3 |

### 2.3 Maturity ladder — Crawl / Walk / Run

You do not need to be at "Run" everywhere. The FinOps Foundation is explicit about this: *business value drives target maturity per capability*. For a small team inheriting a sandbox, "Crawl on most, Walk on one or two" is a healthy first quarter.

```
Crawl  →  basic visibility, manual tagging, monthly review
Walk   →  budgets per workload, automated tag-enforcement, scheduled cleanup
Run    →  cost-as-code in CI/CD, real-time anomaly detection, FOCUS-spec billing
```

---

<a id="3-step-1--inform-see-what-you-have"></a>
## 3. Step 1 — Inform: See What You Have

> **FinOps phase:** Inform · **WA principle:** Analyze and attribute expenditure
> **Time to value:** 1–2 hours · **Cost:** $0

You cannot optimize what you cannot see. Before any control is deployed, generate three artifacts.

### 3.1 Turn on Cost Explorer (and enable hourly + resource-level granularity)

Console → Billing → Cost Explorer → **Enable Cost Explorer**. Then under *Cost Explorer Settings* enable:

- **Hourly granularity** (last 14 days). Required for anomaly investigation.
- **Resource-level data** (last 14 days). Maps cost to individual resource IDs, not just services.

Both have small per-row costs but cap at a few dollars/month on a sandbox and are essential.

### 3.2 Activate cost-allocation tags

Console → Billing → Cost Allocation Tags → activate every tag you intend to use as a chargeback / showback dimension. For the pattern in this guide, at minimum activate:

- `CostCenter` (the primary attribution dimension)
- `Owner` (email of the responsible engineer)
- `Environment` (`dev` / `staging` / `prod`)
- `Workload` (the application name)

Activated tags take up to **24 hours** to appear in Cost Explorer reports. Activate them on day one.

### 3.3 Run the Trusted Advisor cost checks

Console → Trusted Advisor → **Cost Optimization**. The free checks identify:

- Low-utilization EC2 instances
- Idle load balancers
- Unassociated Elastic IPs
- Underutilized EBS volumes
- RDS idle DB instances *(Business / Enterprise Support only)*

If you only have Basic / Developer Support, substitute CloudWatch metrics on `CPUUtilization` (sustained < 5 % over 7 days is a reasonable idle signal) and the scanners in `src/python/scanners/` in this repo.

### 3.4 Tagging audit query — find what is *not* attributed

Use the Resource Groups Tag Editor or the AWS CLI:

```powershell
# Untagged EC2 instances (no CostCenter)
aws resourcegroupstaggingapi get-resources `
  --resource-type-filters ec2:instance `
  --tag-filters "Key=CostCenter,Values=" `
  --region eu-west-1
```

Anything returned is invisible to your future chargeback. This list is the input to Step 3.

### 3.5 (Power users) Cost & Usage Report + Athena

For organizations that have outgrown Cost Explorer, enable the **Cost & Usage Report** (CUR) writing Parquet to S3, then query with Athena. CUR is the source-of-truth dataset behind every third-party FinOps tool and is the right input for unit-economics dashboards. Out of scope for this guide; see [AWS docs](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html).

**Deliverable for this step:** a single page (or Confluence/Notion doc) titled *"What we found"* with: top 10 services by spend, % of spend that is untagged, list of zombie candidates from Trusted Advisor / scanners, top 3 anomalies.

---

<a id="4-step-2--operate-stop-the-bleeding-budgets--alerts"></a>
## 4. Step 2 — Operate: Stop the Bleeding (Budgets & Alerts)

> **FinOps phase:** Operate · **WA principle:** Implement Cloud Financial Management
> **Time to value:** 30 minutes · **Cost:** ≈ $0 (first 2 budgets free; $0.02/budget/day after)

This is the cheapest insurance in cloud. Do it first, before any architectural change.

### 4.1 Why FORECASTED beats ACTUAL — and why you use both

AWS Budgets supports two notification types. They look similar but solve different problems:

| Notification | Fires when | Solves | Reaction time |
|---|---|---|---|
| **ACTUAL** | Actual spend crosses a threshold (e.g. 80 % of budget) | Detects past breaches | Hours to days |
| **FORECASTED** | AWS's projection says spend *will* cross 100 % by month-end | Detects future breaches *now* | Minutes — catches runaway costs before they land |

Layer both. The FORECASTED alert at 100 % is your early-warning radar; the ACTUAL at 80 % is the late-warning fallback if forecasting fails.

### 4.2 Topology

```
AWS Budgets ──► SNS topic ──► Email subscription (confirmed)
                    │
                    └─► (later) Slack webhook via Lambda
                    └─► (later) PagerDuty for critical thresholds
```

The SNS topic must have a **topic policy** granting `budgets.amazonaws.com` publish access — without it, the budget silently fails to fire. This is the #1 misconfiguration in this control.

### 4.3 Implementation — using this repo

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_budget=true" `
  -var="lab_budget_email=you@example.com" `
  -var="lab_budget_limit_usd=50" `
  -var="lab_budget_actual_threshold_percent=80" `
  -auto-approve
```

This deploys [`terraform/modules/lab-budgets-sns/`](../terraform/modules/lab-budgets-sns/) which creates the budget, SNS topic, topic policy, and email subscription. **Confirm the subscription via the email AWS sends** — unconfirmed subscriptions silently drop messages.

### 4.4 Verification

```powershell
# 1. The budget exists with the expected notifications
aws budgets describe-budget `
  --account-id $(aws sts get-caller-identity --query Account --output text) `
  --budget-name cloudsweep-dev-lab-monthly-budget --region us-east-1

# 2. Publish a test SNS message — should arrive in your inbox within seconds
aws sns publish `
  --topic-arn arn:aws:sns:eu-west-1:<account>:cloudsweep-dev-lab-cost-alerts `
  --subject "Budget test" --message "Verifying end-to-end delivery."
```

**Production thresholds** (rule of thumb): one global budget at ~20 % above last quarter's run-rate, plus one per major workload at the workload's expected ceiling. Layer environments (`Environment=prod`) on top.

---

<a id="5-step-3--operate-enforce-hygiene-at-launch-tagging-governance"></a>
## 5. Step 3 — Operate: Enforce Hygiene at Launch (Tagging Governance)

> **FinOps phase:** Operate · **WA principle:** Analyze and attribute expenditure
> **Time to value:** 1–2 hours · **Cost:** $0 (IAM) / ~$0.001/evaluation (Config)

Cost Explorer, chargeback, and the budgets you just deployed are only as good as your tagging discipline. Tagging-after-the-fact is a Sisyphean task; **enforce at launch** instead.

### 5.1 Three layers of defense

| Layer | Mechanism | Where it blocks | Recommended for |
|---|---|---|---|
| **Preventive (single account)** | IAM managed deny policy with `aws:RequestTag/<Key>` condition | `ec2:RunInstances`, `ec2:DeleteTags` | Single AWS account; this repo's default |
| **Preventive (org-wide)** | AWS Organizations SCP + Tag Policy | Same actions, across every account in the OU | Multi-account orgs with AWS Organizations |
| **Detective** | AWS Config managed rule `REQUIRED_TAGS` | Existing & newly created resources | Compliance reporting; supplements either preventive layer |

### 5.2 Decision matrix

```
Have AWS Organizations access?  ──► YES ──► Use SCP (covers every account)
                                  └─► NO  ──► Use IAM deny policy

Need an audit trail of compliance? ─► add Config REQUIRED_TAGS rule
Comfortable with $0.001 per evaluation? ─► enable Config

Worried about post-launch tag removal? ─► add ec2:DeleteTags deny statement
                                          (always recommended)
```

### 5.3 Implementation — using this repo

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_tag_governance=true" `
  -var="lab_required_tag_key=CostCenter" `
  -auto-approve
```

This deploys [`terraform/modules/lab-tag-governance/`](../terraform/modules/lab-tag-governance/) which creates:

- IAM managed deny policy `cloudsweep-dev-lab-require-costcenter`
- A dedicated test role `cloudsweep-dev-lab-restricted-role` for negative-path testing
- (Opt-in via `lab_enable_config_rule=true`) AWS Config `REQUIRED_TAGS` rule scoped to `AWS::EC2::Instance`

The deny policy JSON is reproduced verbatim in [Appendix B](#appendix-b--iam--scp-json).

### 5.4 Verification — negative and positive tests

```powershell
# Negative: launch without CostCenter — must fail with explicit deny
aws ec2 run-instances --image-id ami-0c13c2049f369d641 --instance-type t3.micro `
  --count 1 --region eu-west-1
# Expected: UnauthorizedOperation ... explicit deny in identity-based policy:
#   cloudsweep-dev-lab-require-costcenter

# Positive: launch with CostCenter — must succeed
aws ec2 run-instances --image-id ami-0c13c2049f369d641 --instance-type t3.micro `
  --count 1 --region eu-west-1 `
  --tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]"
```

Always test both paths. A policy that denies *everything* is just as broken as one that denies *nothing*.

### 5.5 Enterprise variant — Organizations SCP + Tag Policy

If you have AWS Organizations, prefer the SCP path. SCPs sit above IAM and cannot be bypassed even by account-root credentials. See [docs/lab/tag-governance.md](lab/tag-governance.md) § *Enterprise variant* for the full SCP + Tag Policy JSON.

---

<a id="6-step-4--optimize-right-size-the-steady-state-spot--mixed-instances"></a>
## 6. Step 4 — Optimize: Right-Size the Steady State (Spot + Mixed Instances)

> **FinOps phase:** Optimize · **WA principle:** Adopt a consumption model
> **Time to value:** 2–4 hours · **Recurring savings:** ~50 % for stateless tiers

For any stateless workload — web tier, queue worker, batch processor — the textbook FinOps win is a Mixed Instances Auto Scaling Group with an On-Demand baseline and Spot for scale-out. Spot is **60–90 % cheaper** than On-Demand for the same hardware.

### 6.1 The pattern

```
       desired = N
       ┌──────────────────────────┐
       │   On-Demand (baseline)   │  ←  guarantees the service stays up
       │   (count = base, e.g. 1) │     even if every Spot is reclaimed
       ├──────────────────────────┤
       │     Spot (scale-out)     │  ←  the other N-base nodes
       │   spread across:         │     cheap, interruptible, diversified
       │   • 4 instance types     │
       │   • 3 availability zones │
       └──────────────────────────┘
```

### 6.2 When Spot is safe — and when it isn't

| Property | Spot-safe? |
|---|---|
| Stateless (no local disk state) | ✅ |
| Behind a load balancer or queue | ✅ |
| Graceful shutdown < 2 minutes (the Spot termination notice) | ✅ |
| Long-running stateful processes that can't checkpoint | ❌ |
| Per-instance licensing (e.g. SQL Server BYOL) | ❌ — costs may exceed Spot savings |
| Strict SLAs with no fallback capacity plan | ⚠️ — pair with On-Demand fallback |

### 6.3 Configuration — the four knobs that matter

| Knob | This repo's default | Why |
|---|---|---|
| `on_demand_base_capacity` | `1` | Guarantees a minimum baseline regardless of Spot availability |
| `on_demand_percentage_above_base_capacity` | `0` | All scale-out is Spot — maximises savings |
| `spot_allocation_strategy` | `price-capacity-optimized` | Balances current price with pool depth; best interruption resilience as of 2024+ |
| `override` (instance types) | `t3.micro, t3a.micro, t2.micro, t3.small` | 4 types × 3 AZs = 12 Spot pools to choose from |

`capacity_rebalance = true` is also set, allowing the ASG to preemptively replace at-risk Spot instances before AWS reclaims them.

### 6.4 Implementation — using this repo

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_compute=true" `
  -var="lab_compute_on_demand_base=1" `
  -var="lab_compute_desired_capacity=2" `
  -var="lab_compute_max_size=4" `
  -auto-approve
```

This deploys [`terraform/modules/lab-compute/`](../terraform/modules/lab-compute/) — launch template + ASG with `mixed_instances_policy`. The launch template carries `CostCenter=Lab` on both the instance and volume `tag_specifications`, so every ASG-launched instance automatically satisfies the Step 3 tagging policy.

### 6.5 Verification — confirm the mix is what you asked for

```powershell
aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names cloudsweep-dev-lab-asg `
  --region eu-west-1 `
  --query "AutoScalingGroups[0].Instances[].{Id:InstanceId,Type:InstanceType,AZ:AvailabilityZone,Life:LifecycleState}"

# Then cross-reference with describe-instances to confirm Spot vs On-Demand:
aws ec2 describe-instances `
  --filters Name=tag:aws:autoscaling:groupName,Values=cloudsweep-dev-lab-asg `
  --region eu-west-1 `
  --query "Reservations[].Instances[].{Id:InstanceId,Life:InstanceLifecycle,Type:InstanceType,AZ:Placement.AvailabilityZone}"
```

Spot instances show `InstanceLifecycle: "spot"`; On-Demand show `null`.

### 6.6 Cost math (eu-west-1, May 2026 list prices)

A steady 4-node `t3.micro` fleet, 730 hours/month:

| Configuration | Hourly | Monthly | vs. All-OD |
|---|---|---|---|
| All On-Demand | $0.0456 | **$33.29** | baseline |
| 1 OD + 3 Spot (this module's default) | $0.0222 | **$16.21** | **−51 %** |
| All Spot (no baseline) | $0.0144 | **$10.51** | −68 % (higher availability risk) |

Apply the same ratio to a 100-node web tier and the saving is ~$400+/month — for the cost of writing one Terraform module once.

### 6.7 Interruption handling checklist

Spot instances receive a **2-minute termination notice** at `http://169.254.169.254/latest/meta-data/spot/termination-time`. Your application must:

- [ ] Stop accepting new work within 30 seconds of the notice
- [ ] Finish in-flight requests / checkpoint state
- [ ] Deregister from any load balancer or service discovery
- [ ] Exit cleanly before the 120-second deadline

ASG lifecycle hooks + ELB connection draining handle most of this automatically when wired correctly.

---

<a id="7-step-5--optimize-automate-cleanup-the-janitor-pattern"></a>
## 7. Step 5 — Optimize: Automate Cleanup (the Janitor Pattern)

> **FinOps phase:** Optimize · **WA principle:** Stop spending on undifferentiated heavy lifting
> **Time to value:** 1 day for a basic janitor; the CloudSweep platform in this repo is the elaborated form.

Detect → classify → notify-or-remediate, on a schedule. Five rules make the difference between a useful janitor and an outage:

### 7.1 The five rules of safe automated cleanup

1. **Dry-run by default.** The destructive flag must be explicit and require justification (a ticket, a tag, an approval). The repo's [`scripts/lab/garbage_collect_ebs.py`](../scripts/lab/garbage_collect_ebs.py) refuses to delete unless `--delete` is passed, *and* refuses if no tag filter is supplied alongside.
2. **Tag-scope every destructive call.** Never operate "account-wide." Always filter by `CostCenter`, `Owner`, or another attribution tag. An empty tag filter combined with delete is a bug.
3. **Snapshot before delete** for any resource that holds data (EBS volumes, RDS instances, S3 lifecycle, EFS). Tag the snapshot with `PreDeleteSnapshot=true, SourceResourceId=<id>` so it is itself recoverable and discoverable.
4. **Grace period.** Skip resources younger than N days (default 7). New resources are often mid-deployment and look "unattached" for legitimate reasons.
5. **Audit trail.** Every action — even a dry-run skip — emits a structured log line with resource ID, action, reason, and dollar estimate. Send to CloudWatch Logs + (optionally) Slack/Teams.

### 7.2 What to clean up first (by ROI)

| Class | Detection signal | Typical $/resource/mo | Risk if wrong |
|---|---|---|---|
| Unattached EBS volumes | `State=available` for > grace_days | $0.08–$0.30/GiB | Low (snapshot first) |
| Unassociated Elastic IPs | `AssociationId is null` | $3.65 | None |
| Orphan snapshots | Source `VolumeId` deleted | $0.05/GiB | Medium (data loss) |
| Idle EC2 instances | `CPUUtilization` < 5 % for 7 days | $5–$500+ | High — confirm with the owner |
| Idle RDS | Connections=0 for 7 days | $15–$2000+ | High — confirm with the owner |
| Stopped instances > 30 days | `State=stopped` + age | $0 (compute) but $0.10/GiB EBS | Low |
| Empty load balancers | TargetCount=0 | $16–$25/month | Low |
| Unused NAT Gateways | No flow logs for 7 days | $32+ | Medium |

### 7.3 The reference implementation — CloudSweep

This repo's [`src/python/`](../src/python) tree is a production-grade janitor:

- **Scanners** (`src/python/scanners/{ebs,eip,rds,snapshot}.py`) per resource class
- **Evaluator** classifies findings as `AUTO_REMEDIATE` (low blast-radius, e.g. < $500 monthly impact) or `REQUIRE_APPROVAL` (anything higher)
- **Remediator** performs the action — *with `DRY_RUN=true` until you flip the flag*
- **Notifier** posts a Slack message with the actions taken or the approval link
- **Step Functions** orchestrates the whole pipeline on an EventBridge schedule
- **Approval API** routes the human-in-the-loop path back through Slack interactivity → API Gateway → Step Functions callback

You do not need all of this to get started. A single Lambda running the EBS GC script on a schedule covers ~30 % of typical waste at zero ops cost.

### 7.4 Minimum viable janitor (Day-1)

```powershell
# Step 1: prove the script works in dry-run against your real account
python scripts/lab/garbage_collect_ebs.py --region eu-west-1 --tag CostCenter=Lab

# Step 2: schedule it as a Lambda on EventBridge (daily)
# Step 3: tag-scope it to non-production first; promote after 2 weeks of clean dry-runs
# Step 4: enable --delete behind a feature flag with an alert wired to the SNS topic from Step 2
```

---

<a id="8-step-6--manage-measure-and-iterate"></a>
## 8. Step 6 — Manage: Measure and Iterate

> **FinOps phase:** Operate · **WA principle:** Measure overall efficiency
> **Cadence:** monthly review · quarterly target-setting

You're done with the controls. Now you need a feedback loop.

### 8.1 KPIs worth tracking (start with 5, not 25)

| KPI | Definition | Healthy target |
|---|---|---|
| **% tag coverage** | Resources with required tag set ÷ total resources | > 95 % for production, > 80 % for non-production |
| **Waste $ identified per month** | Sum of findings flagged by janitor scanners | Should trend down over a quarter |
| **Spot %** | Spot instance-hours ÷ total instance-hours | > 50 % for stateless tiers |
| **Forecast accuracy** | abs(actual − forecast) / actual | < 10 % month-over-month |
| **MTTR on findings** | Median hours between *finding raised* and *resource cleaned* | < 7 days |

Vanity metrics to avoid: total spend (goes up with growth, doesn't reflect efficiency) and savings-vs-list-price (RIs/SPs always look good against list).

### 8.2 Monthly review agenda (60 min, fixed)

1. (5 min) Top 5 movers — services that grew > 20 % MoM
2. (10 min) Tag coverage % per environment
3. (15 min) Open findings: aging, owner assignments, blockers
4. (10 min) Anomalies caught by Cost Anomaly Detection (if enabled)
5. (15 min) One architectural decision: what's the next workload to right-size?
6. (5 min) Action items + owners

### 8.3 Maturity targets — what "Walk" looks like after one quarter

- Every workload has a budget, an owner tag, and an environment tag.
- 80 %+ of stateless compute is on Spot or Savings Plans.
- The janitor runs daily; findings are auto-remediated under $X impact and routed to Slack above that.
- Cost Anomaly Detection is on; alerts trigger investigations, not just emails.
- Cost Explorer reports are bookmarked, not rebuilt from scratch each meeting.

---

<a id="9-anti-patterns-to-avoid"></a>
## 9. Anti-Patterns to Avoid

| Anti-pattern | Why it hurts | What to do instead |
|---|---|---|
| **Buying Savings Plans before right-sizing** | Locks you into oversized capacity for 1–3 years | Right-size first, then SP the steady-state floor |
| **Account-wide cleanup scripts (no tag filter)** | First bad day deletes production | Tag-scope everything; refuse to run if filter is empty |
| **One global budget, no per-workload alerts** | Noise — no actionable signal | One global *plus* one per workload |
| **Tagging policy without `DeleteTags` deny** | Users strip the tag immediately after launch | Always pair `RunInstances` deny with `DeleteTags` deny |
| **Spot for stateful or licensed workloads** | Surprise data loss; licensing cost > Spot savings | Stateless tier only; or pair with full On-Demand fallback |
| **No verification of the deny path** | Policy looks deployed but allows everything | Always run both negative + positive tests |
| **Optimizing without a baseline** | "We saved 30 %" with no baseline is a story, not a metric | Snapshot Cost Explorer before changes; compare same window |

---

<a id="appendix-a--copy-pasteable-terraform-variables"></a>
## Appendix A — Copy-Pasteable Terraform Variables

Full set for this repo's `dev` environment. Copy into a `*.auto.tfvars`:

```hcl
# Cost Detective lab — all four modules on
enable_lab_seed             = true
enable_lab_budget           = true
enable_lab_tag_governance   = true
enable_lab_compute          = true

# Attribution
lab_cost_center             = "Lab"
lab_owner_email             = "you@example.com"

# Budget
lab_budget_email                    = "you@example.com"
lab_budget_limit_usd                = 50
lab_budget_actual_threshold_percent = 80

# Tag governance
lab_required_tag_key                = "CostCenter"
lab_enable_config_rule              = false   # flip true to add detective control
lab_create_config_recorder          = false   # flip true if Config not yet active

# Compute (Mixed Instances ASG)
lab_compute_instance_types          = ["t3.micro", "t3a.micro", "t2.micro", "t3.small"]
lab_compute_on_demand_base          = 1
lab_compute_desired_capacity        = 2
lab_compute_max_size                = 4

# Idle EC2 seed (Phase 1)
lab_idle_instance_type              = "t3.micro"  # free-tier friendly; t3.large for realistic waste
lab_availability_zone               = "eu-west-1a"
```

---

<a id="appendix-b--iam--scp-json"></a>
## Appendix B — IAM / SCP JSON

### B.1 IAM managed deny — single-account preventive control

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRunInstancesWithoutCostCenter",
      "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "Null": { "aws:RequestTag/CostCenter": "true" }
      }
    },
    {
      "Sid": "DenyDeleteCostCenterTag",
      "Effect": "Deny",
      "Action": "ec2:DeleteTags",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "ForAnyValue:StringEquals": { "aws:TagKeys": ["CostCenter"] }
      }
    }
  ]
}
```

### B.2 SCP — org-wide preventive control (AWS Organizations)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyEC2WithoutCostCenter",
      "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "Null": { "aws:RequestTag/CostCenter": "true" }
      }
    }
  ]
}
```

Attach to the OU containing your member accounts. Pair with an AWS Organizations **Tag Policy** that enforces allowed values for `CostCenter`.

### B.3 SNS topic policy — required for AWS Budgets to publish

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowBudgetsToPublish",
    "Effect": "Allow",
    "Principal": { "Service": "budgets.amazonaws.com" },
    "Action": "sns:Publish",
    "Resource": "arn:aws:sns:eu-west-1:<account>:cloudsweep-dev-lab-cost-alerts"
  }]
}
```

---

<a id="appendix-c--aws-cli-verification-queries"></a>
## Appendix C — AWS CLI Verification Queries

Drop-in commands keyed to each step. PowerShell syntax; for bash replace backticks with `\`.

```powershell
# Step 1 — untagged EC2 instances
aws resourcegroupstaggingapi get-resources `
  --resource-type-filters ec2:instance `
  --tag-filters "Key=CostCenter,Values=" --region eu-west-1

# Step 2 — confirm budget + subscription
aws budgets describe-budget --account-id <acct> `
  --budget-name cloudsweep-dev-lab-monthly-budget --region us-east-1
aws sns list-subscriptions-by-topic `
  --topic-arn arn:aws:sns:eu-west-1:<acct>:cloudsweep-dev-lab-cost-alerts

# Step 3 — confirm IAM deny policy is attached and effective
aws iam list-attached-role-policies `
  --role-name cloudsweep-dev-lab-restricted-role
# (negative test runs as that role; positive test as a normal admin)

# Step 4 — confirm ASG mix
aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names cloudsweep-dev-lab-asg --region eu-west-1 `
  --query "AutoScalingGroups[0].MixedInstancesPolicy"

# Step 5 — find zombie EBS via the script (dry-run)
python scripts/lab/garbage_collect_ebs.py --region eu-west-1 --tag CostCenter=Lab

# Teardown verification — these four must all be empty
aws ec2 describe-instances --filters Name=tag:CostCenter,Values=Lab `
  Name=instance-state-name,Values=running,pending --region eu-west-1 `
  --query "Reservations[].Instances[].InstanceId"
aws ec2 describe-volumes --filters Name=tag:CostCenter,Values=Lab `
  --region eu-west-1 --query "Volumes[].VolumeId"
aws ec2 describe-addresses --filters Name=tag:CostCenter,Values=Lab `
  --region eu-west-1 --query "Addresses[].AllocationId"
aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names cloudsweep-dev-lab-asg --region eu-west-1 `
  --query "AutoScalingGroups[].AutoScalingGroupName"
```

---

<a id="appendix-d--glossary"></a>
## Appendix D — Glossary

| Term | Meaning |
|---|---|
| **Zombie asset** | A provisioned AWS resource that incurs cost but serves no purpose (unattached EBS, unassociated EIP, idle EC2). |
| **Spot Instance** | Spare EC2 capacity sold at 60–90 % discount; AWS can reclaim with a 2-minute notice. |
| **On-Demand** | Standard EC2 pricing — pay-as-you-go, no commitment, no interruption risk. |
| **Reserved Instance (RI)** | 1- or 3-year commitment to a specific instance family in exchange for ~30–70 % discount. |
| **Savings Plan (SP)** | More flexible alternative to RIs — commit to a $/hour spend rate; applies across instance families. |
| **Mixed Instances Policy** | ASG feature that combines On-Demand and Spot, optionally across multiple instance types. |
| **price-capacity-optimized** | Spot allocation strategy that picks pools balancing current price and pool depth. |
| **FORECASTED alert** | AWS Budgets notification fired when projected month-end spend will cross a threshold. |
| **SCP (Service Control Policy)** | AWS Organizations policy that sets the *maximum* permissions for accounts in an OU. Sits above IAM. |
| **CUR (Cost & Usage Report)** | AWS's most detailed billing dataset, delivered to S3 as Parquet/CSV. |
| **FOCUS** | FinOps Open Cost & Usage Specification — emerging standard schema for multi-cloud billing data. |
| **Chargeback / Showback** | Attributing cloud cost back to the team or product that incurred it (chargeback = billed; showback = informational). |
| **Crawl / Walk / Run** | FinOps Foundation's maturity ladder per capability. |

---

<a id="references"></a>
## References

- **FinOps Foundation — Framework Overview** — https://www.finops.org/framework/
- **FinOps Foundation — Phases (Inform/Optimize/Operate)** — https://www.finops.org/framework/phases/
- **FinOps Foundation — Maturity Model** — https://www.finops.org/framework/maturity-model/
- **AWS Well-Architected — Cost Optimization Pillar** — https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
- **AWS Well-Architected — Cost Design Principles** — https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/design-principles.html
- **AWS Budgets** — https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html
- **AWS Cost Anomaly Detection** — https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html
- **AWS Config — REQUIRED_TAGS rule** — https://docs.aws.amazon.com/config/latest/developerguide/required-tags.html
- **AWS Organizations — Tag Policies** — https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html
- **EC2 Spot Best Practices** — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html
- **EC2 ASG Mixed Instances Policy** — https://docs.aws.amazon.com/autoscaling/ec2/userguide/asg-purchase-options.html
- **AWS Trusted Advisor — Cost Optimization checks** — https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor-check-reference.html

---

*This guide is a living document. Pull requests welcome — particularly evidence of the patterns in production at different scales.*
