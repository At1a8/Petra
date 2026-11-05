#!/usr/bin/env python3
"""One Petra task per machine: a lock in /dev/shm, which every container started with --ipc=host
shares with the host (scripts/run_docker.sh starts them that way), which no other machine sees, and
which a reboot clears.

    python3 scripts/run_lock.py acquire --run-dir DIR --mode MODE --task TEXT [--idle-hours 12]
    python3 scripts/run_lock.py release --run-dir DIR        # or: release --force
    python3 scripts/run_lock.py status

acquire exits 1 when another task holds the machine and prints who. A lock is taken over without
asking when its run has finished (a report newer than the lock) or has written nothing in its run
directory for the holder's --idle-hours; a lock left by a run that died is freed at once with
`release --force`. Standard library only.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import sys
import time

LOCK_FILE = os.environ.get("PETRA_LOCK_FILE", "/dev/shm/petra-run.lock")
REPORTS = ("report.md", "validation_report.md")


def _open(path: str) -> int:
    """The lock file, readable and writable by everyone. /dev/shm is sticky, and protected_regular
    refuses O_CREAT on a file another user owns even to root, so an existing file is opened without it."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o666)
        os.fchmod(fd, 0o666)
        return fd
    except FileExistsError:
        return os.open(path, os.O_RDWR)


def _read(fd: int) -> dict:
    os.lseek(fd, 0, os.SEEK_SET)
    raw = b""
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        raw += chunk
    try:
        data = json.loads(raw.decode() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _write(fd: int, data: dict) -> None:
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    if data:
        os.write(fd, (json.dumps(data, indent=1) + "\n").encode())


def last_activity(holder: dict) -> float:
    """When the holder last showed life: its start, or the newest entry of its run directory or logs/."""
    latest = float(holder.get("started", 0))
    run_dir = holder.get("run_dir", "")
    for d in (run_dir, os.path.join(run_dir, "logs")) if run_dir else ():
        try:
            with os.scandir(d) as entries:
                for e in entries:
                    try:
                        latest = max(latest, e.stat(follow_symlinks=False).st_mtime)
                    except OSError:
                        pass
        except OSError:
            pass
    return latest


def stale_reason(holder: dict, now: float) -> str:
    """'' while the holder's run is alive; otherwise why its lock can be taken over."""
    if not holder.get("run_dir"):
        return "free"
    started = float(holder.get("started", 0))
    for name in REPORTS:
        try:
            if os.stat(os.path.join(holder["run_dir"], name)).st_mtime >= started:
                return "its run finished"
        except OSError:
            pass
    idle_hours = float(holder.get("idle_hours", 12))
    if now - last_activity(holder) > idle_hours * 3600:
        return "its run wrote nothing for %g h" % idle_hours
    return ""


def acquire(lock: str, run_dir: str, task: str = "", mode: str = "", idle_hours: float = 12,
            now: float | None = None) -> dict:
    now = time.time() if now is None else now
    run_dir = os.path.abspath(run_dir)
    fd = _open(lock)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        holder = _read(fd)
        if holder.get("run_dir") == run_dir:
            return {"status": "acquired", "holder": holder}
        reason = stale_reason(holder, now)
        if not reason:
            return {"status": "busy", "holder": holder}
        new = {"run_dir": run_dir, "mode": mode, "task": task, "idle_hours": idle_hours, "started": now,
               "started_at": time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(now)),
               "host": socket.gethostname(), "container": os.environ.get("PETRA_CONTAINER", "")}
        _write(fd, new)
        out = {"status": "acquired", "holder": new}
        if reason != "free":
            out["took_over"] = {"run_dir": holder.get("run_dir", ""), "reason": reason}
        return out
    finally:
        os.close(fd)  # closing the descriptor releases the flock


def release(lock: str, run_dir: str = "", force: bool = False) -> dict:
    try:
        fd = os.open(lock, os.O_RDWR)
    except FileNotFoundError:
        return {"status": "free"}
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        holder = _read(fd)
        if not holder.get("run_dir"):
            return {"status": "free"}
        if force or (run_dir and holder["run_dir"] == os.path.abspath(run_dir)):
            _write(fd, {})
            return {"status": "released", "holder": holder}
        return {"status": "held", "holder": holder}
    finally:
        os.close(fd)


def status(lock: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    try:
        fd = os.open(lock, os.O_RDONLY)
    except FileNotFoundError:
        return {"status": "free"}
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        holder = _read(fd)
    finally:
        os.close(fd)
    if not holder.get("run_dir"):
        return {"status": "free"}
    out = {"status": "held", "holder": holder, "idle_hours_so_far": round((now - last_activity(holder)) / 3600, 1)}
    reason = stale_reason(holder, now)
    if reason:
        out.update(status="stale", reason=reason)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One Petra task per machine.")
    ap.add_argument("--lock", default=LOCK_FILE, help="lock file (default %(default)s; PETRA_LOCK_FILE)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    acq = sub.add_parser("acquire", help="take the machine for a run; exit 1 when another task holds it")
    acq.add_argument("--run-dir", required=True)
    acq.add_argument("--mode", default="")
    acq.add_argument("--task", default="")
    acq.add_argument("--idle-hours", type=float, default=12,
                     help="hours without a write in the run directory after which the lock counts as stale")
    rel = sub.add_parser("release", help="free the machine")
    rel.add_argument("--run-dir", default="")
    rel.add_argument("--force", action="store_true", help="free it whoever holds it (a run that died)")
    sub.add_parser("status", help="who holds the machine")
    a = ap.parse_args(argv)
    if a.cmd == "acquire":
        out = acquire(a.lock, a.run_dir, a.task, a.mode, a.idle_hours)
    elif a.cmd == "release":
        out = release(a.lock, a.run_dir, a.force)
    else:
        out = status(a.lock)
    print(json.dumps(out, indent=1))
    return 1 if a.cmd != "status" and out["status"] in ("busy", "held") else 0


if __name__ == "__main__":
    sys.exit(main())
