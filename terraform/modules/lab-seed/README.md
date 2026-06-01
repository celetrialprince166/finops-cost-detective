# Module: `lab-seed`

> **LAB artifact — Cost Detective Audit.** Not part of CloudSweep MVP.

Creates controlled "zombie assets" in a sandbox AWS account so the audit walkthrough has real, screenshot-worthy waste to detect, clean up, and remediate.

## What it creates

| Resource | Type | Tag | Notes |
|---|---|---|---|
| Unattached EBS volume | `aws_ebs_volume.zombie` | `ZombieType=unattached-ebs` | gp3, 8 GiB by default, encrypted, never attached. |
| Unassociated Elastic IP | `aws_eip.orphan` | `ZombieType=unassociated-eip` | VPC-scope, never associated. |
| Idle EC2 instance | `aws_instance.idle` | `ZombieType=idle-ec2` | Amazon Linux 2023, `t3.large` default, no ingress, no workload. |
| Security group | `aws_security_group.idle` | n/a | Egress-only; required for the idle instance. |
| Dedicated subnet | `aws_subnet.lab` (conditional) | n/a | Only created when `subnet_id` is empty. Lives in `vpc_id` (or default VPC), CIDR from `subnet_cidr` (default `10.0.0.240/28`). |

All resources are tagged:

```
CostCenter = <var.cost_center>   # default "Lab"
Owner      = <var.owner>
Project    = "cost-detective"
ManagedBy  = "terraform"
LabRole    = "zombie-asset"
```

The `CostCenter=Lab` tag is the filter used by `scripts/lab/garbage_collect_ebs.py` and by the tagging-governance demo.

## Cost note

The idle `t3.large` is the most expensive resource (~$0.092/hr on-demand in `eu-west-1`, about **$67/month** if left running). Pair with the `budgets-sns` module (Phase 4) and **always run teardown** after the walkthrough. Override `idle_instance_type` to `t3.micro` for free-tier-friendly demos.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | `string` | — | Prefix for every resource Name tag (e.g. `cs-lab`). |
| `cost_center` | `string` | `"Lab"` | Value of the `CostCenter` tag. |
| `owner` | `string` | — | Email/identifier recorded in `Owner` tag. |
| `ebs_size_gb` | `number` | `8` | Zombie volume size. |
| `ebs_availability_zone` | `string` | `"eu-west-1a"` | AZ for EBS + idle instance. |
| `idle_instance_type` | `string` | `"t3.large"` | EC2 instance type. |
| `idle_instance_ami_id` | `string` | `""` | Override SSM-published AL2023 AMI lookup. |
| `vpc_id` | `string` | `""` | VPC to create the lab subnet in. Empty = use default VPC. |
| `subnet_id` | `string` | `""` | Existing subnet to launch idle EC2 in. Empty = module creates a dedicated `/28` lab subnet in `vpc_id`. |
| `subnet_cidr` | `string` | `"10.0.0.240/28"` | CIDR used when the module creates the lab subnet. Must fit inside `vpc_id`'s CIDR. |
| `extra_tags` | `map(string)` | `{}` | Extra tags merged onto every resource. |

## Outputs

`ebs_volume_id`, `ebs_volume_size_gb`, `eip_allocation_id`, `eip_public_ip`, `idle_instance_id`, `idle_instance_type`, `security_group_id`, `summary`.

## Usage

Module is opt-in. Wired from `terraform/environments/dev/main.tf` behind the `enable_lab_seed` variable:

```hcl
module "lab_seed" {
  count  = var.enable_lab_seed ? 1 : 0
  source = "../../modules/lab-seed"

  name_prefix = "${var.project_name}-lab"
  owner       = var.lab_owner_email
  cost_center = var.lab_cost_center
}
```

Apply with:

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_seed=true" `
  -var="lab_owner_email=prince.ayiku@amalitechtraining.org" `
  -auto-approve
```

## Teardown

```powershell
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_seed=false" `
  -auto-approve
```

Then verify nothing remains:

```powershell
aws ec2 describe-instances --filters Name=tag:CostCenter,Values=Lab Name=instance-state-name,Values=running,pending
aws ec2 describe-volumes  --filters Name=tag:CostCenter,Values=Lab
aws ec2 describe-addresses --filters Name=tag:CostCenter,Values=Lab
```

All three should return empty arrays.
