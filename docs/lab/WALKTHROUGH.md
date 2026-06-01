# Cost Detective Audit — Live Walkthrough

Timed demo script for the submission walkthrough. Target length: **~25 minutes**.

| Field | Value |
|---|---|
| **Sandbox account / region** | `eu-west-1` |
| **Lab tag baseline** | `CostCenter=Lab`, `Owner=<presenter-email>`, `Project=cost-detective` |
| **Budget cap** | `$50` monthly forecast threshold |
| **Pre-reqs** | AWS CLI logged in, Terraform ≥ 1.6, Python 3.11, repo at clean `main`, Slack webhook in SSM `/cloudsweep/slack/webhook` |

> Convention: **CS** = CloudSweep engineering artifact, **LAB** = Cost Detective lab artifact. Tag every console step accordingly during the demo.

---

## 0. Pre-Flight (do BEFORE the live session — ~10 min, off-camera)

- [ ] `aws sts get-caller-identity` — confirm sandbox account.
- [ ] `aws ssm get-parameter --name /cloudsweep/slack/webhook --with-decryption` — confirm webhook present.
- [ ] CloudSweep dev stack already deployed (Phase 1–4, per [docs/DEV_DIARY.md](../DEV_DIARY.md)).
- [ ] No leftover `CostCenter=Lab` resources from previous runs (run teardown § 7 first).
- [ ] Browser tabs open: EC2, EBS, EIP, Budgets, SNS, Step Functions, Cost Explorer, Trusted Advisor, CloudWatch Logs.
- [ ] Screen recording started.

---

## 1. Scenario Framing (~2 min)

- [ ] Open [docs/COST_DETECTIVE_AUDIT.md § 2](../COST_DETECTIVE_AUDIT.md#2-scenario-and-objectives) — read scenario.
- [ ] Show traceability matrix (§ 3) — one-screen overview of CS vs LAB split.

---

## 2. Deploy Lab Sandbox Waste — **LAB** (~3 min)

- [ ] `terraform -chdir=terraform/environments/dev plan -var="enable_lab_seed=true"`
- [ ] `terraform -chdir=terraform/environments/dev apply -var="enable_lab_seed=true" -auto-approve`
- [ ] Show outputs: lab EBS volume ID, EIP allocation ID, idle EC2 instance ID.
- [ ] EC2 console → Volumes → filter `CostCenter=Lab` → show unattached volume.
- [ ] EC2 console → Elastic IPs → filter `CostCenter=Lab` → show unassociated EIP.
- [ ] EC2 console → Instances → filter `CostCenter=Lab` → show idle large instance.
- [ ] Capture screenshots per [evidence-checklist.md § Phase 2](evidence-checklist.md#phase-2--sandbox-waste).

---

## 3. Detect Waste — **CS + Console** (~4 min)

- [ ] Cost Explorer → "Service" group-by → daily granularity → screenshot spike.
- [ ] Trusted Advisor → "Idle / Underutilized" checks → screenshot findings (if support plan exposes them).
- [ ] **CS:** Step Functions console → start execution of `cloudsweep-dev-sfn` manually.
- [ ] Wait for state machine → SCAN → EVALUATE → DECISION.
- [ ] DynamoDB → `cloudsweep-dev-findings` → show new findings rows tagged with the lab resources.
- [ ] CloudWatch Logs → latest scanner Lambda log → show structured JSON finding.

---

## 4. EBS Garbage Collector — **LAB** (~3 min)

- [ ] `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --grace-days 0 --dry-run`
- [ ] Show dry-run output: "Would delete N volumes (estimated $X/month)."
- [ ] `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --grace-days 0 --delete --snapshot-first`
- [ ] EC2 console → Snapshots → confirm safety snapshot exists.
- [ ] EC2 console → Volumes → confirm lab volume gone.
- [ ] (Walk back through script flags briefly — emphasize default dry-run.)

---

## 5. Active Cost Controls — **LAB** (~3 min)

- [ ] Budgets console → show `cs-lab-monthly-budget` ($50 forecasted threshold).
- [ ] SNS console → topic `cs-lab-cost-alerts` → show confirmed email subscription.
- [ ] CloudWatch console → demonstrate forecasted-spend alert email (pre-staged screenshot from a previous test if budget hasn't fired live yet).

---

## 6. CostCenter Tag Governance — **LAB** (~3 min)

- [ ] **Negative test:** `aws ec2 run-instances --image-id <ami> --instance-type t3.micro --count 1` (no tag).
  - [ ] Expect: `UnauthorizedOperation` referencing `aws:RequestTag/CostCenter`.
- [ ] **Positive test:** rerun with `--tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]"`.
  - [ ] Expect: instance launches.
- [ ] AWS Config console → `required-tags-ec2` rule → show compliance view.
- [ ] Briefly point to [tag-governance.md](tag-governance.md) for SCP / Organizations enterprise variant.
- [ ] Terminate the test instance.

---

## 7. Mixed Instances Spot ASG — **LAB** (~4 min)

- [ ] `terraform -chdir=terraform/environments/dev apply -var="enable_lab_seed=true" -var="enable_compute_lab=true" -auto-approve`
- [ ] EC2 → Auto Scaling Groups → `cs-lab-asg` → show Mixed Instances Policy.
- [ ] Instances tab → show 1 On-Demand + N Spot.
- [ ] Trigger scale-out: set desired capacity to 4 → observe Spot instances launch.
- [ ] Walk through [spot-asg-walkthrough.md](spot-asg-walkthrough.md) cost comparison.

---

## 8. Savings Plan Summary (~2 min)

- [ ] [docs/COST_DETECTIVE_AUDIT.md § 8](../COST_DETECTIVE_AUDIT.md#8-savings-plan-and-prioritized-recommendations) — walk the prioritized list.
- [ ] Highlight: zombie deletion (immediate), tagging (preventive), Spot adoption (sustained).

---

## 9. Teardown (~2 min, off-camera if time-constrained)

- [ ] `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --grace-days 0 --delete` (clean any new volumes).
- [ ] Manually release any test EIPs not destroyed by Terraform.
- [ ] `terraform -chdir=terraform/environments/dev apply -var="enable_lab_seed=false" -var="enable_compute_lab=false" -auto-approve`
- [ ] Manual cleanup:
  - [ ] SNS email subscription confirmation if leaving budget in place; otherwise unsubscribe.
  - [ ] EBS snapshots created by `--snapshot-first`.
  - [ ] CloudWatch Log groups for terminated lab Lambdas (optional).
- [ ] `aws ec2 describe-instances --filters Name=tag:CostCenter,Values=Lab` → expect empty.
- [ ] `aws ec2 describe-volumes --filters Name=tag:CostCenter,Values=Lab` → expect empty.
- [ ] `aws ec2 describe-addresses --filters Name=tag:CostCenter,Values=Lab` → expect empty.

---

## 10. Q&A / Buffer (~1 min)

- [ ] Confirm submission docs link in chat: `docs/COST_DETECTIVE_AUDIT.md`.
- [ ] Stop recording.

---

## Appendix — Recovery Cheatsheet (mid-demo failures)

| Symptom | Fast recovery |
|---|---|
| Terraform apply fails | Skip to pre-deployed screenshots in `images/lab/` and narrate. |
| Step Functions stuck on approval | Open `WaitForApproval` state input, call approval API manually via `curl` example in [docs/DEV_DIARY.md](../DEV_DIARY.md). |
| Slack webhook 404 | Notifier fails open — show CloudWatch Logs of the constructed payload instead. |
| Spot capacity unavailable | Show ASG events explaining diversification kicked in; pivot to cost comparison talking point. |
| Cost Explorer empty | Cost Explorer lags ~24h; pre-stage a screenshot from yesterday. |
