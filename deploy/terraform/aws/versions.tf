# Isogeny Evidence Lab on AWS (21 November 2026). See README.md in this folder.
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State: local by default. For a team, copy backend.tf.example to backend.tf (an S3 bucket with locking).
}

provider "aws" {
  region = var.region

  default_tags {
    tags = merge({ Project = "evidence-lab", Environment = var.name, ManagedBy = "terraform" }, var.tags)
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  name = var.name
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  https      = var.domain_name != "" && var.route53_zone_id != ""
  public_url = local.https ? "https://${var.domain_name}" : "http://${aws_lb.app.dns_name}"

  github_enabled = var.github_client_id != ""
}
