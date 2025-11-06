import json
import boto3
import os
import time
from datetime import datetime

def lambda_handler(event, context):
    """
    Lambda function para coletar logs de emergência antes da terminação de instâncias
    Baseado no nosso trabalho anterior de monitoramento PHP-FPM
    """
    
    # Clientes AWS
    ssm_client = boto3.client('ssm')
    s3_client = boto3.client('s3')
    asg_client = boto3.client('autoscaling')
    ec2_client = boto3.client('ec2')
    
    # Parse da mensagem SNS
    try:
        sns_message = json.loads(event['Records'][0]['Sns']['Message'])
        instance_id = sns_message['EC2InstanceId']
        lifecycle_hook_name = sns_message['LifecycleHookName']
        auto_scaling_group_name = sns_message['AutoScalingGroupName']
        lifecycle_action_token = sns_message['LifecycleActionToken']
        
        print(f"Processando terminação de emergência para instância: {instance_id}")
        
    except Exception as e:
        print(f"Erro ao processar mensagem SNS: {str(e)}")
        return {'statusCode': 400, 'body': 'Erro no parse da mensagem'}
    
    # Verificar se a instância ainda está acessível
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance_state = response['Reservations'][0]['Instances'][0]['State']['Name']
        
        if instance_state not in ['running', 'stopping']:
            print(f"Instância {instance_id} não está em estado válido: {instance_state}")
            complete_lifecycle_action(asg_client, lifecycle_hook_name, auto_scaling_group_name, 
                                    instance_id, lifecycle_action_token, 'CONTINUE')
            return {'statusCode': 200, 'body': 'Instância não acessível'}
            
    except Exception as e:
        print(f"Erro ao verificar estado da instância: {str(e)}")
        complete_lifecycle_action(asg_client, lifecycle_hook_name, auto_scaling_group_name, 
                                instance_id, lifecycle_action_token, 'CONTINUE')
        return {'statusCode': 500, 'body': 'Erro ao verificar instância'}
    
    # Script de coleta de emergência (baseado no nosso monitor_php_fpm.py)
    emergency_script = """#!/bin/bash
set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TEMP_DIR="/tmp/emergency_logs_${TIMESTAMP}"
mkdir -p "$TEMP_DIR"

echo "=== COLETA DE EMERGÊNCIA - $(date) ===" > "$TEMP_DIR/emergency_info.txt"
echo "Instância sendo terminada: $(curl -s http://169.254.169.254/latest/meta-data/instance-id)" >> "$TEMP_DIR/emergency_info.txt"
echo "Motivo: Auto Scaling Group Termination" >> "$TEMP_DIR/emergency_info.txt"
echo "" >> "$TEMP_DIR/emergency_info.txt"

# Informações críticas do sistema
echo "=== LOAD AVERAGE ===" >> "$TEMP_DIR/system_critical.txt"
uptime >> "$TEMP_DIR/system_critical.txt"
echo "" >> "$TEMP_DIR/system_critical.txt"

echo "=== MEMORY USAGE ===" >> "$TEMP_DIR/system_critical.txt"
free -h >> "$TEMP_DIR/system_critical.txt"
echo "" >> "$TEMP_DIR/system_critical.txt"

echo "=== DISK USAGE ===" >> "$TEMP_DIR/system_critical.txt"
df -h >> "$TEMP_DIR/system_critical.txt"
echo "" >> "$TEMP_DIR/system_critical.txt"

# PHP-FPM Status Crítico
echo "=== PHP-FPM PROCESSES ===" >> "$TEMP_DIR/php_fpm_critical.txt"
ps aux | grep -E "(php-fpm|nginx)" | grep -v grep >> "$TEMP_DIR/php_fpm_critical.txt" 2>/dev/null || echo "Nenhum processo PHP-FPM encontrado" >> "$TEMP_DIR/php_fpm_critical.txt"
echo "" >> "$TEMP_DIR/php_fpm_critical.txt"

echo "=== PHP-FPM PROCESS COUNT ===" >> "$TEMP_DIR/php_fpm_critical.txt"
ps aux | grep php-fpm | grep -v grep | wc -l >> "$TEMP_DIR/php_fpm_critical.txt" 2>/dev/null || echo "0" >> "$TEMP_DIR/php_fpm_critical.txt"
echo "" >> "$TEMP_DIR/php_fpm_critical.txt"

# Últimas linhas dos logs críticos
echo "=== ÚLTIMAS 100 LINHAS - NGINX ERROR ===" > "$TEMP_DIR/nginx_error_tail.txt"
tail -100 /var/log/nginx/error.log >> "$TEMP_DIR/nginx_error_tail.txt" 2>/dev/null || echo "Log não encontrado" >> "$TEMP_DIR/nginx_error_tail.txt"

echo "=== ÚLTIMAS 100 LINHAS - PHP-FPM ERROR ===" > "$TEMP_DIR/php_fpm_error_tail.txt"
tail -100 /var/log/php-fpm/www-error.log >> "$TEMP_DIR/php_fpm_error_tail.txt" 2>/dev/null || echo "Log não encontrado" >> "$TEMP_DIR/php_fpm_error_tail.txt"

echo "=== ÚLTIMAS 50 LINHAS - SYSLOG ===" > "$TEMP_DIR/syslog_tail.txt"
tail -50 /var/log/syslog >> "$TEMP_DIR/syslog_tail.txt" 2>/dev/null || tail -50 /var/log/messages >> "$TEMP_DIR/syslog_tail.txt" 2>/dev/null || echo "Syslog não encontrado" >> "$TEMP_DIR/syslog_tail.txt"

# Configuração PHP-FPM atual
echo "=== PHP-FPM POOL CONFIG ===" > "$TEMP_DIR/php_fpm_config.txt"
cat /etc/php-fpm.d/www.conf >> "$TEMP_DIR/php_fpm_config.txt" 2>/dev/null || echo "Config não encontrada" >> "$TEMP_DIR/php_fpm_config.txt"

# Conexões de rede ativas
echo "=== CONEXÕES ATIVAS ===" > "$TEMP_DIR/network_connections.txt"
netstat -tuln >> "$TEMP_DIR/network_connections.txt" 2>/dev/null || ss -tuln >> "$TEMP_DIR/network_connections.txt" 2>/dev/null || echo "Comando não disponível" >> "$TEMP_DIR/network_connections.txt"

# Criar arquivo TAR (sem compressão para compatibilidade)
cd /tmp
tar -cf "emergency_logs_${TIMESTAMP}.tar" "emergency_logs_${TIMESTAMP}/"

echo "emergency_logs_${TIMESTAMP}.tar"
"""
    
    try:
        # Executar coleta de emergência
        print(f"Iniciando coleta de emergência na instância {instance_id}")
        
        command_response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunShellScript',
            Parameters={
                'commands': [emergency_script],
                'executionTimeout': ['180']  # 3 minutos
            },
            TimeoutSeconds=200
        )
        
        command_id = command_response['Command']['CommandId']
        
        # Aguardar conclusão
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                result = ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )
                
                status = result['Status']
                if status == 'Success':
                    output = result['StandardOutputContent']
                    tar_filename = output.strip().split('\n')[-1]
                    
                    # Download do arquivo TAR
                    download_command = f"cat /tmp/{tar_filename}"
                    download_response = ssm_client.send_command(
                        InstanceIds=[instance_id],
                        DocumentName='AWS-RunShellScript',
                        Parameters={'commands': [download_command]},
                        TimeoutSeconds=60
                    )
                    
                    time.sleep(5)
                    
                    download_result = ssm_client.get_command_invocation(
                        CommandId=download_response['Command']['CommandId'],
                        InstanceId=instance_id
                    )
                    
                    if download_result['Status'] == 'Success':
                        # Upload para S3
                        s3_key = f"emergency-logs/{instance_id}/{datetime.now().strftime('%Y/%m/%d')}/{tar_filename}"
                        
                        # Nota: Em produção, você precisaria de uma abordagem diferente para transferir o arquivo binário
                        # Esta é uma versão simplificada que salva os metadados
                        emergency_metadata = {
                            'instance_id': instance_id,
                            'termination_time': datetime.now().isoformat(),
                            'asg_name': auto_scaling_group_name,
                            'collection_status': 'success',
                            'tar_filename': tar_filename
                        }
                        
                        s3_client.put_object(
                            Bucket=os.environ['S3_BUCKET'],
                            Key=f"emergency-logs/{instance_id}/metadata.json",
                            Body=json.dumps(emergency_metadata, indent=2),
                            ContentType='application/json'
                        )
                        
                        print(f"Logs de emergência coletados com sucesso para {instance_id}")
                        break
                    
                elif status in ['Failed', 'Cancelled', 'TimedOut']:
                    print(f"Coleta falhou com status: {status}")
                    break
                    
            except Exception as e:
                print(f"Erro na tentativa {attempt + 1}: {str(e)}")
                
            time.sleep(5)
        
    except Exception as e:
        print(f"Erro durante coleta de emergência: {str(e)}")
    
    finally:
        # Sempre completar o lifecycle action para não bloquear o ASG
        complete_lifecycle_action(asg_client, lifecycle_hook_name, auto_scaling_group_name, 
                                instance_id, lifecycle_action_token, 'CONTINUE')
    
    return {
        'statusCode': 200,
        'body': json.dumps(f'Processamento de emergência concluído para {instance_id}')
    }

def complete_lifecycle_action(asg_client, hook_name, asg_name, instance_id, token, result):
    """Completa a ação do lifecycle hook"""
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hook_name,
            AutoScalingGroupName=asg_name,
            InstanceId=instance_id,
            LifecycleActionToken=token,
            LifecycleActionResult=result
        )
        print(f"Lifecycle action completada: {result}")
    except Exception as e:
        print(f"Erro ao completar lifecycle action: {str(e)}")
