# github-api-upload 使用说明

在 `git push` 连不上 `github.com` 时,用 GitHub REST API(`api.github.com`)把本地目录上传到仓库。

## 安装 / 依赖

```bash
pip install requests
```

## 适用场景

- 把本地项目 / WorkBuddy skill 上传到 GitHub
- `git push` 报 `Failed to connect to github.com:443` / `Empty reply from server`
- 无 `gh` CLI,或 `gh` 未登录

## 准备凭据

1. classic PAT:GitHub → Settings → Developer settings → Tokens(classic)→ 勾选 `repo`。
2. 确认 API 通道可用:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://api.github.com   # 期望 200
   ```

## 用法

### 1. 建仓库

```bash
python scripts/push_repo.py create \
  --token ghp_xxx --name my-repo --public --desc "我的仓库"
```

### 2. 推送目录

```bash
python scripts/push_repo.py push \
  --token ghp_xxx --owner hhbhunter --repo my-repo \
  --local ./my-project --branch main \
  --message "feat: initial commit"
```

脚本行为:
- 跳过 `.git`、`.env`、`*.zip`、`__pycache__` 等(读 `.gitignore`,否则用内置默认)。
- 优先 Git Data API 生成单提交;空仓库 409 时自动回退 Contents API 逐文件提交。
- 已存在文件带 `sha` 更新。

## 工作流建议

1. 先把本地目录整理好(确认 `.gitignore` 含 `.env`)。
2. `create` 建仓库(若已存在会跳过)。
3. `push` 上传。
4. 收尾:不要保留带令牌的 remote URL;`.env` 不入仓库。

## 限制

- 依赖 `api.github.com` 可达;`github.com` 主站不通不影响。
- 大量文件逐文件提交会产生多个 commit(可用 Git Data 单提交路径优化)。

## 文件

- `scripts/push_repo.py` — 主脚本
- `scripts/.env.example` — 凭据示例
- `references/github_api.md` — 接口、PAT 差异、网络排查、errcode
