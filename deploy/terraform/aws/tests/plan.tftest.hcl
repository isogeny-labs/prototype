# Offline checks of the plan, with mocked AWS (no account, no credentials):  terraform test
mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address            = "evidence-lab.abc.us-east-1.rds.amazonaws.com"
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-db", kms_key_id = "", secret_status = "active" }]
    }
  }
  mock_resource "aws_lb" {
    defaults = { dns_name = "evidence-lab-1.us-east-1.elb.amazonaws.com", arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/evidence-lab/1" }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn                       = "arn:aws:acm:us-east-1:123456789012:certificate/1"
      domain_validation_options = [{ domain_name = "lab.example.com", resource_record_name = "_x.lab.example.com", resource_record_type = "CNAME", resource_record_value = "_y.acm-validations.aws" }]
    }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/evidence-lab-mock" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/evidence-lab/1" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/evidence-lab:1" }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = { certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/1" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:github" }
  }
}

mock_provider "random" {}

run "plain_http_without_a_domain" {
  command = apply

  assert {
    condition     = output.app_url == "http://evidence-lab-1.us-east-1.elb.amazonaws.com"
    error_message = "Without a domain the app is on the load balancer's own name over HTTP."
  }
  assert {
    condition     = length(aws_lb_listener.https) == 0 && aws_lb_listener.http.default_action[0].type == "forward"
    error_message = "Without a domain there is no HTTPS listener and HTTP forwards to the app."
  }
  assert {
    condition     = aws_ecs_service.app.desired_count == 1 && aws_ecs_service.app.deployment_maximum_percent == 100
    error_message = "Exactly one copy of the app runs, never two at once."
  }
  assert {
    condition     = length(aws_secretsmanager_secret.github_client_secret) == 0
    error_message = "No GitHub secret without a GitHub App."
  }
  assert {
    condition     = !strcontains(aws_ecs_task_definition.app.container_definitions, "GITHUB")
    error_message = "Without a GitHub App the task has no GitHub settings (the password login is used)."
  }
  assert {
    condition     = aws_db_instance.this.manage_master_user_password && aws_db_instance.this.storage_encrypted && !aws_db_instance.this.publicly_accessible
    error_message = "The database password is kept by RDS, storage is encrypted, the database is private."
  }
  assert {
    condition     = aws_db_instance.this.deletion_protection
    error_message = "Data is protected by default."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.files.block_public_acls && aws_s3_bucket_public_access_block.files.restrict_public_buckets
    error_message = "The bucket is private."
  }
  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled
    error_message = "Redis is reached over TLS."
  }
}

run "https_and_github_with_a_domain" {
  command = apply

  variables {
    domain_name          = "lab.example.com"
    route53_zone_id      = "Z123"
    github_client_id     = "Iv1.test"
    github_client_secret = "test-only-secret"
    github_allowed_orgs  = ["isogeny-labs"]
  }

  assert {
    condition     = output.app_url == "https://lab.example.com" && output.github_callback_url == "https://lab.example.com/api/auth/github/callback"
    error_message = "With a domain the app is on HTTPS at that domain."
  }
  assert {
    condition     = length(aws_lb_listener.https) == 1 && aws_lb_listener.http.default_action[0].type == "redirect"
    error_message = "HTTPS listener, and HTTP redirects to it."
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.alb_https) == 1
    error_message = "Port 443 is open to allowed_cidrs."
  }
  assert {
    condition = alltrue([
      strcontains(aws_ecs_task_definition.app.container_definitions, "\"EVIDENCE_LAB_GITHUB_ALLOWED_ORGS\""),
      strcontains(aws_ecs_task_definition.app.container_definitions, "\"valueFrom\":\"arn:aws:secretsmanager:us-east-1:123456789012:secret:github\""),
      !strcontains(aws_ecs_task_definition.app.container_definitions, "test-only-secret"),
      strcontains(aws_ecs_task_definition.app.container_definitions, "\"EVIDENCE_LAB_DATABASE_PASSWORD\""),
      strcontains(aws_ecs_task_definition.app.container_definitions, "rediss://"),
    ])
    error_message = "Secrets reach the task from Secrets Manager, never as plain values; Redis is TLS."
  }
}

run "throwaway_copy" {
  command = plan

  variables {
    protect_data = false
  }

  assert {
    condition     = !aws_db_instance.this.deletion_protection && aws_db_instance.this.skip_final_snapshot && aws_s3_bucket.files.force_destroy
    error_message = "protect_data = false lets terraform destroy remove everything."
  }
}
