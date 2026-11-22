# ---- PostgreSQL (RDS). The master password is made and rotated by RDS in Secrets Manager; the app gets it as
# EVIDENCE_LAB_DATABASE_PASSWORD and never sees it in a URL or in the Terraform state.

resource "aws_db_subnet_group" "this" {
  name       = local.name
  subnet_ids = module.vpc.private_subnets
}

resource "aws_db_parameter_group" "this" {
  name   = local.name
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "this" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name                     = "evidence_lab"
  username                    = "evidence_lab"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  parameter_group_name   = aws_db_parameter_group.this.name
  vpc_security_group_ids = [aws_security_group.data.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period    = 7
  auto_minor_version_upgrade = true
  deletion_protection        = var.protect_data
  skip_final_snapshot        = !var.protect_data
  final_snapshot_identifier  = var.protect_data ? "${local.name}-final" : null
  copy_tags_to_snapshot      = true
}

# ---- Redis (ElastiCache), TLS in transit; reachable from the app only. It holds only the one-time login state.

resource "aws_elasticache_subnet_group" "this" {
  name       = local.name
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = local.name
  description          = "Evidence Lab cache"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  num_cache_clusters   = 1
  port                 = 6379

  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.data.id]
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  automatic_failover_enabled = false
}

# ---- S3: copies of scanner files and evidence downloads. Private, encrypted, versioned.

resource "aws_s3_bucket" "files" {
  bucket_prefix = "${local.name}-files-"
  force_destroy = !var.protect_data
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "files_tls_only" {
  bucket = aws_s3_bucket.files.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "TLSOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.files.arn, "${aws_s3_bucket.files.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.files]
}

# ---- EFS: the app's data folder (/data). It holds the key that signs evidence files, the demo test certificate and
# the connected demo repositories; on Fargate's own disk they would be made anew at every restart, and evidence
# downloaded before would no longer check against "this app's key".

resource "aws_efs_file_system" "data" {
  creation_token   = "${local.name}-data"
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"
}

resource "aws_efs_backup_policy" "data" {
  file_system_id = aws_efs_file_system.data.id
  backup_policy {
    status = var.protect_data ? "ENABLED" : "DISABLED"
  }
}

resource "aws_efs_mount_target" "data" {
  for_each        = { for i, s in module.vpc.private_subnets : i => s }
  file_system_id  = aws_efs_file_system.data.id
  subnet_id       = each.value
  security_groups = [aws_security_group.data.id]
}

# The container runs as uid 10001 (Dockerfile, user "lab").
resource "aws_efs_access_point" "data" {
  file_system_id = aws_efs_file_system.data.id

  posix_user {
    uid = 10001
    gid = 10001
  }

  root_directory {
    path = "/evidence-lab"
    creation_info {
      owner_uid   = 10001
      owner_gid   = 10001
      permissions = "0700"
    }
  }
}
