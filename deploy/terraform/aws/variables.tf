variable "name" {
  description = "Name of this copy; prefixes every resource (letters, digits and dashes)."
  type        = string
  default     = "evidence-lab"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,24}$", var.name))
    error_message = "name: 2 to 25 lowercase letters, digits or dashes, starting with a letter."
  }
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Extra tags for every resource."
  type        = map(string)
  default     = {}
}

# ---- network

variable "vpc_cidr" {
  description = "Address range of the new VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "allowed_cidrs" {
  description = "Who may reach the load balancer. Narrow it (an office or VPN range) until the open questions in docs/HOSTING.md are settled."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ---- address (HTTPS when both are given; otherwise plain HTTP on the load balancer's own name)

variable "domain_name" {
  description = "The address people open, e.g. lab.example.com. Needs route53_zone_id."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone that holds domain_name (for the certificate and the alias record)."
  type        = string
  default     = ""
}

# ---- the app

variable "image_tag" {
  description = "Tag of the app image in the ECR repository this creates (push it first; README.md)."
  type        = string
  default     = "latest"
}

variable "cpu" {
  description = "Fargate CPU units for the app (1024 = 1 vCPU)."
  type        = number
  default     = 1024
}

variable "memory" {
  description = "Fargate memory for the app, in MiB."
  type        = number
  default     = 2048
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps the app's logs."
  type        = number
  default     = 30
}

# ---- GitHub login (docs/HOSTING.md, "The GitHub App")

variable "github_client_id" {
  description = "The GitHub App's Client ID. Empty: no GitHub login, the app asks for a password instead."
  type        = string
  default     = ""
}

variable "github_client_secret" {
  description = "The GitHub App's client secret. Kept in Secrets Manager (and in the Terraform state: keep the state private)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_app_slug" {
  description = "The App's name in github.com/apps/<slug> (optional)."
  type        = string
  default     = ""
}

variable "github_allowed_users" {
  description = "GitHub logins or numeric account ids that may log in."
  type        = list(string)
  default     = []
}

variable "github_allowed_orgs" {
  description = "Organizations whose active members may log in (the App needs Members: read-only)."
  type        = list(string)
  default     = []
}

variable "github_allow_anyone" {
  description = "Let every GitHub account log in. Everyone shares the same assessments."
  type        = bool
  default     = false
}

# ---- data

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS storage in GiB."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Run the database in two availability zones."
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "protect_data" {
  description = "Keep the database, bucket and file system from being destroyed by terraform destroy (deletion protection, final snapshot, no force-destroy). Turn off only for a throwaway copy."
  type        = bool
  default     = true
}
