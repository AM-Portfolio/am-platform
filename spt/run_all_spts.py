import subprocess
import os
import re
import json

k6_path = r"C:\Program Files\k6\k6.exe"
base_url = "https://am-dev.asrax.in"
spt_dir = r"C:\Users\adhik\Downloads\Asrax\AM\am-platform"

scenarios = [
    {"service": "Identity", "script": "spt/identity-spt.js", "name": "baseline"},
    {"service": "Identity", "script": "spt/identity-spt.js", "name": "load"},
    {"service": "Identity", "script": "spt/identity-spt.js", "name": "stress"},
    {"service": "Subscription", "script": "spt/subscription-spt.js", "name": "baseline"},
    {"service": "Subscription", "script": "spt/subscription-spt.js", "name": "load"},
    {"service": "Subscription", "script": "spt/subscription-spt.js", "name": "stress"}
]

results = []

def run_k6(service, script, scenario):
    cmd = [
        k6_path, "run",
        "--insecure-skip-tls-verify",
        "--env", f"SCENARIO={scenario}",
        "--env", f"BASE_URL={base_url}",
        script
    ]
    print(f"=== Running {service} - {scenario} ===")
    
    # Run process and capture output
    process = subprocess.run(cmd, cwd=spt_dir, capture_output=True, text=True)
    output = process.stdout + "\n" + process.stderr
    
    # Save raw output to log file
    log_name = f"spt_{service.lower()}_{scenario}.log"
    with open(os.path.join(spt_dir, "spt", log_name), "w", encoding="utf-8") as f:
        f.write(output)
        
    print(f"Finished {service} - {scenario}. Logs saved to spt/{log_name}")
    
    # Parse metrics from output
    metrics = {
        "service": service,
        "scenario": scenario,
        "checks_pct": "0.00%",
        "req_failed_pct": "100.00%",
        "avg_lat": "0s",
        "p95_lat": "0s",
        "reqs_sec": "0/s",
        "status": "Failed"
    }
    
    # Extract Checks Percentage
    checks_match = re.search(r"checks_succeeded\.*:\s+([\d\.]+)%", output)
    if checks_match:
        metrics["checks_pct"] = f"{checks_match.group(1)}%"
        
    # Extract Request Fail Rate
    fail_match = re.search(r"http_req_failed\.*:\s+([\d\.]+)%", output)
    if fail_match:
        metrics["req_failed_pct"] = f"{fail_match.group(1)}%"
        
    # Extract Latencies
    duration_match = re.search(r"http_req_duration\.*:\s+avg=([^\s]+)\s+min=[^\s]+\s+med=[^\s]+\s+max=[^\s]+\s+p\(90\)=[^\s]+\s+p\(95\)=([^\s]+)", output)
    if duration_match:
        metrics["avg_lat"] = duration_match.group(1)
        metrics["p95_lat"] = duration_match.group(2)
        
    # Extract requests per second
    reqs_match = re.search(r"http_reqs\.*:\s+\d+\s+([\d\.]+)/s", output)
    if reqs_match:
        metrics["reqs_sec"] = f"{reqs_match.group(1)}/s"
        
    # Check if threshold crossed
    if "thresholds on metrics" in output:
        metrics["status"] = "Threshold Crossed"
    else:
        metrics["status"] = "Passed"
        
    results.append(metrics)

def main():
    # Make sure spt folder exists
    os.makedirs(os.path.join(spt_dir, "spt"), exist_ok=True)
    
    for sc in scenarios:
        run_k6(sc["service"], sc["script"], sc["name"])
        
    # Write JSON results summary
    with open(os.path.join(spt_dir, "spt", "spt_results_summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("=== ALL SPT RUNS COMPLETE ===")

if __name__ == "__main__":
    main()
