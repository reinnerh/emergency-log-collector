#!/usr/bin/env python3
import boto3, sys, logging, os, time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

ssm = boto3.client('ssm', region_name='sa-east-1')

def emergency_download(instance_id):
    """Download ultra-rápido de logs de uma instância específica"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    logging.info(f"🚨 EMERGÊNCIA: Coletando logs de {instance_id}")
    
    # Comando otimizado para velocidade
    command = f"""
    # Logs críticos apenas
    echo "=== EMERGENCY LOG COLLECTION ===" > /tmp/emergency.log
    echo "Instance: {instance_id}" >> /tmp/emergency.log
    echo "Time: $(date)" >> /tmp/emergency.log
    echo "Uptime: $(uptime)" >> /tmp/emergency.log
    echo "Memory: $(free -h | head -2)" >> /tmp/emergency.log
    echo "CPU: $(cat /proc/loadavg)" >> /tmp/emergency.log
    echo "Top processes:" >> /tmp/emergency.log
    ps aux --sort=-%cpu | head -5 >> /tmp/emergency.log
    echo "\\n=== CPU CHECK LOG ===" >> /tmp/emergency.log
    tail -50 /var/log/cpu_check.log >> /tmp/emergency.log 2>/dev/null || echo "cpu_check.log não encontrado" >> /tmp/emergency.log
    echo "\\n=== SYSLOG RECENT ===" >> /tmp/emergency.log
    tail -100 /var/log/syslog >> /tmp/emergency.log 2>/dev/null || echo "syslog não encontrado" >> /tmp/emergency.log
    
    # Retorna direto sem compactar (mais rápido)
    base64 /tmp/emergency.log
    """
    
    try:
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunShellScript',
            Parameters={'commands': [command]},
            TimeoutSeconds=60
        )
        
        command_id = response['Command']['CommandId']
        logging.info(f"Comando enviado, aguardando...")
        
        # Aguarda com timeout menor
        for i in range(20):  # 20 tentativas de 1s = 20s max
            time.sleep(1)
            result = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            
            if result['Status'] in ['Success', 'Failed']:
                break
            
            if i % 5 == 0:
                logging.info(f"Aguardando... ({i+1}s)")
        
        if result['Status'] == 'Success':
            # Decodifica e salva
            import base64
            log_content = base64.b64decode(result['StandardOutputContent']).decode('utf-8')
            
            filename = f"emergency_{instance_id}_{timestamp}.log"
            with open(filename, 'w') as f:
                f.write(log_content)
            
            logging.info(f"✅ SUCESSO! Logs salvos em: {filename}")
            
            # Mostra preview dos logs
            print("\\n" + "="*50)
            print("PREVIEW DOS LOGS:")
            print("="*50)
            print(log_content[:1000] + "..." if len(log_content) > 1000 else log_content)
            
        else:
            logging.error(f"❌ FALHOU: {result.get('StandardErrorContent', 'Erro desconhecido')}")
            
    except Exception as e:
        logging.error(f"❌ ERRO: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("🚨 USO EMERGÊNCIA:")
        print("  python3 emergency_logs.py i-1234567890abcdef0")
        print("\\nPara listar instâncias do ASG:")
        print("  aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names 'Plataforma Jornada' --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' --output text")
        sys.exit(1)
    
    emergency_download(sys.argv[1])