#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import subprocess
import re
from pathlib import Path

PID = 85035
DB_WORKDIR = "/Users/wyl/MediaCrawler-main"
SUPABASE_BIN = "/Users/wyl/.local/bin/supabase"
STATE_FILE = Path("/private/tmp/monitor_85035_state.json")

def is_pid_running(pid):
    try:
        res = subprocess.check_output(["ps", "-p", str(pid)], text=True)
        return str(pid) in res
    except subprocess.CalledProcessError:
        return False

def check_other_processes():
    try:
        output = subprocess.check_output(["ps", "-ef"], text=True)
        lines = []
        for line in output.splitlines():
            if "classify_images_gemini.py" in line and "grep" not in line:
                lines.append(line.strip())
        return lines
    except Exception:
        return []

def get_db_count(sql):
    for attempt in range(4):
        try:
            res = subprocess.check_output(
                [SUPABASE_BIN, "db", "query", "--linked", sql],
                cwd=DB_WORKDIR,
                text=True,
                timeout=45
            )
            matches = re.findall(r'│\s*(\d+)\s*│', res)
            if matches:
                return int(matches[0])
            numbers = re.findall(r'\b\d+\b', res)
            if numbers:
                return int(numbers[0])
        except Exception as e:
            sys.stderr.write(f"Attempt {attempt+1} failed executing SQL: {e}\n")
            if attempt < 3:
                time.sleep(3)
    return None

def main():
    running = is_pid_running(PID)
    
    # Check other processes in case PID changed or it is running under another PID
    other_procs = check_other_processes()
    
    # Query database counts
    sql_classified = "SELECT count(*) FROM weibo_images WHERE is_commercial IS NOT NULL AND is_selfie IS NOT NULL"
    sql_total = "SELECT count(*) FROM weibo_images"
    
    classified = get_db_count(sql_classified)
    total = get_db_count(sql_total)
    
    if classified is None or total is None:
        print("Error: Could not retrieve counts from Supabase. Process might still be running but DB query timed out.")
        sys.exit(1)
        
    unclassified = total - classified
    progress_pct = (classified / total) * 100 if total > 0 else 0.0
    
    now = time.time()
    
    # Load state
    state = {}
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
            
    # Initialize state if not present
    if not state or "start_count" not in state:
        state = {
            "start_time": now,
            "start_count": classified,
            "last_time": now,
            "last_count": classified,
            "total_records": total
        }
    
    elapsed_since_last = now - state["last_time"]
    processed_since_last = classified - state["last_count"]
    
    elapsed_total = now - state["start_time"]
    processed_total = classified - state["start_count"]
    
    # Calculate speeds
    speed_last_min = 0.0
    if elapsed_since_last > 0:
        speed_last_min = (processed_since_last / elapsed_since_last) * 60
        
    speed_total_min = 0.0
    if elapsed_total > 0:
        speed_total_min = (processed_total / elapsed_total) * 60
        
    # Estimate time remaining (ETC)
    # Prefer recent speed if available, otherwise total speed
    speed_for_etc = speed_last_min if speed_last_min > 0 else speed_total_min
    
    etc_str = "N/A"
    if speed_for_etc > 0 and unclassified > 0:
        minutes_left = unclassified / speed_for_etc
        hours = int(minutes_left // 60)
        mins = int(minutes_left % 60)
        etc_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
    elif unclassified == 0:
        etc_str = "0m (Completed!)"
        
    # Update state
    state["last_time"] = now
    state["last_count"] = classified
    state["total_records"] = total
    
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass
        
    # Render report
    status_str = "RUNNING 🟢" if running else "STOPPED 🔴"
    if not running and other_procs:
        status_str = f"PID {PID} STOPPED, but active process found: {other_procs[0]}"
        
    print(f"📊 Process 85035 Monitor Report")
    print(f"========================================")
    print(f"Process Status: {status_str}")
    print(f"Classified:     {classified:,} / {total:,} ({progress_pct:.2f}%)")
    print(f"Remaining:      {unclassified:,} records")
    print(f"----------------------------------------")
    print(f"Recent Speed:   {speed_last_min:.2f} recs/min (over last {elapsed_since_last/60:.1f}m)")
    print(f"Average Speed:  {speed_total_min:.2f} recs/min (over last {elapsed_total/60:.1f}m)")
    print(f"ETC:            {etc_str}")
    print(f"========================================")
    
if __name__ == "__main__":
    main()
