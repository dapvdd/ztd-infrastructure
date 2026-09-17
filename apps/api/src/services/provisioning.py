import secrets
import logging
import paramiko
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import SessionLocal
from src.models import Device, DeploymentLog
from src.config import settings

logger = logging.getLogger("provisioning")

def log_stage(db: Session, device: Device, stage: str, status: str, output: str = None):
    log_entry = DeploymentLog(
        device_id=device.id,
        stage=stage,
        status=status,
        log_output=output
    )
    db.add(log_entry)
    db.commit()

def run_remote_command(ssh_client, cmd: str, sudo_pass: str = None) -> tuple[int, str, str]:
    """Execute a command over SSH and capture exit status, stdout, and stderr."""
    stdin, stdout, stderr = ssh_client.exec_command(cmd, get_pty=True)
    if sudo_pass and "sudo" in cmd:
        stdin.write(f"{sudo_pass}\n")
        stdin.flush()
    
    exit_status = stdout.channel.recv_exit_status()
    out_text = stdout.read().decode().strip()
    err_text = stderr.read().decode().strip()
    return exit_status, out_text, err_text

def execute_provisioning(device_id: UUID, ip_address: str, ssh_password: str, ssh_port: int, mqtt_host: str):
    """
    Connects to the Raspberry Pi over SSH, verifies hardware MAC, 
    generates token, installs edge agent, and starts systemd service.
    """
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            logger.error(f"Device with ID {device_id} not found.")
            return False, "Device not found."
        device.status = "PROVISIONING"
        device.ip_address = ip_address
        db.commit()
        log_stage(db, device, "SSH_CONNECT", "STARTED", f"Connecting to {device.ssh_user}@{ip_address}:{ssh_port}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=ip_address,
                port=ssh_port,
                username=device.ssh_user,
                password=ssh_password,
                timeout=10,
                look_for_keys=False
            )
            log_stage(db, device, "SSH_CONNECT", "SUCCESS", "SSH connection established successfully.")
        except Exception as e:
            err_msg = f"Failed to connect via SSH: {str(e)}"
            logger.error(err_msg)
            device.status = "FAILED"
            log_stage(db, device, "SSH_CONNECT", "FAILED", err_msg)
            return False, err_msg
        try:
            # 1. HARDWARE MAC VERIFICATION
            code, out, _ = run_remote_command(ssh_client=client, cmd="cat /sys/class/net/eth0/address || cat /sys/class/net/wlan0/address")
            physical_mac = out.strip().lower()
            if physical_mac != device.mac_address.lower():
                err_msg = f"MAC verification failed! Whitelist: {device.mac_address}, Physical on device: {physical_mac}"
                log_stage(db, device, "MAC_VERIFY", "FAILED", err_msg)
                device.status = "REVOKED"
                db.commit()
                client.close()
                return False, err_msg
            log_stage(db, device, "MAC_VERIFY", "SUCCESS", f"Physical MAC '{physical_mac}' matches whitelist.")
            # 2. GENERATE CRYPTOGRAPHIC DEVICE TOKEN
            if not device.device_token:
                device.device_token = f"ztd_tok_{secrets.token_hex(16)}"
                db.commit()
            
            log_stage(db, device, "TOKEN_CHECK", "SUCCESS", f"Using pre-assigned token: {device.device_token[:12]}...")

            # 3. TRANSFER AGENT CODE TO PI
            sftp = client.open_sftp()
            run_remote_command(client, "mkdir -p /tmp/iot-agent", ssh_password)
            
            sftp.put("/app/agent/agent.py", "/tmp/iot-agent/agent.py")
            sftp.put("/app/agent/requirements.txt", "/tmp/iot-agent/requirements.txt")
            sftp.put("/app/agent/iot-agent.service", "/tmp/iot-agent/iot-agent.service")
            sftp.close()
            # 4. INSTALL DIRECTORIES & WRITE /etc/iot-agent/config.env
            target_mqtt_host = mqtt_host or settings.SERVER_HOST
            setup_cmds = f"""
        echo '{ssh_password}' | sudo -S mkdir -p /opt/iot-agent /etc/iot-agent
        echo '{ssh_password}' | sudo -S cp /tmp/iot-agent/agent.py /opt/iot-agent/agent.py
        echo '{ssh_password}' | sudo -S cp /tmp/iot-agent/requirements.txt /opt/iot-agent/requirements.txt
        echo '{ssh_password}' | sudo -S cp /tmp/iot-agent/iot-agent.service /etc/systemd/system/iot-agent.service
        # Write environment config with the pre-assigned token & server IP
        echo '{ssh_password}' | sudo -S bash -c 'cat <<EOF > /etc/iot-agent/config.env
DEVICE_TOKEN={device.device_token}
MQTT_HOST={target_mqtt_host}
MQTT_PORT=1883
HEARTBEAT_INTERVAL=30
EOF'
        # Set permissions, create virtualenv, install dependencies, and start service
        echo '{ssh_password}' | sudo -S chown -R {device.ssh_user}:{device.ssh_user} /opt/iot-agent
        python3 -m venv /opt/iot-agent/venv
        /opt/iot-agent/venv/bin/pip install --quiet -r /opt/iot-agent/requirements.txt
        echo '{ssh_password}' | sudo -S systemctl daemon-reload
        echo '{ssh_password}' | sudo -S systemctl enable --now iot-agent.service
        """
            
            code, out, err = run_remote_command(client, setup_cmds, ssh_password)
            log_stage(db, device, "DEPLOY_SERVICE", "SUCCESS" if code == 0 else "FAILED", f"Output: {out}\nErrors: {err}")
            if code == 0:
                device.status = "PROVISIONED"
                device.provisioned_at = datetime.now(timezone.utc)
                db.commit()
                return True, "Provisioning succeeded. Service installed and running."
            else:
                device.status = "FAILED"
                db.commit()
                return False, f"Setup script failed with exit code {code}."
        except Exception as e:
            err_msg = f"Unexpected error during provisioning: {str(e)}"
            device.status = "FAILED"
            log_stage(db, device, "PROVISIONING", "FAILED", err_msg)
            return False, err_msg
        finally:
            client.close()
    finally:
        db.close()

