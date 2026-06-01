# Module: `lab-compute`

> **LAB artifact - Cost Detective Audit.** Not part of CloudSweep MVP.

Stateless "cost-aware" workload demonstrating the Mixed Instances + Spot Auto Scaling pattern.

## What it creates

| Resource | Purpose |
|---|---|
| `aws_launch_template.this` | AL2023 t3.micro by default, IMDSv2 required, encrypted gp3 root volume, `CostCenter=Lab` tag applied to every instance and volume. |
| `aws_security_group.asg` | Egress-only SG; no ingress. |
| `aws_autoscaling_group.this` | Mixed Instances policy: On-Demand base (default 1) + 100% Spot above base, 4 instance-type overrides, `price-capacity-optimized` allocation, multi-AZ. |

## Key cost knobs

| Variable | Default | Effect |
|---|---|---|
| `on_demand_base_capacity` | `1` | Floor of On-Demand instances kept for stability. Set to `0` to go fully Spot (cheaper, less reliable). |
| `on_demand_percentage_above_base` | `0` | Of capacity ABOVE base, what percent is On-Demand. `0` = scale-out is 100% Spot. |
| `spot_allocation_strategy` | `price-capacity-optimized` | Balances cost vs interruption risk. Use `lowest-price` for pure cost minimisation. |
| `instance_types` | 4 types | Diversifies across Spot pools to reduce simultaneous-interruption risk. |
| `desired_capacity` | `2` | Initial = 1 OD + 1 Spot. |
| `max_size` | `4` | Allows the walkthrough to scale up and observe Spot growth. |

## Trade-offs

- **Spot interruptions** - AWS may reclaim Spot instances with a 2-minute notice. Acceptable for stateless workloads only. The lab workload does nothing, so interruption is harmless. For real workloads add proper drain/replace logic.
- **Capacity rebalancing** - `capacity_rebalance=true` lets ASG proactively replace at-risk Spot instances before AWS reclaims them.
- **Instance diversification** - 4 types across 3 AZs = 12 Spot pools. Greatly reduces the probability of a single shortage taking out scale-out capacity.

## Verification

```powershell
# Show the ASG's mixed-instances policy
aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names <asg_name output> `
  --region eu-west-1 `
  --query "AutoScalingGroups[0].MixedInstancesPolicy"

# List current instances and their On-Demand / Spot lifecycle
aws ec2 describe-instances `
  --filters "Name=tag:aws:autoscaling:groupName,Values=<asg_name>" `
  --region eu-west-1 `
  --query "Reservations[].Instances[].{id:InstanceId,type:InstanceType,lifecycle:InstanceLifecycle,state:State.Name}" `
  --output table

# Scale up to demonstrate Spot growth
aws autoscaling set-desired-capacity `
  --auto-scaling-group-name <asg_name> `
  --desired-capacity 4 `
  --region eu-west-1
```

Lifecycle `null` = On-Demand. Lifecycle `spot` = Spot.

## Usage

Module is opt-in. Wired from `terraform/environments/dev/main.tf`:

```hcl
module "lab_compute" {
  count  = var.enable_lab_compute ? 1 : 0
  source = "../../modules/lab-compute"

  name_prefix = "${var.project_name}-lab"
  cost_center = var.lab_cost_center
  owner       = var.lab_owner_email
}
```
