---
name: github-api-upload
description: 通过 GitHub REST API 把本地项目/技能文件上传到 GitHub 仓库。当 git 协议（github.com:443）被网络屏蔽、无法用 git push 时，改用 api.github.com 的 Contents / Git Data API 完成建仓库与推送。适用于"代码上传到 GitHub""把 skill 发布到 GitHub""git 推不上去"等场景。
agent_created: true
---

# github-api-upload

当本机 `git push` 连不上 `github.com`(端口 443 被网络/沙箱屏蔽),用 GitHub REST API
走 `api.github.com` 完成**建仓库 + 上传文件 + 提交**。

## 触发场景

- 用户要求"把代码 / 项目 / skill 上传到 GitHub""发布到 GitHub"。
- `git push` 报 `Failed to connect to github.com:443` / `Empty reply from server`。
- 没有 `gh` CLI,或 `gh` 未登录。
- 有 classic PAT(`ghp_` 开头)或 fine-grained PAT(需有 Contents: Read and Write)。

## 工作流程

### 0. 准备凭据

- classic PAT:GitHub → Settings → Developer settings → Tokens(classic)→ 勾选 `repo`。
- fine-grained PAT:需对账号**授权**,且 Permissions → **Contents: Read and Write**(否则创建仓库 403、推送 404/403)。
- 用前确认 `api.github.com` 可达:`curl -s -o /dev/null -w "%{http_code}" https://api.github.com`
  返回 200 即说明 API 通道可用(即便 github.com 主站不通)。

### 1. 建仓库(若不存在)

```bash
python scripts/push_repo.py create --token <PAT> --name my-repo --public
```

### 2. 推送本地目录

```bash
python scripts/push_repo.py push \
  --token <PAT> --owner hhbhunter --repo my-repo \
  --local ./my-project --branch main \
  --message "feat: initial commit"
```

脚本会:
1. 用 `git check-ignore`(或内置 `.gitignore` 解析)跳过 `.git`、`.env`、`*.zip`、`__pycache__` 等。
2. 优先走 **Git Data API** 生成一个干净的单提交(含完整目录树)。
3. 若仓库为空导致 blob 创建返回 409,自动回退到 **Contents API** 逐文件提交(同样可靠)。
4. 已存在文件会带 `sha` 更新,不会丢历史。

### 3. 安全收尾

- 推送完成后**不要把 PAT 写进 `git remote` URL**;若用 git,执行
  `git remote set-url origin https://github.com/<owner>/<repo>.git` 去掉令牌。
- `.env` 等密钥必须被 `.gitignore` 忽略,且永远只传源码文件。

## 限制与注意

- 本方式依赖 `api.github.com` 可达;`github.com` 主站不通不影响。
- Git Data API 路径下,空仓库可能返回 409,脚本已内置 Contents API 回退。
- 大仓库(上千文件)建议分批或先用 Git Data API 单提交;逐文件提交会产生多个 commit。

## Scripts

- `scripts/push_repo.py` — 建仓 + 推送主脚本(依赖 `requests`)。
- `scripts/.env.example` — 凭据配置示例。

## References

- `references/github_api.md` — 接口端点、PAT 类型差异、网络屏蔽排查、常见 errcode。
- `README.md` — 完整使用说明与示例。
