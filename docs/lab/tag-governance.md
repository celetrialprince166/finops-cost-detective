# Cost Detective Audit - CostCenter Tagging Policy

Goal: every EC2 instance in the account must carry a `CostCenter` tag so finance can attribute spend and engineering teams can be held accountable. Untagged launches must be blocked, not just flagged after the fact.

Two layers of control:

| Layer | Tool | What it does | When to use |
|---|---|---|---|
| **Preventive** | IAM deny policy (and/or SCP) | Blocks the API call at launch time. | Always - cheapest, fastest, deterministic. |
| **Detective** | AWS Config `required-tags` managed rule | Flags any non-compliant instance that slipped through. | Recommended belt-and-braces; required for audit history. |

The Cost Detective lab implements the preventive layer (IAM deny) by default and offers the detective layer (Config rule) opt-in. The enterprise variant (SCP + Tag Policy via AWS Organizations) is documented below for production-grade rollouts.

---

## Single-account implementation (this lab)

Implemented in [`terraform/modules/lab-tag-governance/`](../../terraform/modules/lab-tag-governance/README.md).

### Deny logic (excerpt)

```hcl
statement {
  sid       = "DenyRunInstancesWithoutRequiredTag"
  effect    = "Deny"
  actions   = ["ec2:RunInstances"]
  resources = ["arn:aws:ec2:*:*:instance/*"]
  condition {
    test     = "Null"
    variable = "aws:RequestTag/CostCenter"
    values   = ["true"]
  }
}

statement {
  sid       = "DenyRemovingRequiredTag"
  effect    = "Deny"
  actions   = ["ec2:DeleteTags"]
  resources = ["arn:aws:ec2:*:*:instance/*"]
  condition {
    test     = "ForAnyValue:StringEquals"
    variable = "aws:TagKeys"
    values   = ["CostCenter"]
  }
}
```

Key choices:

- `aws:RequestTag/CostCenter` evaluates the tag set on the inbound `RunInstances` request, not on the resulting instance. That is what makes this a launch-time block.
- The second statement (`DenyRemovingRequiredTag`) closes the loophole where a user launches with the tag and then strips it via `ec2:DeleteTags`. Without this, the preventive control is bypassable post-launch.
- The policy is attached to a dedicated test IAM role, **not** to the user that runs Terraform. This keeps the deploy workflow unaffected while still demonstrating the control.
- We do **not** attach the deny policy at the account root. Identity-based IAM policies cannot be attached to the root user, and even if they could, doing so could lock you out of recovery actions.

### How to demonstrate

The procedure is captured in [`docs/lab/manual-test-plan.md`](manual-test-plan.md) tests LAB-4.1 / LAB-4.2 / LAB-4.3. Summary:

1. Assume the lab test role:
   ```powershell
   $creds = aws sts assume-role `
     --role-arn <module.lab_tag_governance.test_role_arn> `
     --role-session-name lab-tag-test `
     --query "Credentials" --output json | ConvertFrom-Json
   $env:AWS_ACCESS_KEY_ID = $creds.AccessKeyId
   $env:AWS_SECRET_ACCESS_KEY = $creds.SecretAccessKey
   $env:AWS_SESSION_TOKEN = $creds.SessionToken
   ```
2. **Negative test** - call `aws ec2 run-instances` without any tag specification. Expect an `AccessDenied` error citing `aws:RequestTag/CostCenter`.
3. **Positive test** - same command with `--tag-specifications "ResourceType=instance,Tags=[{Key=CostCenter,Value=Lab}]"`. Expect a new `InstanceId`.
4. Terminate the positive-test instance immediately. Unset the temp credentials.

Capture both responses for the audit evidence checklist ([`evidence-checklist.md`](evidence-checklist.md) section Phase 5).

### Detective layer (optional)

When `enable_config_rule=true` the module also provisions the AWS Config managed rule `REQUIRED_TAGS`, scoped to `AWS::EC2::Instance`. Non-compliant instances appear in the Config console under Rules -> required-tags-ec2 with `COMPLIANT` / `NON_COMPLIANT` status per resource.

Requires an active Config recorder. If the account has none, set `create_config_recorder=true` so the module creates a minimal recorder, delivery channel, and S3 bucket scoped to `AWS::EC2::Instance` only.

---

## Enterprise variant (AWS Organizations)

For multi-account environments the preventive control belongs at the organization root or OU, not in each member account. AWS Organizations provides two complementary mechanisms:

### 1. Service Control Policy (SCP)

Attach an SCP to the OU containing your member accounts:

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
      "Sid": "DenyRemovingCostCenter",
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

The SCP supersedes any identity-based policy in the member account: even an account-level admin cannot launch an untagged instance.

### 2. Tag Policy

Tag Policies define the allowed set of keys and (optionally) values, and which resource types must comply. Example:

```json
{
  "tags": {
    "CostCenter": {
      "tag_key": { "@@assign": "CostCenter" },
      "tag_value": {
        "@@assign": ["Lab", "Platform", "DataPlatform", "Marketing"]
      },
      "enforced_for": {
        "@@assign": ["ec2:instance"]
      }
    }
  }
}
```

This both standardises the key spelling (`CostCenter`, not `costcenter` or `Cost-Center`) and constrains the values to an approved list. Combined with the SCP, the result is: launches without the key are denied, and launches with bad values are flagged as non-compliant in the Tag Policy compliance report.

### Why we did not deploy the enterprise variant here

A single-account sandbox lacks an Organizations management account, so:

- `aws organizations create-policy` fails with `AWSOrganizationsNotInUseException`.
- SCPs cannot be attached without an OU structure.
- Tag Policies have the same dependency.

In production, this is the right place to put the control. In the lab we demonstrate the identical *enforcement semantics* via an IAM deny policy, but with a smaller blast radius and zero dependency on Organizations access.

---

## Limitations and gotchas

- **Service-linked roles can bypass IAM denies.** This is uncommon for `RunInstances` but worth knowing. SCPs do not have this weakness.
- **Other launch paths** - Auto Scaling Group instance launches use the ASG's launch template tags, which Terraform manages. Make sure the lab-compute launch template (Phase 6) carries `CostCenter` on its `tag_specifications`.
- **`MetadataOptions.HttpTokens=required`** - unrelated to tagging, but enforced on the lab idle EC2 to keep the audit doc honest about other security hygiene.
- **Existing untagged instances** are not retroactively terminated. The detective Config rule flags them; remediation policy (terminate, force-tag, notify owner) is the operator's decision.

---

## Audit deliverable checklist

- [ ] IAM policy JSON visible in the AWS IAM console screenshot.
- [ ] Failed `RunInstances` CLI output (negative test) - showing the deny condition phrase.
- [ ] Successful `RunInstances` CLI output (positive test) - showing the new `InstanceId`.
- [ ] (Optional) Config rule compliance view screenshot.
- [ ] Reference to this document in the main audit doc, Phase 2 / governance section.
