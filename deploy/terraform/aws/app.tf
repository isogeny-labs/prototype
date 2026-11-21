# ---- the image

resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "MUTABLE"
  force_delete         = !var.protect_data

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

# ---- secrets

resource "aws_secretsmanager_secret" "github_client_secret" {
  count                   = local.github_enabled ? 1 : 0
  name_prefix             = "${local.name}/github-client-secret-"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "github_client_secret" {
  count         = local.github_enabled ? 1 : 0
  secret_id     = aws_secretsmanager_secret.github_client_secret[0].id
  secret_string = var.github_client_secret
}

# ---- logs

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
}

# ---- roles

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# Used by ECS to start the task: pull the image, write logs, read the two secrets.
resource "aws_iam_role" "execution" {
  name_prefix        = "${local.name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [aws_db_instance.this.master_user_secret[0].secret_arn],
      aws_secretsmanager_secret.github_client_secret[*].arn,
    )
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# Used by the app itself: the bucket and the file system, nothing else.
resource "aws_iam_role" "task" {
  name_prefix        = "${local.name}-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "Bucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.files.arn]
  }
  statement {
    sid       = "Objects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.files.arn}/*"]
  }
  statement {
    sid       = "DataFolder"
    actions   = ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"]
    resources = [aws_efs_file_system.data.arn]
    condition {
      test     = "StringEquals"
      variable = "elasticfilesystem:AccessPointArn"
      values   = [aws_efs_access_point.data.arn]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# ---- the service

resource "aws_ecs_cluster" "this" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  environment = merge(
    {
      EVIDENCE_LAB_DATA_DIR     = "/data"
      EVIDENCE_LAB_MODE         = "demo"
      EVIDENCE_LAB_DATABASE_URL = "postgresql://${aws_db_instance.this.username}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${aws_db_instance.this.db_name}?sslmode=require"
      EVIDENCE_LAB_REDIS_URL    = "rediss://${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
      EVIDENCE_LAB_STORAGE_URL  = "s3://${aws_s3_bucket.files.bucket}/files"
      EVIDENCE_LAB_PUBLIC_URL   = local.public_url
      AWS_REGION                = var.region
      # Only the load balancer can reach the task (security groups), so its forwarded headers are trusted.
      EVIDENCE_LAB_FORWARDED_ALLOW_IPS = "*"
    },
    local.github_enabled ? {
      EVIDENCE_LAB_GITHUB_CLIENT_ID     = var.github_client_id
      EVIDENCE_LAB_GITHUB_APP_SLUG      = var.github_app_slug
      EVIDENCE_LAB_GITHUB_ALLOWED_USERS = join(",", var.github_allowed_users)
      EVIDENCE_LAB_GITHUB_ALLOWED_ORGS  = join(",", var.github_allowed_orgs)
      EVIDENCE_LAB_GITHUB_ALLOW_ANYONE  = var.github_allow_anyone ? "on" : "off"
    } : {},
  )

  secrets = concat(
    [{ name = "EVIDENCE_LAB_DATABASE_PASSWORD", valueFrom = "${aws_db_instance.this.master_user_secret[0].secret_arn}:password::" }],
    [for s in aws_secretsmanager_secret.github_client_secret : { name = "EVIDENCE_LAB_GITHUB_CLIENT_SECRET", valueFrom = s.arn }],
  )
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.data.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.data.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([{
    name      = "app"
    image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential = true

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = [for k, v in local.environment : { name = k, value = v } if v != ""]
    secrets      = local.secrets
    mountPoints  = [{ sourceVolume = "data", containerPath = "/data", readOnly = false }]

    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "FARGATE"

  # Exactly one copy: the app keeps its running tests and its demo servers in its own process, and one data folder.
  # A deploy stops the old task before the new one starts (a short pause, never two at once).
  desired_count                      = 1
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  health_check_grace_period_seconds  = 90
  enable_execute_command             = false

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.http, aws_efs_mount_target.data]
}
