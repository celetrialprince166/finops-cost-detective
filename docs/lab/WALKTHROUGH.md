# Cost Detective Audit — Live Walkthrough

Timed demo script for the submission walkthrough. **Target length: 22–25 minutes.**

| Field | Value |
|---|---|
| **Sandbox account / region** | `648637468459` · `eu-west-1` |
| **Lab tag baseline** | `CostCenter=Lab`, `Owner=<presenter-email>`, `Project=cost-detective` |
| **Budget cap** | `$50` MONTHLY (FORECASTED 100 % + ACTUAL 80 %) |
| **Pre-reqs** | AWS CLI logged in, Terraform ≥ 1.6, Python 3.11, repo at clean `main`, Slack webhook in SSM `/cloudsweep/slack/webhook` |

> Convention: **CS** = CloudSweep engineering artifact, **LAB** = Cost Detective lab artifact. Tag every step accordingly during narration.

---

## 0. Format & Production Notes (read once before recording)

- **Pre-record, don't present live.** Retake fluffed sections; reviewers can scrub. Use OBS, Loom, or `Win+G` (Game Bar).
- **1080p+ video, mic audio (not just system), zoom browser/terminal fonts** so console text is readable on a phone screen.
- **Record in sections and edit** — do not attempt a single 25-minute take.
- **Pre-stage long Terraform applies** off-camera. On-camera, run `terraform output` or `terraform refresh` to show outputs without making reviewers watch a 3-minute apply.
- **Have every tab and pane open before hitting record** (list in § 1 below).
- **Upload as YouTube *Unlisted* or Loom**, then update `README.md` § 12 with the link.

### The three "senior-engineer moments" — call these out explicitly

Reviewers grade on **judgement**, not button-clicking. Three places to demonstrate it:

| When | What to say (≤ 1 sentence) |
|---|---|
| § 5 Budget config | *"FORECASTED catches runaways before the dollars land; ACTUAL is the fallback if forecasting is off — that's why we layer both."* |
| § 4 EBS GC | *"Dry-run by default, tag-scoped, snapshot before delete — that's the safety triad. Account-wide cleanup with no tag filter is how teams have bad days."* |
| § 7 Spot ASG | *"`price-capacity-optimized` balances current Spot price with pool depth — more interruption-resistant than the older `lowest-price` strategy."* |

These are the three moments where you sound like a senior engineer rather than someone following a tutorial.

---

## 1. Pre-Flight (off-camera, ~15 min before recording)

- [ ] `aws sts get-caller-identity` — confirm sandbox account `648637468459`.
- [ ] `aws ssm get-parameter --name /cloudsweep/slack/webhook --with-decryption --region eu-west-1` — confirm webhook present.
- [ ] CloudSweep dev stack already deployed (Phases 1–4).
- [ ] No leftover `CostCenter=Lab` resources from previous runs — run § 9 teardown first if needed.
- [ ] **Browser tabs in this order** (left-to-right, single window): EC2 Volumes · EC2 Elastic IPs · EC2 Instances · EC2 ASG · Step Functions · Budgets · SNS · IAM Policies · Cost Explorer · Trusted Advisor · CloudWatch Logs.
- [ ] Terminal panes: (a) repo root for `terraform`/`python` commands, (b) AWS CLI pane for `aws ec2 …` queries.
- [ ] Editor open at `README.md` (for § 2 framing) and `docs/COST_DETECTIVE_AUDIT.md` (for § 8 recap).
- [ ] Mic test, screen-recorder ready.

---

## 2. Walkthrough Overview — Timing Table

| # | Section | Time | What's on screen | What you're proving |
|---|---|---|---|---|
| 3 | Scenario framing | 2 min | `README.md` § 1 + § 2 Executive Summary | Problem framed, outcomes quantified |
| 4 | **Inform** — find the waste | 4 min | EC2 console · Cost Explorer · CloudSweep SFN execution | 3 zombies detected 3 ways, $12.79/mo |
| 5 | **Automate** — EBS GC script | 3 min | Terminal: dry-run → real delete with snapshot | Safety triad: dry-run · tag-scope · snapshot |
| 6 | **Govern** — Budget + SNS | 3 min | Budgets console · SNS publish → email inbox | Layered FORECASTED + ACTUAL alerts |
| 7 | **Govern** — Tag enforcement | 3 min | IAM policy JSON · negative + positive `run-instances` | Deny verified both ways |
| 8 | **Optimize** — Spot ASG | 4 min | ASG console · 1 OD + 3 Spot · cost-comparison table | −51 % on stateless tier |
| 9 | Recommendations + teardown | 2 min | `README.md` § 9 · `terraform destroy` | Prioritized plan; clean exit |
| 10 | Recap & close | 1 min | Slide / `README.md` "60 seconds" block | Five outcomes restated |
|    | **Total** | **22 min** | | |

---

## 3. Scenario Framing (2 min)

- [ ] Open `README.md` § 1 ("The Problem"). Read the inherited-account framing aloud.
- [ ] Scroll to § 2 Executive Summary. Point at the four control rows. **Don't read the whole table** — point at the *Verified by* column and say *"every claim in this audit has an artifact behind it."*
- [ ] Mention the two frameworks anchored to: **FinOps Foundation** and **AWS Well-Architected — Cost Optimization Pillar**.

> **Narration anchor:** *"This is an audit, not a hypothetical. Three zombie classes detected, four controls deployed, one optimized architecture pattern, all verified in `eu-west-1` against account 648637468459."*

---

## 4. Inform — Find the Waste (4 min)

### 4.1 Seed (pre-staged off-camera; show outputs only)

- [ ] In terminal pane (a):
      ```powershell
      terraform -chdir=terraform/environments/dev output | grep lab_
      ```
      Show the three IDs: `lab_ebs_volume_id`, `lab_eip_allocation_id`, `lab_idle_instance_id`.

### 4.2 Verify in EC2 console

- [ ] EC2 → **Volumes** → filter tag `CostCenter=Lab` → show the unattached gp3 volume in `State: available`.
- [ ] EC2 → **Elastic IPs** → filter tag `CostCenter=Lab` → show the EIP with no association.
- [ ] EC2 → **Instances** → filter tag `CostCenter=Lab` → show the idle instance. Click into it → Monitoring tab → point at CPUUtilization ≈ 0 %.

### 4.3 Verify in Cost Explorer

- [ ] Cost Explorer → Service group-by → Daily granularity → 14-day window. Point at the spike attributable to the new resources.
- [ ] *(If Trusted Advisor cost checks available — Business / Enterprise Support only)* show them. If not, say so on camera: *"Basic Support doesn't expose the idle-EC2 check; CloudWatch metrics substitute."*

### 4.4 Verify via CloudSweep pipeline (CS)

- [ ] Step Functions → `cloudsweep-dev-sfn` → most recent execution graph. Show the path `Scan → Evaluate → Decision → Remediate → NotifyComplete`.
- [ ] Click the **Scan** state → Output tab → show the two findings (EBS + EIP) in the structured JSON.
- [ ] *(Optional)* DynamoDB → `cloudsweep-dev-findings` table → show the two rows with `CostCenter=Lab`.

> **Narration anchor:** *"Three detection sources: console, CloudSweep pipeline, and CloudWatch metrics for the idle instance. CloudSweep doesn't yet have an EC2-idle scanner — that's tracked as Recommendation #5."*

---

## 5. Automate — EBS Garbage Collector (3 min) — **SENIOR-ENGINEER MOMENT #1**

### 5.1 Dry-run first

- [ ] Terminal:
      ```powershell
      python scripts/lab/garbage_collect_ebs.py `
        --region eu-west-1 --tag CostCenter=Lab --grace-days 0
      ```
      Show the output: candidate count, IDs, monthly $ estimate, **"DRY RUN — no action taken."**

### 5.2 Walk the safety triad

- [ ] Show the script's CLI help: `python scripts/lab/garbage_collect_ebs.py --help`.
- [ ] Narrate **the three guards** visible in the help:
      1. `--delete` required for destructive action (dry-run default).
      2. `--tag KEY=VALUE` mandatory when `--delete` is set; refuses to run with an empty filter.
      3. `--snapshot-first` produces a tagged recovery snapshot.

### 5.3 Real delete with snapshot

- [ ] Terminal:
      ```powershell
      python scripts/lab/garbage_collect_ebs.py `
        --region eu-west-1 --tag CostCenter=Lab --grace-days 0 `
        --delete --snapshot-first
      ```
- [ ] EC2 console → **Snapshots** → filter `PreDeleteSnapshot=true` → show the new snapshot.
- [ ] EC2 console → **Volumes** → refresh → confirm the volume is gone.

> **Narration anchor:** *"Dry-run by default, tag-scoped, snapshot before delete — that's the safety triad. The script literally refuses to delete if you forget the tag filter. Account-wide cleanup with no filter is how teams have bad days."*

---

## 6. Govern — AWS Budget + SNS Alert (3 min)

### 6.1 Show the budget

- [ ] Budgets console → `cloudsweep-dev-lab-monthly-budget` → details.
- [ ] Point at:
      - Limit: $50 USD
      - FORECASTED notification at 100 %
      - ACTUAL notification at 80 %
      - SNS topic ARN
- [ ] SNS console → topic `cloudsweep-dev-lab-cost-alerts` → **Subscriptions** tab → confirm email subscription status `Confirmed`.

### 6.2 Prove end-to-end delivery

- [ ] Terminal:
      ```powershell
      aws sns publish `
        --topic-arn arn:aws:sns:eu-west-1:648637468459:cloudsweep-dev-lab-cost-alerts `
        --subject "Walkthrough test" --message "Budget alert path verified." `
        --region eu-west-1
      ```
- [ ] Switch to inbox → show the message arriving (pre-staged: have a recent test message ready in case Outlook delays).

> **Narration anchor #1 — judgement moment:** *"FORECASTED catches runaways before the dollars land — AWS's projection at the 5–7 day mark of the month is usually within 10 % accuracy. ACTUAL at 80 % is the late-warning fallback if forecasting underestimates. We layer both. The cheapest insurance in cloud."*

---

## 7. Govern — CostCenter Tag Enforcement (3 min) — **SENIOR-ENGINEER MOMENT #2**

### 7.1 Show the policy

- [ ] IAM → Policies → `cloudsweep-dev-lab-require-costcenter` → JSON tab.
- [ ] Narrate the two `Deny` statements:
      1. `ec2:RunInstances` when `aws:RequestTag/CostCenter` is null.
      2. `ec2:DeleteTags` for the `CostCenter` key — *"so users can't strip the tag after launch."*

### 7.2 Negative test — the showcase moment

- [ ] Assume the restricted role in a new terminal pane:
      ```powershell
      $creds = aws sts assume-role `
        --role-arn arn:aws:iam::648637468459:role/cloudsweep-dev-lab-restricted-role `
        --role-session-name walkthrough --query Credentials --output json | ConvertFrom-Json
      $env:AWS_ACCESS_KEY_ID = $creds.AccessKeyId
      $env:AWS_SECRET_ACCESS_KEY = $creds.SecretAccessKey
      $env:AWS_SESSION_TOKEN = $creds.SessionToken
      ```
- [ ] Run the **negative** test (no tag):
      ```powershell
      aws ec2 run-instances --image-id ami-0c13c2049f369d641 `
        --instance-type t3.micro --count 1 --region eu-west-1
      ```
- [ ] Show the response: **`UnauthorizedOperation` — "explicit deny in an identity-based policy: cloudsweep-dev-lab-require-costcenter"**.

### 7.3 Positive test

- [ ] Re-run with the tag:
      ```powershell
      aws ec2 run-instances --image-id ami-0c13c2049f369d641 `
        --instance-type t3.micro --count 1 --region eu-west-1 `
        --tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]"
      ```
- [ ] Show the launched instance ID. Then terminate it immediately:
      `aws ec2 terminate-instances --instance-ids <id> --region eu-west-1`.

### 7.4 Mention the enterprise variant

- [ ] Briefly: *"For multi-account orgs, prefer the SCP variant — it sits above IAM and can't be bypassed even by account-root. Documented in `docs/lab/tag-governance.md`."*
- [ ] Reset env vars: `Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN`.

> **Narration anchor #2 — judgement moment:** *"Both the negative and the positive test. A policy that denies everything is just as broken as one that denies nothing — always verify both paths."*

---

## 8. Optimize — Mixed Instances Spot ASG (4 min) — **SENIOR-ENGINEER MOMENT #3**

### 8.1 Show the ASG configuration

- [ ] EC2 → Auto Scaling Groups → `cloudsweep-dev-lab-asg` → **Instance management** tab.
- [ ] Show the **Mixed Instances Policy**:
      - On-Demand base: 1
      - On-Demand % above base: 0
      - Spot allocation strategy: `price-capacity-optimized`
      - 4 instance types in override list
      - Capacity rebalance: on
- [ ] Instances tab → show the table. Point at the **Lifecycle** column: 1 row says *On-Demand*, the rest say *Spot*. Point at the **Availability Zone** column: 3 distinct AZs.

### 8.2 Trigger scale-out (only if not already at desired=4)

- [ ] Terminal:
      ```powershell
      aws autoscaling set-desired-capacity `
        --auto-scaling-group-name cloudsweep-dev-lab-asg `
        --desired-capacity 4 --region eu-west-1
      ```
- [ ] Activity tab → watch the launch events.
- [ ] Instances tab refresh → confirm 1 OD + 3 Spot, spread across AZs.

### 8.3 The cost math

- [ ] Switch to `README.md` § 7.3 → show the 4-node fleet cost table:
      - All OD: $33.29/mo
      - 1 OD + 3 Spot: **$16.21/mo — −51 %**
      - All Spot: $10.51/mo — −68 % (higher risk)

> **Narration anchor #3 — judgement moment:** *"Four instance types times three AZs gives EC2 twelve Spot pools to choose from — that's the diversification. `price-capacity-optimized` balances current price with pool depth — more interruption-resistant than the older `lowest-price` strategy. The On-Demand baseline guarantees the service stays up even if every Spot pool gets reclaimed. And this same ratio on a 100-node fleet saves $400+ per month for the cost of writing the module once."*

---

## 9. Recommendations + Teardown (2 min)

### 9.1 Walk the recommendations table

- [ ] Switch to `README.md` § 9. Point at the top three:
      1. Budget + FORECASTED alerts (very low effort, prevents thousands)
      2. Tag enforcement (low effort, compounding value)
      3. Spot + Mixed Instances (medium effort, ~50 % recurring)

### 9.2 Teardown (can be off-camera if time-tight)

- [ ] Show the teardown command (don't run on camera unless you have time to verify):
      ```powershell
      terraform -chdir=terraform/environments/dev apply `
        -var="enable_lab_seed=false" `
        -var="enable_lab_budget=false" `
        -var="enable_lab_tag_governance=false" `
        -var="enable_lab_compute=false" -auto-approve
      ```
- [ ] Mention manual cleanup pointer: snapshots from `--snapshot-first`, SNS email unsubscribe, SSM parameters — full list in `README.md` § 14 and audit doc § 9.

### 9.3 Verification

- [ ] Optionally show one teardown-verification query:
      ```powershell
      aws ec2 describe-volumes --filters Name=tag:CostCenter,Values=Lab `
        --region eu-west-1 --query "Volumes[].VolumeId"
      ```
      Empty result confirms clean teardown.

---

## 10. Recap & Close (1 min)

Switch to `README.md` "📖 Read This in 60 Seconds" block. Read the five outcomes aloud:

1. Identified $12.79/mo zombie waste in three sandbox resources.
2. Built a dry-run-first EBS garbage collector with 23/23 unit tests.
3. Deployed a $50 Budget with FORECASTED + ACTUAL → SNS → confirmed email.
4. Enforced `CostCenter` tagging at launch via IAM deny — both paths tested.
5. Architected Mixed Instances ASG with −51 % savings on the stateless tier.

> **Closing line:** *"Submission package: README, audit document, optimization guide, walkthrough script, evidence checklist — all on the repo. Thanks for watching."*

Stop recording.

---

## Appendix A — Recovery Cheatsheet (mid-demo failures)

| Symptom | Fast recovery |
|---|---|
| Terraform apply fails | Skip to pre-deployed screenshots in `images/lab/` and narrate. |
| Step Functions stuck on approval | Open `WaitForApproval` state input, call approval API manually via `curl`. |
| Slack webhook 404 | Notifier fails open — show CloudWatch Logs of the constructed payload instead. |
| Spot capacity unavailable | Show ASG events explaining diversification kicked in; pivot to cost-comparison talking point. |
| Cost Explorer empty | Cost Explorer lags ~24h; pre-stage a screenshot from yesterday. |
| SNS test publish doesn't arrive in inbox | Pre-stage a screenshot of a prior delivery (MessageId in audit doc § 6.1). |
| IAM `assume-role` denied | Confirm the trust policy on `cloudsweep-dev-lab-restricted-role` allows your principal. |

---

## Appendix B — Post-Recording Checklist

- [ ] Watch the recording end-to-end at 1.25× speed. Cut dead air.
- [ ] Confirm all on-screen text is legible (zoom in on the smallest moment).
- [ ] Add a 5-second title card (project name + your name) at the start.
- [ ] Add a 5-second end card with the GitHub repo URL.
- [ ] Upload as **YouTube Unlisted** (or Loom).
- [ ] Update `README.md` § 12 — replace the *"to be linked here after recording"* placeholder with the URL.
- [ ] Commit the README update with a `docs: link walkthrough recording` commit and push.
