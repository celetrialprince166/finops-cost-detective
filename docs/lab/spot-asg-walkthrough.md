# Cost Detective Audit - Mixed Instances Spot ASG

The optimization architecture for the lab's stateless workload. Implemented by [`terraform/modules/lab-compute/`](../../terraform/modules/lab-compute/README.md).

---

## Why this pattern

Three things together explain almost all the cost savings:

1. **Spot Instances are 60-90% cheaper than On-Demand** for the same hardware. The trade is that AWS can reclaim them with two minutes' notice when its own demand spikes.
2. **A baseline of On-Demand instances** keeps the service alive even if every single Spot instance is reclaimed simultaneously. This is the safety floor.
3. **Diversifying across multiple instance types and Availability Zones** spreads the workload across many Spot pools, making a coordinated reclamation event very unlikely.

A Mixed Instances Auto Scaling Group is the AWS-native way to encode all three.

---

## Reference architecture

```
                            Auto Scaling Group
                            ┌──────────────────┐
                            │ desired = 2..N   │
                            │ min = 1, max = 4 │
                            └────────┬─────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
   ┌────▼──────┐               ┌─────▼─────┐                ┌────▼────┐
   │ Baseline  │               │  Scale-out capacity        │
   │ On-Demand │               │  (Spot 100%)               │
   │ count = 1 │               │ diversified across:        │
   └───────────┘               │   t3.micro                 │
                               │   t3a.micro                │
                               │   t2.micro                 │
                               │   t3.small                 │
                               │ in eu-west-1a / 1b / 1c    │
                               └────────────────────────────┘
```

Spot allocation strategy is `price-capacity-optimized`: AWS picks Spot pools that combine the lowest current price with the deepest available capacity, balancing cost against interruption risk.

---

## Walkthrough

Deploy with the lab variables already wired in `terraform/environments/dev`:

```powershell
$env:AWS_REGION = "eu-west-1"
terraform -chdir=terraform/environments/dev apply `
  -var="enable_lab_compute=true" `
  -var="lab_owner_email=prince.ayiku@amalitechtraining.org" `
  -auto-approve
```

After ~1 minute the ASG settles to `desired_capacity=2`.

### Show the policy

```powershell
aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names cloudsweep-dev-lab-asg `
  --region eu-west-1 `
  --query "AutoScalingGroups[0].MixedInstancesPolicy"
```

Expected output highlights:

- `InstancesDistribution.OnDemandBaseCapacity` = `1`
- `InstancesDistribution.OnDemandPercentageAboveBaseCapacity` = `0`
- `InstancesDistribution.SpotAllocationStrategy` = `price-capacity-optimized`
- `LaunchTemplate.Overrides[]` = four instance-type entries

### Confirm baseline mix

```powershell
aws ec2 describe-instances `
  --filters "Name=tag:aws:autoscaling:groupName,Values=cloudsweep-dev-lab-asg" `
            "Name=instance-state-name,Values=running" `
  --region eu-west-1 `
  --query "Reservations[].Instances[].{id:InstanceId,type:InstanceType,az:Placement.AvailabilityZone,lifecycle:InstanceLifecycle}" `
  --output table
```

Expect one `lifecycle=null` (On-Demand) and one `lifecycle=spot`. They may sit in different AZs - the diversification working.

### Scale up to demonstrate Spot growth

```powershell
aws autoscaling set-desired-capacity `
  --auto-scaling-group-name cloudsweep-dev-lab-asg `
  --desired-capacity 4 `
  --region eu-west-1
```

Wait ~2 minutes, repeat the `describe-instances` query. The two new instances should both be `lifecycle=spot`. On-Demand count stays at the base capacity of 1; the rest of the fleet is Spot.

### Scale back down

```powershell
aws autoscaling set-desired-capacity `
  --auto-scaling-group-name cloudsweep-dev-lab-asg `
  --desired-capacity 1 `
  --region eu-west-1
```

ASG drops to a single On-Demand instance (since `min_size=1` and `OnDemandBaseCapacity=1`).

---

## Cost comparison

Using `eu-west-1` Linux On-Demand prices (May 2026 list) for the instance types in the override list:

| Instance type | On-Demand $/hr | Typical Spot discount | Spot $/hr (approx.) |
|---|---|---|---|
| `t3.micro`  | $0.0114 | -68% | $0.0036 |
| `t3a.micro` | $0.0102 | -68% | $0.0033 |
| `t2.micro`  | $0.0126 | -65% | $0.0044 |
| `t3.small`  | $0.0228 | -68% | $0.0073 |

For a 4-node fleet running 24/7 on **`t3.micro`** as the representative size:

| Mode | Hourly | Monthly (~730h) |
|---|---|---|
| All On-Demand                                          | 4 x $0.0114 = $0.0456 | $33.29 |
| 1 OD baseline + 3 Spot (this module's default)         | 1 x $0.0114 + 3 x $0.0036 = $0.0222 | $16.21 |
| All Spot (zero baseline, riskier)                      | 4 x $0.0036 = $0.0144 | $10.51 |

**The default policy saves ~51% versus all-On-Demand**, while still keeping one always-on baseline for predictability. Going fully Spot saves another ~$5.70/month but trades it for the risk of every node disappearing during a regional shortage.

> The lab fleet is intentionally tiny so the absolute dollar values are small, but the **percentage savings scale linearly** to production workloads (e.g., a 100-node web tier saves $400+/month at the same ratios).

---

## Required tag compliance

The launch template's `tag_specifications` set `CostCenter=Lab` on every instance and volume. This:

- Satisfies the tag-governance deny policy ([tag-governance.md](tag-governance.md)).
- Makes scale-out instances visible in Cost Explorer filtered by `CostCenter`.
- Allows the EBS garbage collector to find ASG-launched volumes if any leak.

If you change `cost_center`, also update the allow-list in the tag-governance module so the ASG-launched instances don't trip the deny.

---

## Limitations and gotchas

- **Spot capacity unavailability** - if all 4 instance types are exhausted in all 3 AZs (rare in `eu-west-1`), scale-out will stall. ASG events will show `Failed to launch`. The mitigation is the diversification itself, plus the On-Demand baseline.
- **Interruption tolerance only** - this is a stateless demo. Don't put stateful workloads (databases, in-flight transaction processors, etc.) on Spot without proper handoff logic.
- **IMDSv2 enforced** - some legacy boot scripts that fetch metadata over the unauthenticated endpoint will fail. Update them to use the token.

---

## Audit deliverable checklist

- [ ] ASG console screenshot showing the Mixed Instances Policy panel.
- [ ] EC2 console filtered by ASG name showing OD + Spot mix.
- [ ] Scale-out activity log screenshot.
- [ ] This document referenced in the main audit doc § 7 (Optimization Architecture).
- [ ] Cost comparison table copied into the savings plan.
