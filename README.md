# Sistema de Coleta de Logs de Emergência (Lambda + Lifecycle Hooks)

Lambda que coleta logs críticos antes da terminação de instâncias EC2 via ASG Lifecycle Hooks.

## 🚀 Funcionalidades

- **Lifecycle Hooks**: Intercepta terminação de instâncias EC2
- **Coleta Automática**: Extrai logs críticos via SSM
- **Armazenamento S3**: Backup seguro dos logs
- **Notificações SNS**: Alertas em tempo real

## 🛠️ Tecnologias

- AWS Lambda (Python)
- Auto Scaling Lifecycle Hooks
- Systems Manager (SSM)
- S3 para armazenamento
- SNS para notificações

## 📁 Arquivos

- `lambda_function.py` - Função Lambda principal
- `emergency_logs.py` - Script de coleta local
- `lifecycle_hook_setup.tf` - Infraestrutura Terraform

## 🔧 Deploy

```bash
terraform apply -var='asg_name=production-asg'
aws lambda invoke --function-name emergency-log-collector response.json
cat response.json | jq .statusCode
```
