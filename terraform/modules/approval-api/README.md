# approval-api Terraform Module

Exposes a single API Gateway REST endpoint that receives Slack interactive
component callbacks (button clicks on Approve / Deny messages) and proxies
them to the CloudSweep approval Lambda.

## What this module creates

| Resource | Purpose |
|---|---|
| `aws_api_gateway_rest_api` | Root REST API |
| `aws_api_gateway_resource` `/approval` | Parent path segment |
| `aws_api_gateway_resource` `/approval/callback` | Callback endpoint path |
| `aws_api_gateway_method` `POST /approval/callback` | Accepts Slack POST events |
| `aws_api_gateway_integration` | AWS_PROXY to approval Lambda |
| `aws_api_gateway_deployment` | Deploys the API definition |
| `aws_api_gateway_stage` `v1` | Publishes the deployment |
| `aws_lambda_permission` | Grants API GW permission to invoke the Lambda |

## Inputs

| Name | Type | Description |
|---|---|---|
| `name` | `string` | Base name for the REST API and child resources |
| `approval_lambda_arn` | `string` | ARN of the approval Lambda function |
| `approval_lambda_name` | `string` | Name of the approval Lambda (for the permission resource) |
| `tags` | `map(string)` | Tags applied to taggable resources |

## Outputs

| Name | Description |
|---|---|
| `api_endpoint` | Full invoke URL (`https://{id}.execute-api.{region}.amazonaws.com/v1/approval/callback`) |
| `rest_api_id` | API Gateway REST API ID |
| `stage_name` | Deployed stage name (`v1`) |

## Usage

```hcl
module "approval_api" {
  source               = "../../modules/approval-api"
  name                 = "cloudsweep-dev-approval-api"
  approval_lambda_arn  = module.approval_lambda.function_arn
  approval_lambda_name = module.approval_lambda.function_name
  tags                 = local.common_tags
}
```

Configure the `api_endpoint` output as the **Request URL** under your Slack
app's **Interactivity & Shortcuts** settings page.
