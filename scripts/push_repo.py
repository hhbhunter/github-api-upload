#!/usr/bin/env python3
"""通过 GitHub REST API 上传本地目录到仓库。

两种网络环境都可用:
- Git Data API:生成一个干净的提交(含目录树)。空仓库若报 409 则回退。
- Contents API 回退:逐文件 PUT,自动创建首个 commit 与分支。

依赖: pip install requests
"""
import argparse
import base64
import json
import os
import subprocess
import sys

import requests

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

# 内置默认忽略(当 local 不是 git 仓库、无法用 check-ignore 时生效)
DEFAULT_IGNORE = [".git", ".env", "*.env", "*.zip", "__pycache__", "*.pyc", ".DS_Store"]


def _auth(token):
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {token}"
    return h


def _is_ignored(local, rel):
    """优先用 git check-ignore;失败则用内置规则 + .gitignore 简单匹配。"""
    try:
        r = subprocess.run(
            ["git", "-C", local, "check-ignore", rel],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return True
    except Exception:
        pass
    # 内置规则
    name = os.path.basename(rel)
    for pat in DEFAULT_IGNORE:
        if pat == name or rel == pat:
            return True
        if pat.startswith("*") and name.endswith(pat[1:]):
            return True
        if pat.endswith("/") and rel.startswith(pat):
            return True
    # 简单读取 .gitignore
    gi = os.path.join(local, ".gitignore")
    if os.path.isfile(gi):
        with open(gi, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line == name or rel == line or rel.endswith("/" + line):
                    return True
                if line.startswith("*") and name.endswith(line[1:]):
                    return True
    return False


def collect_files(local):
    out = []
    for root, dirs, files in os.walk(local):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, local).replace(os.sep, "/")
            if _is_ignored(local, rel):
                continue
            out.append(rel)
    return sorted(out)


def repo_exists(token, owner, repo):
    r = requests.get(f"{API}/repos/{owner}/{repo}", headers=_auth(token))
    return r.status_code == 200


def create_repo(token, name, private, desc=""):
    body = {"name": name, "private": bool(private), "description": desc, "auto_init": False}
    r = requests.post(f"{API}/user/repos", json=body, headers=_auth(token))
    if r.status_code == 201:
        print(f"[create] 仓库已创建: {name} (private={private})")
        return True
    if r.status_code == 422:
        print(f"[create] 仓库已存在: {name}")
        return True
    print(f"[create] 失败 {r.status_code}: {r.text[:300]}")
    r.raise_for_status()


def _read_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def push_git_data(token, owner, repo, local, branch, message):
    """Git Data API:单提交 + 目录树。空仓库 409 时返回 False 触发回退。"""
    files = collect_files(local)
    if not files:
        print("[push] 没有可上传的文件(可能被 .gitignore 全部忽略)")
        return True
    # 1) blobs
    blobs = {}
    for rel in files:
        b64 = _read_b64(os.path.join(local, rel))
        r = requests.post(
            f"{API}/repos/{owner}/{repo}/git/blobs",
            json={"content": b64, "encoding": "base64"},
            headers=_auth(token),
        )
        if r.status_code == 409:
            print("[push] 空仓库 409,回退 Contents API")
            return False
        r.raise_for_status()
        blobs[rel] = r.json()["sha"]
    # 2) base + tree
    ref_r = requests.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}", headers=_auth(token))
    base_tree = ref_r.json()["object"]["sha"] if ref_r.status_code == 200 else None
    parent = base_tree
    tree = [{"path": rel, "mode": "100644", "type": "blob", "sha": sha} for rel, sha in blobs.items()]
    tr = requests.post(
        f"{API}/repos/{owner}/{repo}/git/trees",
        json={"tree": tree, "base_tree": base_tree},
        headers=_auth(token),
    )
    tr.raise_for_status()
    tree_sha = tr.json()["sha"]
    # 3) commit
    cm = requests.post(
        f"{API}/repos/{owner}/{repo}/git/commits",
        json={
            "message": message,
            "tree": tree_sha,
            "parents": [parent] if parent else [],
            "author": {"name": owner, "email": f"{owner}@users.noreply.github.com"},
        },
        headers=_auth(token),
    )
    cm.raise_for_status()
    commit_sha = cm.json()["sha"]
    # 4) ref
    if parent:
        requests.patch(
            f"{API}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json={"sha": commit_sha},
            headers=_auth(token),
        ).raise_for_status()
    else:
        requests.post(
            f"{API}/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
            headers=_auth(token),
        ).raise_for_status()
    print(f"[push] Git Data API 提交完成: {len(files)} 个文件")
    return True


def push_contents(token, owner, repo, local, branch, message):
    """Contents API 回退:逐文件 PUT,自动建分支。"""
    import urllib.parse

    files = collect_files(local)
    if not files:
        print("[push] 没有可上传的文件(可能被 .gitignore 全部忽略)")
        return
    for rel in files:
        b64 = _read_b64(os.path.join(local, rel))
        url = f"{API}/repos/{owner}/{repo}/contents/{urllib.parse.quote(rel)}"
        body = {"message": f"{message} ({rel})", "content": b64, "branch": branch}
        g = requests.get(url, headers=_auth(token))
        if g.status_code == 200:
            body["sha"] = g.json()["sha"]
        r = requests.put(url, json=body, headers=_auth(token))
        if r.status_code not in (200, 201):
            print(f"[push] 失败 {rel}: {r.status_code} {r.text[:200]}")
            r.raise_for_status()
        print(f"[push] 已提交: {rel}")
    print(f"[push] Contents API 完成: {len(files)} 个文件")


def push(token, owner, repo, local, branch, message):
    if not repo_exists(token, owner, repo):
        print(f"[push] 仓库 {owner}/{repo} 不存在,先创建")
        create_repo(token, repo, False)
    if push_git_data(token, owner, repo, local, branch, message):
        return
    push_contents(token, owner, repo, local, branch, message)


def main():
    p = argparse.ArgumentParser(description="通过 GitHub API 上传本地目录")
    sub = p.add_subparsers(dest="action", required=True)

    pc = sub.add_parser("create", help="创建仓库")
    pc.add_argument("--token", required=True)
    pc.add_argument("--name", required=True)
    pc.add_argument("--owner", default=None)
    pc.add_argument("--public", action="store_true", help="公开仓库(默认私有)")
    pc.add_argument("--desc", default="")

    pp = sub.add_parser("push", help="推送本地目录")
    pp.add_argument("--token", required=True)
    pp.add_argument("--owner", required=True)
    pp.add_argument("--repo", required=True)
    pp.add_argument("--local", required=True)
    pp.add_argument("--branch", default="main")
    pp.add_argument("--message", default="feat: upload via GitHub API")

    args = p.parse_args()
    if args.action == "create":
        create_repo(args.token, args.name, not args.public, args.desc)
    elif args.action == "push":
        push(args.token, args.owner, args.repo, args.local, args.branch, args.message)


if __name__ == "__main__":
    main()
