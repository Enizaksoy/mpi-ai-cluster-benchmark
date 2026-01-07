#!/usr/bin/env python3
"""
MPI Bandwidth Stress Test - Saturate RDMA Links
Similar to rdma_aggressive_sshpass.py but using MPI collective operations

This generates continuous high-bandwidth MPI traffic to stress test
the RDMA network and trigger ECN/PFC.

Usage:
    ./mpi_bandwidth_stress.py start    - Start continuous stress test
    ./mpi_bandwidth_stress.py stop     - Stop all tests
    ./mpi_bandwidth_stress.py status   - Check if running
"""

import subprocess
import sys
import time
import os

# Configuration
MASTER = "192.168.11.152"
PASSWORD = "Versa@123!!"
HOSTFILE = "/home/versa/hostfile_rdma"

# MPI stress test script that runs on the master
MPI_STRESS_SCRIPT = '''#!/bin/bash
# MPI Bandwidth Stress Test - Runs continuously until stopped

HOSTFILE="/home/versa/hostfile_rdma"
OSU_PATH="/usr/local/libexec/osu-micro-benchmarks/mpi/collective"
LOGFILE="/tmp/mpi_stress.log"

# UCX settings for RDMA
export UCX_TLS=ud_verbs,self,sm
export UCX_NET_DEVICES=all

echo "Starting MPI Bandwidth Stress Test" > $LOGFILE
echo "Time: $(date)" >> $LOGFILE
echo "========================================" >> $LOGFILE

iteration=0
while true; do
    iteration=$((iteration + 1))
    echo "" >> $LOGFILE
    echo "=== Iteration $iteration - $(date) ===" >> $LOGFILE

    # Large message Allreduce - simulates gradient synchronization
    echo "Allreduce 4MB x1000..." >> $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \
        -x UCX_TLS -x UCX_NET_DEVICES \
        --mca pml ucx --mca btl ^openib,tcp \
        --mca btl_openib_warn_no_device_params_found 0 \
        $OSU_PATH/osu_allreduce -m 4194304:4194304 -i 1000 >> $LOGFILE 2>&1

    # Alltoall - heavy all-to-all communication
    echo "Alltoall 1MB x500..." >> $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \
        -x UCX_TLS -x UCX_NET_DEVICES \
        --mca pml ucx --mca btl ^openib,tcp \
        --mca btl_openib_warn_no_device_params_found 0 \
        $OSU_PATH/osu_alltoall -m 1048576:1048576 -i 500 >> $LOGFILE 2>&1

    # Broadcast large data
    echo "Broadcast 4MB x1000..." >> $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \
        -x UCX_TLS -x UCX_NET_DEVICES \
        --mca pml ucx --mca btl ^openib,tcp \
        --mca btl_openib_warn_no_device_params_found 0 \
        $OSU_PATH/osu_bcast -m 4194304:4194304 -i 1000 >> $LOGFILE 2>&1

    # Allgather - gather from all nodes
    echo "Allgather 2MB x500..." >> $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \
        -x UCX_TLS -x UCX_NET_DEVICES \
        --mca pml ucx --mca btl ^openib,tcp \
        --mca btl_openib_warn_no_device_params_found 0 \
        $OSU_PATH/osu_allgather -m 2097152:2097152 -i 500 >> $LOGFILE 2>&1

    echo "Iteration $iteration complete" >> $LOGFILE

    # Brief pause between iterations
    sleep 2
done
'''

def run_ssh_script(script_content, description="SSH command"):
    """Run SSH command using script file (more reliable)"""
    script_path = "/tmp/mpi_ssh_cmd.sh"

    # Write script file
    with open(script_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(f"ip={MASTER}\n")
        f.write(f"sshpass -p '{PASSWORD}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 versa@$ip '\n")
        f.write(script_content)
        f.write("\n'\n")

    # Fix line endings and make executable
    subprocess.run(["sed", "-i", "s/\r$//", script_path], capture_output=True)
    os.chmod(script_path, 0o755)

    # Run script
    try:
        result = subprocess.run(
            [script_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "Command timed out", 1
    except Exception as e:
        return f"Error: {e}", 1

def is_running():
    """Check if stress test is running - returns (bool, pid_list)"""
    script = '''
pgrep -x -f "/home/versa/mpi_stress_test.sh" 2>/dev/null || pgrep -f "^/bin/bash /home/versa/mpi_stress" 2>/dev/null
'''
    output, code = run_ssh_script(script)
    pids = [p for p in output.split('\n') if p.strip().isdigit()]
    return len(pids) > 0, pids

def start_stress_test():
    """Start the MPI bandwidth stress test"""
    print("Starting MPI Bandwidth Stress Test...")
    print("This will saturate your RDMA links with continuous MPI traffic")
    print()

    # Check if already running
    running, pids = is_running()
    if running:
        print(f"Stress test already running! PIDs: {', '.join(pids)}")
        print("Use './mpi_bandwidth_stress.py stop' first to restart")
        return

    # Create the stress test script on the server
    print("Deploying stress test script...")

    # Write script to temp file locally
    with open("/tmp/mpi_stress_test.sh", "w") as f:
        f.write(MPI_STRESS_SCRIPT)

    # Fix line endings
    subprocess.run(["sed", "-i", "s/\r$//", "/tmp/mpi_stress_test.sh"], capture_output=True)

    # Copy to server using script
    scp_script = f"""#!/bin/bash
sshpass -p '{PASSWORD}' scp -o StrictHostKeyChecking=no /tmp/mpi_stress_test.sh versa@{MASTER}:/home/versa/
"""
    with open("/tmp/mpi_scp.sh", "w") as f:
        f.write(scp_script)
    subprocess.run(["sed", "-i", "s/\r$//", "/tmp/mpi_scp.sh"], capture_output=True)
    os.chmod("/tmp/mpi_scp.sh", 0o755)
    subprocess.run(["/tmp/mpi_scp.sh"], capture_output=True)

    # Make executable and start
    start_script = '''
chmod +x /home/versa/mpi_stress_test.sh
rm -f /tmp/mpi_stress.log
nohup /home/versa/mpi_stress_test.sh > /dev/null 2>&1 &
sleep 3
pgrep -f "mpi_stress_test.sh" || echo "FAILED"
'''
    output, code = run_ssh_script(start_script, "Start stress test")

    time.sleep(2)

    # Verify it started
    running, pids = is_running()
    if running:
        print()
        print("=" * 50)
        print("MPI Bandwidth Stress Test STARTED")
        print("=" * 50)
        print(f"PIDs: {', '.join(pids)}")
        print()
        print("Traffic pattern:")
        print("  - Allreduce 4MB x 1000 iterations")
        print("  - Alltoall 1MB x 500 iterations")
        print("  - Broadcast 4MB x 1000 iterations")
        print("  - Allgather 2MB x 500 iterations")
        print("  - Repeats continuously")
        print()
        print("Monitor with:")
        print("  ./mpi_bandwidth_stress.py status")
        print("  ./mpi_bandwidth_stress.py log")
        print()
        print("Stop with:")
        print("  ./mpi_bandwidth_stress.py stop")
    else:
        print("Failed to start stress test")
        print("Check log: ./mpi_bandwidth_stress.py log")

def stop_stress_test():
    """Stop all MPI stress tests"""
    print("Stopping MPI Bandwidth Stress Test...")

    stop_script = '''
pkill -9 -f "mpi_stress_test.sh" 2>/dev/null
pkill -9 -f "mpirun.*osu_" 2>/dev/null
sleep 2
pgrep -f "mpi_stress_test.sh" 2>/dev/null || echo "STOPPED"
'''
    output, code = run_ssh_script(stop_script, "Stop stress test")

    if "STOPPED" in output:
        print("MPI Bandwidth Stress Test STOPPED")
    else:
        print("Warning: Some processes may still be running")
        print(f"Output: {output}")

def show_status():
    """Show status of stress test"""
    print("MPI Bandwidth Stress Test Status")
    print("=" * 50)

    running, pids = is_running()

    if running:
        print(f"Status: RUNNING (PIDs: {', '.join(pids)})")

        # Show current MPI processes
        status_script = '''
echo "Active mpirun: $(pgrep -f mpirun | wc -l)"
echo ""
echo "Recent activity:"
echo "----------------------------------------"
tail -20 /tmp/mpi_stress.log 2>/dev/null || echo "No log file"
'''
        output, code = run_ssh_script(status_script, "Get status")
        print(output)
    else:
        print("Status: NOT RUNNING")
        print()
        print("Start with: ./mpi_bandwidth_stress.py start")

def show_log():
    """Show live log output"""
    print("MPI Stress Test Log (last 50 lines):")
    print("=" * 50)

    log_script = '''
tail -50 /tmp/mpi_stress.log 2>/dev/null || echo "No log file found"
'''
    output, code = run_ssh_script(log_script, "Get log")
    print(output)

def main():
    if len(sys.argv) < 2:
        print("MPI Bandwidth Stress Test")
        print()
        print("Usage:")
        print("  ./mpi_bandwidth_stress.py start   - Start continuous stress test")
        print("  ./mpi_bandwidth_stress.py stop    - Stop stress test")
        print("  ./mpi_bandwidth_stress.py status  - Check status")
        print("  ./mpi_bandwidth_stress.py log     - Show recent log")
        print()
        print("This generates continuous high-bandwidth MPI traffic")
        print("similar to rdma_aggressive_sshpass.py but using MPI collectives.")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "start":
        start_stress_test()
    elif command == "stop":
        stop_stress_test()
    elif command == "status":
        show_status()
    elif command == "log":
        show_log()
    else:
        print(f"Unknown command: {command}")
        print("Use: start, stop, status, or log")
        sys.exit(1)

if __name__ == "__main__":
    main()
