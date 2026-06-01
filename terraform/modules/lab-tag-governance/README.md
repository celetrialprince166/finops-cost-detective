# Module: `lab-tag-governance`

> **LAB artifact - Cost Detective Audit.** Not part of CloudSweep MVP.

Preventive (and optionally detective) controls that require every EC2 instance launch to carry a `CostCenter` tag.

## What it creates

| Resource | Purpose |
|---|---|
| `aws_iam_policy.require_tag` | Managed policy denying `ec2:RunInstances` when the request lacks `CostCenter` (and optionally when the value is outside an allow-list). Also denies `ec2:DeleteTags` for that key. |
| `aws_iam_role.test` | Role wrapping the deny policy + a baseline allow-list of EC2 APIs. Used to verify allow vs deny RunInstances paths without applying the deny to your real user. |
| `aws_iam_role_policy.test_baseline` + attachment | EC2 perms for the test role. |
| `aws_config_config_rule.required_tags` *(optional)* | AWS Config `REQUIRED_TAGS` managed rule scoped to `AWS::EC2::Instance`. |
| Config recorder + S3 + IAM role *(optional)* | Created only when `create_config_recorder=true` and Config isn't already active. |

## Inputs (key ones)

| Name | Default | Description |
|---|---|---|
| `name_prefix` | - | Prefix for policy / role / Config rule names. |
| `required_tag_key` | `"CostCenter"` | Tag key required on RunInstances. |
| `allowed_tag_values` | `[]` | Optional allow-list for the tag value. Empty = any non-empty value. |
| `test_role_trusted_principal_arns` | `[]` | Who may assume the test role. Empty = account root (you, via your normal user with `sts:AssumeRole`). |
| `enable_config_rule` | `false` | Create the AWS Config rule. |
| `create_config_recorder` | `false` | Also create Config recorder + S3 + role. Set false if Config is already active. |

## Verification

After `terraform apply`, assume the test role and run two `RunInstances` calls:

```powershell
# Capture credentials
$creds = aws sts assume-role `
  --role-arn <test_role_arn output> `
  --role-session-name lab-tag-test `
  --query "Credentials" --output json | ConvertFrom-Json
$env:AWS_ACCESS_KEY_ID = $creds.AccessKeyId
$env:AWS_SECRET_ACCESS_KEY = $creds.SecretAccessKey
$env:AWS_SESSION_TOKEN = $creds.SessionToken

# Look up a current AL2023 AMI for the test
$ami = aws ssm get-parameter `
  --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" `
  --region eu-west-1 --query "Parameter.Value" --output text

# NEGATIVE: no CostCenter tag - expect UnauthorizedOperation / AccessDenied
aws ec2 run-instances --image-id $ami --instance-type t3.micro --count 1 --region eu-west-1

# POSITIVE: with CostCenter tag - expect a new InstanceId
aws ec2 run-instances --image-id $ami --instance-type t3.micro --count 1 `
  --tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]" `
  --region eu-west-1
```

Always terminate the positive-test instance afterwards and unset the temp env vars:

```powershell
aws ec2 terminate-instances --instance-ids <new-id> --region eu-west-1
Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN
```

## Enterprise variant

For a real multi-account org, the preferred control is an AWS Organizations Service Control Policy (SCP) + Tag Policy attached at the OU. See [docs/lab/tag-governance.md](../../../docs/lab/tag-governance.md) for the full enterprise pattern - this single-account module is the practical equivalent when Organizations access is not available (e.g. a student sandbox).

## Usage

Module is opt-in. Wired from `terraform/environments/dev/main.tf`:

```hcl
module "lab_tag_governance" {
  count  = var.enable_lab_tag_governance ? 1 : 0
  source = "../../modules/lab-tag-governance"

  name_prefix      = "${var.project_name}-lab"
  required_tag_key = var.lab_cost_center_tag_key   # default "CostCenter"

  tags = {
    CostCenter = "Lab"
    Project    = "cost-detective"
    ManagedBy  = "terraform"
  }
}
```
