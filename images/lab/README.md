# Cost Detective Audit - Evidence Screenshots

This directory holds AWS console screenshots captured during the audit walkthrough on 2026-05-26 against account `648637468459` in `eu-west-1`.

Screenshots were captured automatically by `scripts/lab/capture_window.ps1`, which screen-grabs the foreground Chrome window (matched by title) and writes a PNG straight into this folder. The 8 `phase*.png` files below are the canonical evidence set. (Three older `*.jpg` files saved manually earlier are redundant duplicates and can be deleted.)

To re-capture any shot: navigate Chrome to the source URL, then run:

```powershell
& scripts/lab/capture_window.ps1 -TitleMatch "<window title substring>" -OutPath images/lab/<name>.png
```

| Order | Suggested filename | Description | Source URL |
|---|---|---|---|
| 1 | `phase2-ebs-volumes.png` | EC2 Volumes filtered by `CostCenter=Lab` showing 1 Available (zombie) + 2 In-use (ASG OD + idle EC2). Re-seeded after the GC test deleted the earlier `vol-077...`. | https://eu-west-1.console.aws.amazon.com/ec2/home?region=eu-west-1#Volumes:v=3;tag:CostCenter=Lab |
| 2 | `phase2-eip-unassociated.png` | Elastic IPs filtered by `CostCenter=Lab` showing `eipalloc-09ee668a67c373136` (54.74.64.254) with empty Association ID = orphan zombie. | https://eu-west-1.console.aws.amazon.com/ec2/home?region=eu-west-1#Addresses:v=3;tag:CostCenter=Lab |
| 3 | `phase2-ec2-instances.png` | EC2 Instances filtered by `CostCenter=Lab` showing the idle lab EC2 (`i-0a16a702b048f6396`, t3.micro, Running, 3/3 checks passed) and terminated ASG members. | https://eu-west-1.console.aws.amazon.com/ec2/home?region=eu-west-1#Instances:v=3;tag:CostCenter=Lab;state=running,pending |
| 4 | `phase3-cs-sfn-graph.png` | Step Functions execution `smoke-20260526152525` graph view: Succeeded in 10.4 s through Scan -> Evaluate -> Decision -> Remediate -> NotifyComplete -> WorkflowEnd. | https://eu-west-1.console.aws.amazon.com/states/home?region=eu-west-1#/v2/executions/details/arn:aws:states:eu-west-1:648637468459:execution:cloudsweep-dev-cloudsweep:smoke-20260526152525 |
| 5 | `phase4-budget-config.png` | Budget detail page for `cloudsweep-dev-lab-monthly-budget`: $50 monthly cap, 0.17% current, OK alerts, Healthy. | https://us-east-1.console.aws.amazon.com/costmanagement/home#/budgets/details?name=cloudsweep-dev-lab-monthly-budget |
| 6 | `phase4-sns-confirmed.png` | SNS topic `cloudsweep-dev-lab-cost-alerts` with email subscription to `prince.ayiku@amalitechtraining.org` showing **Confirmed** status. | https://eu-west-1.console.aws.amazon.com/sns/v3/home?region=eu-west-1#/topic/arn:aws:sns:eu-west-1:648637468459:cloudsweep-dev-lab-cost-alerts |
| 7 | `phase5-iam-deny-summary.png` | IAM managed policy `cloudsweep-dev-lab-require-costcenter` Permissions Summary view showing Explicit deny on EC2 service (Write+Tagging) with "Multiple" request conditions. | https://us-east-1.console.aws.amazon.com/iam/home#/policies/details/arn%3Aaws%3Aiam%3A%3A648637468459%3Apolicy%2Fcloudsweep-dev-lab-require-costcenter?section=permissions |
| 8 | `phase5-iam-deny-json.png` | Same policy in JSON view: `DenyRunInstancesWithoutRequiredTag` (Null check on `aws:RequestTag/CostCenter`) and `DenyRemovingRequiredTag` (ForAnyValue StringEquals on `aws:TagKeys = CostCenter`). | https://us-east-1.console.aws.amazon.com/iam/home#/policies/details/arn%3Aaws%3Aiam%3A%3A648637468459%3Apolicy%2Fcloudsweep-dev-lab-require-costcenter?section=permissions&view=json |
| 9 | `phase6-asg-mixed-policy.png` | ASG `cloudsweep-dev-lab-asg` Details view scrolled to Mixed Instances Policy: 4 instance types (t3.micro/t3a.micro/t2.micro/t3.small), 0% On-Demand / 100% Spot above base, OD base = 1, allocation = price-capacity-optimized, capacity rebalance On, 3 AZs (eu-west-1a/b/c). | https://eu-west-1.console.aws.amazon.com/ec2/home?region=eu-west-1#AutoScalingGroupDetails:id=cloudsweep-dev-lab-asg;view=details |

## Why these screenshots are not automatically saved

The Claude Chrome extension's `save_to_disk` option writes screenshots to a Claude-managed location that is not exposed to the local filesystem. The screenshots are rendered inline in the conversation only. To get PNG files in this directory:

1. Open your Claude chat scrollback for this session.
2. Scroll to each image listed above.
3. Right-click -> "Save image as" -> save to `images/lab/<filename>.png`.

## Alternative: re-capture via the console URLs above

If the chat history is lost or the screenshots are no longer in scrollback, the source URLs are deterministic - log into the AWS console as `Prince_Dev_Labs`, paste each URL, and capture with your local snipping tool. As long as the lab Terraform stack is still applied (`enable_lab_*=true` flags), the IDs and resource state remain valid.

## Corroborating CLI evidence (already in the audit doc)

Many of these screenshots correspond to CLI commands captured in [`../../docs/COST_DETECTIVE_AUDIT.md`](../../docs/COST_DETECTIVE_AUDIT.md) (resource IDs, costs, test outputs). The screenshots are visual confirmation of the same facts.
