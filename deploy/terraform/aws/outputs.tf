output "app_url" {
  description = "The address people open."
  value       = local.public_url
}

output "github_callback_url" {
  description = "Put this in the GitHub App's Callback URL."
  value       = "${local.public_url}/api/auth/github/callback"
}

output "ecr_repository_url" {
  description = "Push the app image here (README.md, step 2)."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}

output "files_bucket" {
  description = "Where the copies of scanner files and evidence go."
  value       = aws_s3_bucket.files.bucket
}

output "database_endpoint" {
  value = aws_db_instance.this.address
}

output "database_password_secret_arn" {
  description = "RDS keeps the database password here (it is never in the Terraform state)."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.app.name
}
