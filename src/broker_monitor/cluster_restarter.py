from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .restarter import ServiceInfo


def _run_ps(script: str, timeout: int = 120) -> tuple[int, str, str]:
    """Runs a PowerShell command and returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ---------------------------------------------------------------------------
# Stop (parallel)
# ---------------------------------------------------------------------------

def _stop_one(cluster_name: str, resource_name: str) -> tuple[bool, str]:
    rc, _, err = _run_ps(
        f"Import-Module FailoverClusters; "
        f"Stop-ClusterResource -Cluster '{cluster_name}' -Name '{resource_name}' -ErrorAction Stop"
    )
    return rc == 0, err


def stop_resources_parallel(
    cluster_name: str,
    resource_names: list[str],
    stop_timeout: int = 60,
) -> dict[str, tuple[bool, str]]:
    """
    Stops cluster resources in parallel using a thread pool.
    Mirrors the RunspacePool approach from the original PowerShell script.
    Returns {resource_name: (success, error_message)}.
    """
    results: dict[str, tuple[bool, str]] = {}
    n = max(1, len(resource_names))

    with ThreadPoolExecutor(max_workers=n) as executor:
        future_map = {
            executor.submit(_stop_one, cluster_name, name): name
            for name in resource_names
        }
        for future in as_completed(future_map, timeout=stop_timeout):
            name = future_map[future]
            try:
                ok, err = future.result()
                results[name] = (ok, err)
            except Exception as exc:
                results[name] = (False, str(exc))

    return results


# ---------------------------------------------------------------------------
# Taskkill (forced, per resource)
# ---------------------------------------------------------------------------

def taskkill_resource(cluster_name: str, resource_name: str) -> bool:
    """
    Finds the Windows service behind the cluster resource and kills it with
    taskkill /F on the owner node. Equivalent to the original Invoke-TaskKillOnClusterResource.
    """
    script = f"""
    Import-Module FailoverClusters
    $r       = Get-ClusterResource -Cluster '{cluster_name}' -Name '{resource_name}' -ErrorAction Stop
    $svcName = ($r | Get-ClusterParameter -Name ServiceName -ErrorAction Stop).Value
    $node    = $r.OwnerNode.Name
    if (-not $svcName) {{ exit 1 }}
    Invoke-Command -ComputerName $node -ScriptBlock {{
        param($n)
        $w = Get-WmiObject Win32_Service -Filter "Name='$n'" -ErrorAction SilentlyContinue
        if ($w -and $w.ProcessId -gt 0) {{
            & taskkill /F /PID $w.ProcessId 2>&1 | Out-Null
        }}
    }} -ArgumentList $svcName -ErrorAction Stop
    """
    rc, _, _ = _run_ps(script)
    return rc == 0


# ---------------------------------------------------------------------------
# Start (sequential, with wait)
# ---------------------------------------------------------------------------

def start_resource_with_wait(
    cluster_name: str,
    resource_name: str,
    start_timeout: int,
) -> tuple[bool, str]:
    """
    Starts a cluster resource and waits until it reaches Online state.
    Mirrors Start-ClusterResourceWithWait from the original script.
    """
    rc, state_out, _ = _run_ps(
        f"Import-Module FailoverClusters; "
        f"(Get-ClusterResource -Cluster '{cluster_name}' -Name '{resource_name}').State"
    )
    if rc == 0 and state_out == "Online":
        return True, "Online (already)"

    rc, _, err = _run_ps(
        f"Import-Module FailoverClusters; "
        f"Start-ClusterResource -Cluster '{cluster_name}' -Name '{resource_name}' -ErrorAction Stop"
    )
    if rc != 0:
        return False, f"Start-ClusterResource falhou: {err}"

    elapsed = 0
    while elapsed < start_timeout:
        time.sleep(2)
        elapsed += 2
        rc, state_out, _ = _run_ps(
            f"Import-Module FailoverClusters; "
            f"(Get-ClusterResource -Cluster '{cluster_name}' -Name '{resource_name}').State"
        )
        if rc == 0:
            if state_out == "Online":
                return True, f"Online ({elapsed}s)"
            if state_out == "Failed":
                return False, "Failed"

    return False, f"Timeout aguardando Online -- estado final: {state_out}"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def restart_cluster_slaves(
    cluster_name: str,
    infos: list[ServiceInfo],
    stop_timeout: int,
    start_timeout: int,
) -> tuple[list[ServiceInfo], list[ServiceInfo]]:
    """
    Full cluster restart sequence (mirrors Restart-MarfrigSlaves):
      1. Stop-ClusterResource in parallel
      2. Wait + taskkill /F on all resources (force, one-shot)
      3. Start-ClusterResource sequentially, waiting for Online

    Returns (restarted, failed).
    """
    resource_names = [info.resource_name for info in infos if info.resource_name]

    # 1. Stop in parallel
    stop_results = stop_resources_parallel(cluster_name, resource_names, stop_timeout)
    for name, (ok, err) in stop_results.items():
        if not ok:
            pass  # log handled by caller; continue regardless (taskkill will force it)

    # 2. Taskkill (forced, without checking stop result -- one-shot strategy)
    time.sleep(2)
    for info in infos:
        if info.resource_name:
            taskkill_resource(cluster_name, info.resource_name)
    time.sleep(3)

    # 3. Start sequentially
    restarted: list[ServiceInfo] = []
    failed: list[ServiceInfo] = []

    for info in infos:
        if not info.resource_name:
            failed.append(info)
            continue
        ok, state = start_resource_with_wait(cluster_name, info.resource_name, start_timeout)
        if ok:
            restarted.append(info)
        else:
            failed.append(info)

    return restarted, failed
