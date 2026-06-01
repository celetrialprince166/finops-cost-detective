PYTHON ?= python
TERRAFORM ?= terraform
TF_DEV_DIR := terraform/environments/dev
TF_PROD_DIR := terraform/environments/prod
AWS_REGION ?= eu-west-1

# ---- Cost Detective lab variables (override on command line as needed) ------
LAB_OWNER_EMAIL ?= prince.ayiku@amalitechtraining.org
LAB_INSTANCE_TYPE ?= t3.micro
LAB_VARS := \
  -var="enable_lab_seed=true" \
  -var="lab_owner_email=$(LAB_OWNER_EMAIL)" \
  -var="lab_idle_instance_type=$(LAB_INSTANCE_TYPE)" \
  -var="enable_lab_budget=true" \
  -var="lab_budget_email=$(LAB_OWNER_EMAIL)" \
  -var="enable_lab_tag_governance=true" \
  -var="enable_lab_compute=true"

.PHONY: lint test tf-fmt tf-validate dev-plan prod-plan \
        lab-plan lab-apply lab-destroy lab-gc-dry-run lab-gc-delete lab-test \
        lab-verify lab-scan

lint:
	black --check src tests
	isort --check-only src tests
	$(TERRAFORM) -chdir=$(TF_DEV_DIR) fmt -check -recursive

test:
	pytest --cov=src/python --cov-report=term-missing

tf-fmt:
	$(TERRAFORM) fmt -recursive terraform

tf-validate:
	$(TERRAFORM) -chdir=$(TF_DEV_DIR) init -backend=false
	$(TERRAFORM) -chdir=$(TF_DEV_DIR) validate
	$(TERRAFORM) -chdir=$(TF_PROD_DIR) init -backend=false
	$(TERRAFORM) -chdir=$(TF_PROD_DIR) validate

dev-plan:
	$(TERRAFORM) -chdir=$(TF_DEV_DIR) plan

prod-plan:
	$(TERRAFORM) -chdir=$(TF_PROD_DIR) plan

# ============================================================================
# Cost Detective lab convenience targets
# ============================================================================

## Plan the full CloudSweep + lab stack
lab-plan:
	AWS_REGION=$(AWS_REGION) $(TERRAFORM) -chdir=$(TF_DEV_DIR) plan $(LAB_VARS)

## Apply the full CloudSweep + lab stack
lab-apply:
	AWS_REGION=$(AWS_REGION) $(TERRAFORM) -chdir=$(TF_DEV_DIR) apply $(LAB_VARS) -auto-approve

## Disable all lab modules (keeps CloudSweep deployed)
lab-destroy:
	AWS_REGION=$(AWS_REGION) $(TERRAFORM) -chdir=$(TF_DEV_DIR) apply \
	  -var="enable_lab_seed=false" \
	  -var="enable_lab_budget=false" \
	  -var="enable_lab_tag_governance=false" \
	  -var="enable_lab_compute=false" \
	  -auto-approve

## Dry-run the EBS garbage collector against lab volumes
lab-gc-dry-run:
	$(PYTHON) scripts/lab/garbage_collect_ebs.py --region $(AWS_REGION) --tag CostCenter=Lab --grace-days 0

## Real-delete the lab volumes (creates safety snapshot first)
lab-gc-delete:
	$(PYTHON) scripts/lab/garbage_collect_ebs.py --region $(AWS_REGION) --tag CostCenter=Lab --grace-days 0 --delete --snapshot-first

## Run unit tests for the lab GC script only
lab-test:
	pytest tests/unit/test_garbage_collect_ebs.py -v

## Trigger a CloudSweep state-machine execution and print its status
lab-scan:
	aws stepfunctions start-execution \
	  --state-machine-arn arn:aws:states:$(AWS_REGION):$$(aws sts get-caller-identity --query Account --output text):stateMachine:cloudsweep-dev-cloudsweep \
	  --name manual-$$(date +%Y%m%d%H%M%S) \
	  --region $(AWS_REGION)

## Print verification status of every lab artifact
lab-verify:
	@echo "=== Lab EC2 (CostCenter=Lab) ==="
	@aws ec2 describe-instances --region $(AWS_REGION) --filters Name=tag:CostCenter,Values=Lab Name=instance-state-name,Values=running --query "Reservations[].Instances[].{id:InstanceId,type:InstanceType,az:Placement.AvailabilityZone,lifecycle:InstanceLifecycle}" --output table
	@echo "=== Lab EBS (CostCenter=Lab) ==="
	@aws ec2 describe-volumes --region $(AWS_REGION) --filters Name=tag:CostCenter,Values=Lab --query "Volumes[].{id:VolumeId,size:Size,state:State}" --output table
	@echo "=== Lab EIPs (CostCenter=Lab) ==="
	@aws ec2 describe-addresses --region $(AWS_REGION) --filters Name=tag:CostCenter,Values=Lab --query "Addresses[].{ip:PublicIp,assoc:AssociationId}" --output table
	@echo "=== Lab Budget ==="
	@aws budgets describe-budget --account-id $$(aws sts get-caller-identity --query Account --output text) --budget-name cloudsweep-dev-lab-monthly-budget --query "Budget.{name:BudgetName,limit:BudgetLimit.Amount,unit:BudgetLimit.Unit}" --output table 2>/dev/null || echo "(budget not deployed)"
	@echo "=== Lab ASG ==="
	@aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names cloudsweep-dev-lab-asg --region $(AWS_REGION) --query "AutoScalingGroups[0].{name:AutoScalingGroupName,desired:DesiredCapacity,min:MinSize,max:MaxSize}" --output table 2>/dev/null || echo "(ASG not deployed)"
