#!/usr/bin/env python3
"""Verify downloaded A-class repositories."""
import argparse
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)


def dir_size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", help="Root of an optional external repository collection containing sources/<folder>")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "orchestration" / "a_class_repositories.json"))
    args = ap.parse_args()
    base = Path(args.bundle).expanduser().resolve()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rows = []
    for item in cfg["repositories"]:
        target = base / "sources" / item["folder"]
        readmes = []
        skill_files = []
        if target.exists():
            for name in ["README.md", "README.zh-CN.md", "readme.md", "README_CN.md", "SKILL.md", "skill.md"]:
                p = target / name
                if p.exists():
                    if "readme" in name.lower():
                        readmes.append(str(p.relative_to(base)))
                    if name.lower() == "skill.md":
                        skill_files.append(str(p.relative_to(base)))
        commit = git(target, "rev-parse", "HEAD") if (target / ".git").exists() else None
        status = git(target, "status", "--short") if (target / ".git").exists() else None
        rows.append({
            "repo": item["repo"],
            "folder": item["folder"],
            "exists": target.exists(),
            "is_git_repo": (target / ".git").exists(),
            "commit": commit.stdout.strip() if commit and commit.returncode == 0 else None,
            "dirty": bool(status.stdout.strip()) if status and status.returncode == 0 else None,
            "readmes": readmes,
            "skill_files": skill_files,
            "size_bytes": dir_size(target) if target.exists() else 0,
            "role": item["role"]
        })
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "bundle": str(base),
        "repository_count_expected": len(cfg["repositories"]),
        "repository_count_present": sum(1 for r in rows if r["exists"]),
        "items": rows
    }
    out = base / "verification_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    missing = [r for r in rows if not r["exists"] or not r["is_git_repo"]]
    if missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
