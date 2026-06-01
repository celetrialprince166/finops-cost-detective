# Manual AWS Verification Plan

Per-feature manual test checklist. Run from a Windows PowerShell terminal with AWS CLI logged in to the sandbox account (region `eu-west-1`).

> Convention: **CS** = CloudSweep engineering test. **LAB** = Cost Detective lab test.
> Every test records: CLI command, expected output, screenshot target, pass/fail box.

---

## Conventions

- Replace `<acct>` with sandbox account ID where shown.
- All lab resources tagged `CostCenter=Lab Owner=<email> Project=cost-detective`.
- Run CS tests first to confirm baseline is healthy, then LAB tests.

---

## CS-0 — Baseline Sanity

### CS-0.1 — Identity and region

- [ ] `aws sts get-caller-identity`
  - Expect: `Arn` contains expected sandbox role; `Account` is sandbox.
- [ ] `aws configure get region`
  - Expect: `eu-west-1`.
- [ ] Screenshot: `tests/cs-0.1-identity.png`
- [ ] **PASS / FAIL:** ____

### CS-0.2 — Slack webhook present

- [ ] `aws ssm get-parameter --name /cloudsweep/slack/webhook --with-decryption --query "Parameter.Type" --output text`
  - Expect: `SecureString`.
- [ ] **PASS / FAIL:** ____

### CS-0.3 — Existing pytest suite green

- [ ] `pytest -q`
  - Expect: all tests pass (120 baseline + new lab tests added in later phases).
- [ ] **PASS / FAIL:** ____

---

## CS-1 — CloudSweep Pipeline Live Test

### CS-1.1 — Step Functions manual execution

- [ ] `aws stepfunctions start-execution --state-machine-arn arn:aws:states:eu-west-1:<acct>:stateMachine:cloudsweep-dev-sfn --name manual-test-$(Get-Date -Format yyyyMMddHHmmss)`
  - Expect: `executionArn` returned.
- [ ] Console: Step Functions → execution → graph all green (SCAN → EVALUATE → DECISION → REMEDIATE or WaitForApproval → NOTIFY).
- [ ] Screenshot: `tests/cs-1.1-sfn-graph.png`
- [ ] **PASS / FAIL:** ____

### CS-1.2 — Findings written to DynamoDB

- [ ] `aws dynamodb scan --table-name cloudsweep-dev-findings --limit 5 --query "Items[].{id:finding_id.S,resource:resource_id.S}"`
  - Expect: at least one row referencing a `CostCenter=Lab` resource.
- [ ] **PASS / FAIL:** ____

### CS-1.3 — Slack notification fired

- [ ] Check Slack channel for the configured webhook.
  - Expect: notification message with finding count and link.
- [ ] Screenshot: `tests/cs-1.3-slack.png`
- [ ] **PASS / FAIL:** ____

### CS-1.4 — DRY_RUN behavior

- [ ] `aws lambda get-function-configuration --function-name cloudsweep-dev-remediator --query "Environment.Variables.DRY_RUN"`
  - Expect: `"true"`.
- [ ] Confirm DynamoDB finding for the lab EBS volume shows `action_taken = dry_run` (not `deleted`).
- [ ] **PASS / FAIL:** ____

---

## LAB-1 — Sandbox Waste Seed

### LAB-1.1 — Terraform apply

- [ ] `terraform -chdir=terraform/environments/dev apply -var="enable_lab_seed=true" -auto-approve`
  - Expect: 3 resources created (`aws_ebs_volume.zombie`, `aws_eip.orphan`, `aws_instance.idle`).
- [ ] Output: capture `lab_seed_ebs_id`, `lab_seed_eip_id`, `lab_seed_instance_id`.
- [ ] Screenshot: `tests/lab-1.1-tf-apply.png`
- [ ] **PASS / FAIL:** ____

### LAB-1.2 — Unattached EBS visible

- [ ] `aws ec2 describe-volumes --filters Name=tag:CostCenter,Values=Lab Name=status,Values=available --query "Volumes[].{id:VolumeId,size:Size,az:AvailabilityZone}"`
  - Expect: at least 1 volume, `status=available` (i.e. unattached).
- [ ] Console screenshot: `tests/lab-1.2-ebs.png`
- [ ] **PASS / FAIL:** ____

### LAB-1.3 — Unassociated EIP visible

- [ ] `aws ec2 describe-addresses --filters Name=tag:CostCenter,Values=Lab --query "Addresses[?AssociationId==null].PublicIp"`
  - Expect: at least 1 EIP, no `AssociationId`.
- [ ] **PASS / FAIL:** ____

### LAB-1.4 — Idle EC2 visible

- [ ] `aws ec2 describe-instances --filters Name=tag:CostCenter,Values=Lab Name=instance-state-name,Values=running --query "Reservations[].Instances[].{id:InstanceId,type:InstanceType}"`
  - Expect: 1 running instance, lab-sized type.
- [ ] **PASS / FAIL:** ____

---

## LAB-2 — EBS Garbage Collector Script

### LAB-2.1 — Dry-run reports candidates

- [ ] `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --grace-days 0 --dry-run`
  - Expect: lists lab volume ID(s); ends with "Would delete N volumes"; **no deletion**.
- [ ] **PASS / FAIL:** ____

### LAB-2.2 — Real delete with safety snapshot

- [ ] `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --grace-days 0 --delete --snapshot-first`
  - Expect: snapshot created, then volume deleted.
- [ ] `aws ec2 describe-snapshots --owner-ids self --filters Name=tag:CostCenter,Values=Lab --query "Snapshots[].SnapshotId"`
  - Expect: snapshot present.
- [ ] `aws ec2 describe-volumes --volume-ids <lab volume id>`
  - Expect: `InvalidVolume.NotFound`.
- [ ] **PASS / FAIL:** ____

### LAB-2.3 — Refuses to delete tagged outside filter

- [ ] Tag an unrelated volume with `Project=other`. Run `python scripts/lab/garbage_collect_ebs.py --tag CostCenter=Lab --delete`.
  - Expect: unrelated volume NOT touched.
- [ ] **PASS / FAIL:** ____

### LAB-2.4 — pytest unit tests

- [ ] `pytest tests/unit/test_garbage_collect_ebs.py -v`
  - Expect: all green.
- [ ] **PASS / FAIL:** ____

---

## LAB-3 — Budget + SNS

### LAB-3.1 — Budget exists

- [ ] `aws budgets describe-budgets --account-id <acct> --query "Budgets[?BudgetName=='cs-lab-monthly-budget']"`
  - Expect: budget present, `BudgetLimit.Amount=50`, `TimeUnit=MONTHLY`.
- [ ] **PASS / FAIL:** ____

### LAB-3.2 — SNS topic and confirmed subscription

- [ ] `aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:eu-west-1:<acct>:cs-lab-cost-alerts --query "Subscriptions[].{ep:Endpoint,status:SubscriptionArn}"`
  - Expect: at least one with `status` not equal to `PendingConfirmation`.
- [ ] **PASS / FAIL:** ____

### LAB-3.3 — Forecasted-threshold notification wired

- [ ] `aws budgets describe-notifications-for-budget --account-id <acct> --budget-name cs-lab-monthly-budget --query "Notifications[].{type:NotificationType,threshold:Threshold}"`
  - Expect: `FORECASTED` type at `100` (or configured value).
- [ ] **PASS / FAIL:** ____

### LAB-3.4 — Test publish to SNS triggers email

- [ ] `aws sns publish --topic-arn arn:aws:sns:eu-west-1:<acct>:cs-lab-cost-alerts --subject "TEST alert" --message "Manual verification"`
  - Expect: email received within ~1 min.
- [ ] Screenshot: `tests/lab-3.4-email.png` (subject visible, body redacted if needed)
- [ ] **PASS / FAIL:** ____

---

## LAB-4 — CostCenter Tag Governance

### LAB-4.1 — Untagged RunInstances denied

- [ ] `aws ec2 run-instances --image-id <ami> --instance-type t3.micro --count 1` (no `--tag-specifications`).
  - Expect: `UnauthorizedOperation` referencing `aws:RequestTag/CostCenter`.
- [ ] Screenshot: `tests/lab-4.1-denied.png`
- [ ] **PASS / FAIL:** ____

### LAB-4.2 — Tagged RunInstances allowed

- [ ] `aws ec2 run-instances --image-id <ami> --instance-type t3.micro --count 1 --tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]"`
  - Expect: `InstanceId` returned.
- [ ] Immediately terminate: `aws ec2 terminate-instances --instance-ids <id>`.
- [ ] **PASS / FAIL:** ____

### LAB-4.3 — AWS Config rule compliance

- [ ] `aws configservice describe-compliance-by-config-rule --config-rule-names required-tags-ec2 --query "ComplianceByConfigRules[].Compliance.ComplianceType"`
  - Expect: `COMPLIANT` (after a brief evaluation delay).
- [ ] **PASS / FAIL:** ____

---

## LAB-5 — Mixed Instances Spot ASG

### LAB-5.1 — ASG exists with Mixed Instances Policy

- [ ] `aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names cs-lab-asg --query "AutoScalingGroups[0].MixedInstancesPolicy"`
  - Expect: object with `InstancesDistribution.OnDemandBaseCapacity=1`, multiple `Overrides[].InstanceType` entries.
- [ ] **PASS / FAIL:** ____

### LAB-5.2 — Both OD and Spot instances running

- [ ] `aws ec2 describe-instances --filters Name=tag:aws:autoscaling:groupName,Values=cs-lab-asg --query "Reservations[].Instances[].{id:InstanceId,lifecycle:InstanceLifecycle}"`
  - Expect: at least one `null` (OD) and one `spot`.
- [ ] **PASS / FAIL:** ____

### LAB-5.3 — Scale-out picks Spot

- [ ] `aws autoscaling set-desired-capacity --auto-scaling-group-name cs-lab-asg --desired-capacity 4`
- [ ] Wait ~2 min; rerun LAB-5.2.
  - Expect: additional instances are `spot`.
- [ ] Screenshot: `tests/lab-5.3-scaleout.png`
- [ ] Scale back: `aws autoscaling set-desired-capacity --auto-scaling-group-name cs-lab-asg --desired-capacity 1`
- [ ] **PASS / FAIL:** ____

### LAB-5.4 — Spot interruption resilience (optional)

- [ ] Trigger simulated Spot interruption via FIS (if available) or manually terminate a Spot instance.
  - Expect: ASG replaces it; OD base remains at 1.
- [ ] **PASS / FAIL:** ____

---

## LAB-6 — Teardown Verification

### LAB-6.1 — Lab Terraform destroyed

- [ ] `terraform -chdir=terraform/environments/dev apply -var="enable_lab_seed=false" -var="enable_compute_lab=false" -auto-approve`
- [ ] **PASS / FAIL:** ____

### LAB-6.2 — No lab resources remain

- [ ] `aws ec2 describe-instances --filters Name=tag:CostCenter,Values=Lab Name=instance-state-name,Values=running,pending`
  - Expect: empty `Reservations`.
- [ ] `aws ec2 describe-volumes --filters Name=tag:CostCenter,Values=Lab`
  - Expect: empty `Volumes`.
- [ ] `aws ec2 describe-addresses --filters Name=tag:CostCenter,Values=Lab`
  - Expect: empty `Addresses`.
- [ ] `aws ec2 describe-snapshots --owner-ids self --filters Name=tag:CostCenter,Values=Lab`
  - Expect: snapshots either gone or explicitly retained (documented in audit doc § 9).
- [ ] Screenshot: `tests/lab-6.2-teardown.png`
- [ ] **PASS / FAIL:** ____

---

## Test Run Log

Each manual test run records date, tester, AWS account, result summary.

| Run | Date | Tester | Account | CS-0 | CS-1 | LAB-1 | LAB-2 | LAB-3 | LAB-4 | LAB-5 | LAB-6 |
|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |
