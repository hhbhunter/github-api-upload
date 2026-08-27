# GitHub API 上传参考

## 一、网络通道差异(本环境实测)

| 主机 | 状态 | 用途 |
|------|------|------|
| `github.com:443` | ❌ 连接超时/重置 | `git push`(智能 HTTP)走这里,被屏蔽 |
| `api.github.com:443` | ✅ 200 | REST API(建仓/上传/提交)走这里,可用 |
| `codeload.github.com` | ✅ 301 | 下载/克隆归档,可用 |

**结论**:git 协议推不上去时,改用 `api.github.com` 的 REST API 上传。

## 二、PAT 类型

| 类型 | 前缀 | 建仓库 | 推送(Contents) | 备注 |
|------|------|:--:|:--:|------|
| classic PAT | `ghp_` | ✅(`repo`) | ✅(`repo`) | 一步到位,推荐 |
| fine-grained PAT | `github_pat_` | ❌ 默认 403 | 需 `Contents: RW` | 须对账号授权 + 开 Contents 权限 |

创建 classic PAT:GitHub → Settings → Developer settings → Tokens(classic)→ `repo`。

## 三、核心接口

### 建仓库
`POST /user/repos`
```json
{"name":"my-repo","private":false,"auto_init":false}
```
- 201 成功;422 已存在。

### Git Data API(单提交,首选)
1. `POST /repos/{o}/{r}/git/blobs` — `{"content":<b64>,"encoding":"base64"}` → `sha`
2. `POST /repos/{o}/{r}/git/trees` — `{"tree":[...],"base_tree":<父commit或null>}` → `sha`
3. `POST /repos/{o}/{r}/git/commits` — `{"message","tree","parents":[...]}` → `sha`
4. 空仓库:`POST /repos/{o}/{r}/git/refs` `{"ref":"refs/heads/main","sha":...}`
   已有分支:`PATCH /repos/{o}/{r}/git/refs/heads/main` `{"sha":...}`

> 空仓库首次调 blobs 可能返回 **409 Git Repository is empty** → 回退 Contents API。

### Contents API(回退)
`PUT /repos/{o}/{r}/contents/{path}`
```json
{"message":"...","content":"<b64>","branch":"main","sha":"<已存在文件sha,可选>"}
```
- 首个文件自动创建分支与首个 commit;更新已有文件需带 `sha`。

## 四、常见 errcode / HTTP 状态

| 状态 | 含义 | 处理 |
|------|------|------|
| 401 | token 无效/过期 | 重新生成 PAT |
| 403 | fine-grained 未授权/无权限 | 改用 classic 或开 Contents:RW |
| 404 | 仓库不存在/无权限 | 确认 owner/repo、token 权限 |
| 409 | 空仓库(仅 Git Data blobs) | 回退 Contents API |
| 422 | 仓库已存在 / 参数错误 | 忽略(已存在)或检查参数 |

## 五、安全

- 令牌不在 `git remote` URL 中留存;用后即清。
- `.env` 必须 `.gitignore` 忽略;只传源码文件。
- PAT 等同密码,仅在可信会话提供;可优先用本地 `git init` 提交、自行推送。
