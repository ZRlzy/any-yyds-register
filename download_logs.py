"""Download log files from server."""
import paramiko
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOST = '10.1.202.16'
USER = 'ubuntu'
PASSWORD = '1234'
REMOTE_DIR = '/home/ubuntu/any-auto-register'
LOCAL_DIR = r'g:\MyProject\any-auto-register\server_logs'

def ssh_exec(command, timeout=60):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    client.close()
    return exit_code, out, err

def find_log_files():
    """Find all log files on server."""
    patterns = ['*.log', 'logs/*', 'data/*.log']
    log_files = []
    
    for pattern in patterns:
        exit_code, out, err = ssh_exec(f"find {REMOTE_DIR} -name '{pattern}' -type f 2>/dev/null")
        if out.strip():
            log_files.extend(out.strip().split('\n'))
    
    return [f for f in log_files if f]

def download_file(sftp, remote_path, local_path):
    """Download a single file."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    sftp.get(remote_path, local_path)

def main():
    os.makedirs(LOCAL_DIR, exist_ok=True)
    
    print("=" * 60)
    print("  Finding log files on server...")
    print("=" * 60)
    
    log_files = find_log_files()
    
    if not log_files:
        print("No log files found in project directory.")
    else:
        print(f"Found {len(log_files)} log file(s):")
        for f in log_files:
            print(f"  - {f}")
        
        print("\n" + "=" * 60)
        print("  Downloading log files...")
        print("=" * 60)
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        sftp = client.open_sftp()
        
        downloaded = 0
        for remote_path in log_files:
            try:
                rel_path = remote_path.replace(REMOTE_DIR + '/', '')
                local_path = os.path.join(LOCAL_DIR, rel_path.replace('/', os.sep))
                download_file(sftp, remote_path, local_path)
                downloaded += 1
                print(f"  Downloaded: {rel_path}")
            except Exception as e:
                print(f"  Error downloading {remote_path}: {e}")
        
        sftp.close()
        client.close()
        print(f"\n  Total downloaded: {downloaded} file(s)")
    
    # Capture docker container logs
    print("\nCapturing docker container logs...")
    exit_code, out, err = ssh_exec("docker logs any-auto-register-app 2>&1 | tail -3000")
    if out:
        docker_log_path = os.path.join(LOCAL_DIR, 'docker_container.log')
        with open(docker_log_path, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f"  Saved docker logs to: {docker_log_path}")
    
    print(f"\n  All logs saved to: {LOCAL_DIR}")
    print("=" * 60)
    print("  Download complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()
