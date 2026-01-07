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

echo "Starting MPI Bandwidth Stress Test" | tee $LOGFILE
echo "Time: $(date)" | tee -a $LOGFILE
echo "========================================" | tee -a $LOGFILE

iteration=0
while true; do
    iteration=$((iteration + 1))
    echo "" | tee -a $LOGFILE
    echo "=== Iteration $iteration - $(date) ===" | tee -a $LOGFILE

    # Large message Allreduce - simulates gradient synchronization
    echo "Running Allreduce 4MB (gradient sync simulation)..." | tee -a $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \\
        -x UCX_TLS -x UCX_NET_DEVICES \\
        --mca pml ucx --mca btl ^openib,tcp \\
        --mca btl_openib_warn_no_device_params_found 0 \\
        $OSU_PATH/osu_allreduce -m 4194304:4194304 -i 1000 2>&1 | tee -a $LOGFILE

    # Alltoall - heavy all-to-all communication
    echo "Running Alltoall 1MB (all-to-all exchange)..." | tee -a $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \\
        -x UCX_TLS -x UCX_NET_DEVICES \\
        --mca pml ucx --mca btl ^openib,tcp \\
        --mca btl_openib_warn_no_device_params_found 0 \\
        $OSU_PATH/osu_alltoall -m 1048576:1048576 -i 500 2>&1 | tee -a $LOGFILE

    # Broadcast large data
    echo "Running Broadcast 4MB (parameter distribution)..." | tee -a $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \\
        -x UCX_TLS -x UCX_NET_DEVICES \\
        --mca pml ucx --mca btl ^openib,tcp \\
        --mca btl_openib_warn_no_device_params_found 0 \\
        $OSU_PATH/osu_bcast -m 4194304:4194304 -i 1000 2>&1 | tee -a $LOGFILE

    # Allgather - gather from all nodes
    echo "Running Allgather 2MB..." | tee -a $LOGFILE
    mpirun --hostfile $HOSTFILE -np 8 \\
        -x UCX_TLS -x UCX_NET_DEVICES \\
        --mca pml ucx --mca btl ^openib,tcp \\
        --mca btl_openib_warn_no_device_params_found 0 \\
        $OSU_PATH/osu_allgather -m 2097152:2097152 -i 500 2>&1 | tee -a $LOGFILE

    # Multi-pair bandwidth test if available
    if [ -f "$OSU_PATH/osu_mbw_mr" ]; then
        echo "Running Multi-pair Bandwidth..." | tee -a $LOGFILE
        mpirun --hostfile $HOSTFILE -np 8 \\
            -x UCX_TLS -x UCX_NET_DEVICES \\
            --mca pml ucx --mca btl ^openib,tcp \\
            $OSU_PATH/osu_mbw_mr 2>&1 | tail -5 | tee -a $LOGFILE
    fi

    echo "Iteration $iteration complete" | tee -a $LOGFILE

    # Brief pause between iterations
    sleep 2
done
'''

def ssh_command(cmd, timeout=30):
    """Run SSH command on master server"""
    full_cmd = f"sshpass -p '{PASSWORD}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 versa@{MASTER} \"{cmd}\""
    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error: {e}"

def start_stress_test():
    """Start the MPI bandwidth stress test"""
    print("Starting MPI Bandwidth Stress Test...")
    print("This will saturate your RDMA links with continuous MPI traffic")
    print()

    # Check if already running
    output = ssh_command("pgrep -f 'mpi_stress_test.sh' || echo 'not running'")
    if "not running" not in output and output.strip():
        print("Stress test already running!")
        print(f"PIDs: {output.strip()}")
        return

    # Create the stress test script on the server
    print("Deploying stress test script...")

    # Write script to temp file locally, then scp
    with open("/tmp/mpi_stress_test.sh", "w") as f:
        f.write(MPI_STRESS_SCRIPT)

    # Fix line endings
    subprocess.run(["sed", "-i", "s/\r$//", "/tmp/mpi_stress_test.sh"])

    # Copy to server
    scp_cmd = f"sshpass -p '{PASSWORD}' scp -o StrictHostKeyChecking=no /tmp/mpi_stress_test.sh versa@{MASTER}:/home/versa/"
    subprocess.run(scp_cmd, shell=True)

    # Make executable and start
    ssh_command("chmod +x /home/versa/mpi_stress_test.sh")

    print("Starting continuous MPI stress test...")
    # Start in background with nohup
    ssh_command("nohup /home/versa/mpi_stress_test.sh > /tmp/mpi_stress.log 2>&1 &", timeout=5)

    time.sleep(3)

    # Verify it started
    output = ssh_command("pgrep -f 'mpi_stress_test.sh'")
    if output.strip():
        print()
        print("=" * 50)
        print("MPI Bandwidth Stress Test STARTED")
        print("=" * 50)
        print(f"PID: {output.strip()}")
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
        print("Check log: ssh versa@192.168.11.152 'cat /tmp/mpi_stress.log'")

def stop_stress_test():
    """Stop all MPI stress tests"""
    print("Stopping MPI Bandwidth Stress Test...")

    # Kill the stress test script
    ssh_command("pkill -f 'mpi_stress_test.sh'")

    # Kill any running mpirun processes from stress test
    ssh_command("pkill -f 'mpirun.*osu_'")

    time.sleep(2)

    # Verify stopped
    output = ssh_command("pgrep -f 'mpi_stress_test.sh' || echo 'stopped'")
    if "stopped" in output:
        print("MPI Bandwidth Stress Test STOPPED")
    else:
        print("Warning: Some processes may still be running")
        print(f"PIDs: {output}")

def show_status():
    """Show status of stress test"""
    print("MPI Bandwidth Stress Test Status")
    print("=" * 50)

    # Check if running
    output = ssh_command("pgrep -f 'mpi_stress_test.sh'")
    if output.strip():
        print(f"Status: RUNNING (PID: {output.strip()})")

        # Show current MPI processes
        mpi_procs = ssh_command("pgrep -f 'mpirun' | wc -l")
        print(f"Active mpirun processes: {mpi_procs.strip()}")

        # Show last few lines of log
        print()
        print("Recent activity:")
        print("-" * 50)
        log = ssh_command("tail -15 /tmp/mpi_stress.log")
        print(log)
    else:
        print("Status: NOT RUNNING")

def show_log():
    """Show live log output"""
    print("MPI Stress Test Log (last 50 lines):")
    print("=" * 50)
    log = ssh_command("tail -50 /tmp/mpi_stress.log", timeout=10)
    print(log)

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
