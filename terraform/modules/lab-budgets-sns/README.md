# Module: `lab-budgets-sns`

> **LAB artifact - Cost Detective Audit.** Not part of CloudSweep MVP.

Active cost-control plane for the Cost Detective lab.

## What it creates

| Resource | Purpose |
|---|---|
| `aws_sns_topic.alerts` | Channel that AWS Budgets publishes to when thresholds are crossed. |
| `aws_sns_topic_policy.alerts` | Allows `budgets.amazonaws.com` to call `sns:Publish`. |
| `aws_sns_topic_subscription.email` | Delivers alerts to `var.subscriber_email`. **Requires manual confirmation** via the email AWS sends after apply. |
| `aws_budgets_budget.monthly` | Monthly budget (default $50) with a FORECASTED notification and an optional ACTUAL notification. |

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | `string` | - | Prefix used for the budget and topic names (e.g. `cs-lab`). |
| `budget_limit_usd` | `number` | `50` | Monthly budget cap, USD. |
| `forecasted_threshold_percent` | `number` | `100` | Percent of budget at which the FORECASTED alert fires. |
| `actual_threshold_percent` | `number` | `80` | Percent at which the ACTUAL-spend alert fires. Set to `0` to disable. |
| `subscriber_email` | `string` | - | Email subscribed to the SNS topic. |
| `cost_filters` | `map(list(string))` | `{}` | Optional Budget cost filters, e.g. `{ TagKeyValue = ["user:CostCenter$Lab"] }`. Empty = whole account. |
| `tags` | `map(string)` | `{}` | Extra tags applied to module resources. |

## Outputs

`sns_topic_arn`, `sns_topic_name`, `subscription_arn`, `budget_name`, `budget_id`, `subscriber_email`.

## Confirmation flow

1. `terraform apply` creates the topic, policy, subscription (pending) and budget.
2. AWS sends a confirmation email to `var.subscriber_email`.
3. Subscriber clicks the link in the email - subscription becomes `Confirmed`.
4. Next time the budget crosses a threshold, an email arrives via SNS.

To test the wiring without waiting for real spend, publish to the topic directly:

```powershell
aws sns publish `
  --topic-arn <output sns_topic_arn> `
  --subject "TEST cost alert" `
  --message "Manual verification message" `
  --region eu-west-1
```

## Usage

Module is opt-in. Wired from `terraform/environments/dev/main.tf` behind `enable_lab_budget`:

```hcl
module "lab_budget" {
  count  = var.enable_lab_budget ? 1 : 0
  source = "../../modules/lab-budgets-sns"

  name_prefix      = "${var.project_name}-lab"
  budget_limit_usd = var.lab_budget_limit_usd
  subscriber_email = var.lab_budget_email
  tags = {
    CostCenter = "Lab"
    Project    = "cost-detective"
    ManagedBy  = "terraform"
  }
}
```

Apply with:

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_budget=true" `
  -var="lab_budget_email=prince.ayiku@amalitechtraining.org" `
  -auto-approve
```
