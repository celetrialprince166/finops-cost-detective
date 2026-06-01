output "ebs_volume_id" {
  description = "ID of the unattached zombie EBS volume."
  value       = aws_ebs_volume.zombie.id
}

output "ebs_volume_size_gb" {
  description = "Size of the zombie EBS volume in GiB."
  value       = aws_ebs_volume.zombie.size
}

output "eip_allocation_id" {
  description = "Allocation ID of the unassociated Elastic IP."
  value       = aws_eip.orphan.allocation_id
}

output "eip_public_ip" {
  description = "Public IP address of the orphan EIP."
  value       = aws_eip.orphan.public_ip
}

output "idle_instance_id" {
  description = "Instance ID of the idle EC2."
  value       = aws_instance.idle.id
}

output "idle_instance_type" {
  description = "Instance type of the idle EC2 (used to estimate waste cost)."
  value       = aws_instance.idle.instance_type
}

output "security_group_id" {
  description = "Security group attached to the idle instance."
  value       = aws_security_group.idle.id
}

output "summary" {
  description = "One-line human-readable summary of seeded resources."
  value = format(
    "lab-seed: EBS=%s (%dGiB) EIP=%s (%s) EC2=%s (%s)",
    aws_ebs_volume.zombie.id,
    aws_ebs_volume.zombie.size,
    aws_eip.orphan.allocation_id,
    aws_eip.orphan.public_ip,
    aws_instance.idle.id,
    aws_instance.idle.instance_type,
  )
}
