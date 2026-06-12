# GitHub 每日热点推送 Telegram — 设计文档

日期:2026-06-13

## 目标

通过 GitHub Actions 每日定时运行,抓取 GitHub 上「最近 7 天创建、star 最多」的前 10 个仓库,
格式化后通过 Telegram Bot 推送到指定 chat。

## 关键决策

| 项 | 选择 |
|---|---|
| 数据源 | GitHub Search API(`search/repositories`),非官方 trending 抓取 |
| 热点定义 | 最近 7 天内创建、按 star 降序 Top 10 |
| 实现语言 | Python 3 标准库(`urllib`),零第三方依赖 |
| 调度 | 每日北京时间 08:30 = UTC 00:30,cron `30 0 * * *`,另加 `workflow_dispatch` 手动触发 |
| 推送目标 | 用户已有 Telegram Bot 与 chat,凭证经 GitHub Secrets 注入 |

## 架构

两个文件:

### 1. `scripts/fetch_trending.py`

纯 Python 标准库实现,职责单一:抓取 → 格式化 → 推送。

- **抓取**
  - 计算 7 天前的日期(UTC),构造查询:
    `q=created:>=<YYYY-MM-DD> sort:stars order:desc`,`per_page=10`
  - 请求 `GET https://api.github.com/search/repositories`
  - 携带 `Authorization: Bearer $GITHUB_TOKEN`(使用 Actions 内置 token 提升速率限额),
    以及 `Accept: application/vnd.github+json` 和 `User-Agent` 头
- **格式化**
  - 从每个仓库取 `full_name`、`html_url`、`stargazers_count`、`language`、`description`
  - 组装为一条 Telegram 消息,`parse_mode=HTML`,仓库名做成超链接
  - star 数用千分位;`language`/`description` 缺失时优雅降级(显示 `—` / 省略)
- **推送**
  - `POST https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage`
  - body:`chat_id=$TELEGRAM_CHAT_ID`、`text`、`parse_mode=HTML`、`disable_web_page_preview=true`
- **配置(环境变量)**
  - `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`(必需,缺失即报错退出)
  - `GITHUB_TOKEN`(可选,缺失时无认证请求,限额较低)
- **错误处理**
  - 缺少必需环境变量 → 打印明确错误、`sys.exit(1)`
  - GitHub API 非 200 或返回空结果 → 打印响应、`sys.exit(1)`
  - Telegram 返回非 200 或 `ok=false` → 打印响应、`sys.exit(1)`
  - 任意未捕获异常都应让进程非零退出,使 Action 标红暴露问题

### 2. `.github/workflows/daily-trending.yml`

- 触发:`schedule: cron "30 0 * * *"` + `workflow_dispatch`
- 权限:`contents: read`
- 步骤:
  1. `actions/checkout`
  2. `actions/setup-python`(Python 3.x)
  3. 运行 `python scripts/fetch_trending.py`,注入环境变量:
     - `TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}`
     - `TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}`
     - `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`(内置)

## 消息格式样例

```
📈 GitHub 每日热点 · 2026-06-13
近 7 天新晋高星仓库 Top 10

1. owner/repo  ⭐ 3,210  · Python
   一句话描述…
2. ...
```

仓库名为可点击超链接(HTML `<a>`),消息关闭网页预览以保持紧凑。

## 用户需完成的配置

在仓库 `Settings → Secrets and variables → Actions → New repository secret` 添加:

- `TELEGRAM_BOT_TOKEN`:BotFather 给出的 bot token
- `TELEGRAM_CHAT_ID`:目标 chat / 频道的数字 ID

## 测试策略

- 脚本可本地运行:`export` 两个 Telegram 环境变量后 `python scripts/fetch_trending.py`,
  观察 Telegram 是否收到消息。
- 单元层面:格式化函数(repo 列表 → 消息文本)是纯函数,可对样例数据断言输出,
  覆盖缺失 language/description 的降级路径。
- Workflow 通过 `workflow_dispatch` 手动触发做端到端验证。

## 非目标(YAGNI)

- 不做语言过滤(全语言)。
- 不做去重 / 历史记忆(每天独立查询)。
- 不抓取官方 Trending 页面 HTML。
- 不做多 chat / 多频道分发。
