# The load balancer. With domain_name and route53_zone_id: HTTPS with an ACM certificate, and HTTP redirects to it.
# Without: plain HTTP on the load balancer's own name (fine to try it; not for real data).

resource "aws_lb" "app" {
  name                       = local.name
  load_balancer_type         = "application"
  subnets                    = module.vpc.public_subnets
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  idle_timeout               = 120
}

resource "aws_lb_target_group" "app" {
  name                 = local.name
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = module.vpc.vpc_id
  deregistration_delay = 30

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_acm_certificate" "app" {
  count             = local.https ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  # Keyed by the domain (known before apply); the record's values come from the certificate.
  for_each = local.https ? toset([var.domain_name]) : toset([])
  zone_id  = var.route53_zone_id
  name     = one([for o in aws_acm_certificate.app[0].domain_validation_options : o.resource_record_name if o.domain_name == each.key])
  type     = one([for o in aws_acm_certificate.app[0].domain_validation_options : o.resource_record_type if o.domain_name == each.key])
  records  = [one([for o in aws_acm_certificate.app[0].domain_validation_options : o.resource_record_value if o.domain_name == each.key])]
  ttl      = 300
}

resource "aws_acm_certificate_validation" "app" {
  count                   = local.https ? 1 : 0
  certificate_arn         = aws_acm_certificate.app[0].arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = local.https ? "redirect" : "forward"
    target_group_arn = local.https ? null : aws_lb_target_group.app.arn

    dynamic "redirect" {
      for_each = local.https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = local.https ? 1 : 0
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.app[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_route53_record" "app" {
  count   = local.https ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}
