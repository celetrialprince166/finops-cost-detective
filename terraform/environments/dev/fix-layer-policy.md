# Fix: Add lambda:GetLayerVersion permission to TennisProd

`Out-File` uses UTF-16 by default — AWS CLI rejects non-ASCII policy documents.
Use `Set-Content -Encoding ascii` instead.

## Step 1: Write policy file (ASCII encoding)

```powershell
Set-Content -Path policy.json -Value '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"lambda:GetLayerVersion","Resource":"arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312:*"}]}' -Encoding ascii
```

## Step 2: Apply policy

```powershell
aws iam put-user-policy --user-name TennisProd --policy-name CloudsweepLambdaLayerAccess --policy-document file://policy.json
```

## Step 3: Deploy

```powershell
terraform apply -auto-approve
```

## Step 4: Cleanup

```powershell
Remove-Item policy.json
```
