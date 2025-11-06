# Auto Scaling Lifecycle Hook para capturar logs antes da terminação
resource "aws_autoscaling_lifecycle_hook" "instance_terminating" {
  name                 = "capture-logs-before-termination"
  autoscaling_group_name = "your-asg-name"  # Substitua pelo nome do seu ASG
  default_result       = "ABANDON"
  heartbeat_timeout    = 300  # 5 minutos para coletar logs
  lifecycle_transition = "autoscaling:EC2_INSTANCE_TERMINATING"
  
  notification_target_arn = aws_sns_topic.lifecycle_notifications.arn
  role_arn               = aws_iam_role.lifecycle_hook_role.arn
}

# SNS Topic para notificações do lifecycle hook
resource "aws_sns_topic" "lifecycle_notifications" {
  name = "asg-lifecycle-notifications"
}

# Subscription do SNS para Lambda
resource "aws_sns_topic_subscription" "lifecycle_lambda" {
  topic_arn = aws_sns_topic.lifecycle_notifications.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.emergency_log_collector.arn
}

# IAM Role para o Lifecycle Hook
resource "aws_iam_role" "lifecycle_hook_role" {
  name = "asg-lifecycle-hook-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "autoscaling.amazonaws.com"
        }
      }
    ]
  })
}

# Policy para o Lifecycle Hook
resource "aws_iam_role_policy" "lifecycle_hook_policy" {
  name = "lifecycle-hook-policy"
  role = aws_iam_role.lifecycle_hook_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.lifecycle_notifications.arn
      }
    ]
  })
}

# Lambda Function para coleta de emergência
resource "aws_lambda_function" "emergency_log_collector" {
  filename         = "emergency_log_collector.zip"
  function_name    = "emergency-log-collector"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.9"
  timeout         = 240  # 4 minutos (deixa 1 minuto de margem)

  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.emergency_logs.bucket
    }
  }
}

# S3 Bucket para armazenar logs de emergência
resource "aws_s3_bucket" "emergency_logs" {
  bucket = "emergency-logs-${random_string.bucket_suffix.result}"
}

resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# IAM Role para Lambda
resource "aws_iam_role" "lambda_execution_role" {
  name = "emergency-log-collector-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Policy para Lambda
resource "aws_iam_role_policy" "lambda_policy" {
  name = "emergency-log-collector-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:SendCommand",
          "ssm:GetCommandInvocation",
          "ssm:ListCommandInvocations"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.emergency_logs.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:CompleteLifecycleAction"
        ]
        Resource = "*"
      }
    ]
  })
}

# Permission para SNS invocar Lambda
resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.emergency_log_collector.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.lifecycle_notifications.arn
}
