#!/usr/bin/env python3
"""抓取 GitHub 近 7 天新晋高星仓库,推送到 Telegram。

依赖:仅 Python 3 标准库。

环境变量:
  TELEGRAM_BOT_TOKEN  必需,BotFather 给出的 bot token
  TELEGRAM_CHAT_ID    必需,目标 chat / 频道 ID
  GITHUB_TOKEN        可选,提升 GitHub API 速率限额
  ANTHROPIC_API_KEY   可选,设置后用 Claude 把英文描述翻译成中文;缺失则保留原文
"""

import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
TOP_N = 10
WINDOW_DAYS = 7


def fetch_trending(github_token=None):
    """返回近 WINDOW_DAYS 天创建、按 star 降序的前 TOP_N 个仓库列表。"""
    since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    query = f"created:>={since}"
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": TOP_N}
    )
    url = f"{GITHUB_SEARCH_URL}?{params}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "d3lap1ace-daily-trending",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"[error] GitHub API HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[error] GitHub API 请求失败: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    items = payload.get("items") or []
    if not items:
        print("[error] GitHub API 返回空结果", file=sys.stderr)
        sys.exit(1)
    return items


TRANSLATE_MODEL = "claude-opus-4-8"


def translate_descriptions(descriptions):
    """用 Claude 把仓库描述批量翻译成简体中文。

    一次 API 调用翻译所有非空描述。返回与输入等长的列表,空描述原样保留。
    任意异常向上抛出,由调用方决定是否回退到原文。
    """
    import anthropic  # 延迟导入:本地跑测试时无需安装 SDK

    indexed = [(i, d) for i, d in enumerate(descriptions) if d and d.strip()]
    result = list(descriptions)
    if not indexed:
        return result

    numbered = "\n".join(f"{n}. {d}" for n, (_, d) in enumerate(indexed))
    schema = {
        "type": "object",
        "properties": {
            "translations": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["translations"],
        "additionalProperties": False,
    }
    prompt = (
        "把下面每个 GitHub 仓库描述翻译成简体中文,保留技术术语、专有名词、"
        "产品名和代码标识符的原文。只翻译,不要解释或添加内容。"
        f"按输入顺序返回 translations 数组,长度必须正好是 {len(indexed)}。\n\n"
        f"{numbered}"
    )

    client = anthropic.Anthropic()  # 读取 ANTHROPIC_API_KEY
    resp = client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=2000,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    translations = json.loads(text)["translations"]

    for k, (orig_i, orig_d) in enumerate(indexed):
        result[orig_i] = translations[k] if k < len(translations) else orig_d
    return result


def format_message(repos, today):
    """把仓库列表渲染成 Telegram HTML 消息文本。纯函数,便于测试。"""
    lines = [
        f"📈 <b>GitHub 每日热点 · {today}</b>",
        f"近 {WINDOW_DAYS} 天新晋高星仓库 Top {len(repos)}",
        "",
    ]
    for idx, repo in enumerate(repos, start=1):
        name = html.escape(repo.get("full_name", "unknown"))
        url = html.escape(repo.get("html_url", ""))
        stars = f"{repo.get('stargazers_count', 0):,}"
        language = repo.get("language") or "—"
        lines.append(f'{idx}. <a href="{url}">{name}</a>  ⭐ {stars}  · {language}')
        description = (repo.get("description_zh") or repo.get("description") or "").strip()
        if description:
            lines.append(f"   {html.escape(description)}")
    return "\n".join(lines)


def send_telegram(bot_token, chat_id, text):
    """通过 Telegram Bot sendMessage 发送消息。失败即非零退出。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"[error] Telegram HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[error] Telegram 请求失败: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    if not payload.get("ok"):
        print(f"[error] Telegram 返回错误: {payload}", file=sys.stderr)
        sys.exit(1)


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(
            "[error] 缺少必需环境变量 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID",
            file=sys.stderr,
        )
        sys.exit(1)

    github_token = os.environ.get("GITHUB_TOKEN")
    repos = fetch_trending(github_token)

    if os.environ.get("ANTHROPIC_API_KEY"):
        descriptions = [r.get("description") or "" for r in repos]
        try:
            translated = translate_descriptions(descriptions)
            for repo, text in zip(repos, translated):
                repo["description_zh"] = text
            print("[info] 已用 Claude 翻译仓库描述")
        except Exception as exc:  # 翻译失败不应阻断推送,回退英文原文
            print(f"[warn] 翻译失败,保留英文原文: {exc}", file=sys.stderr)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    message = format_message(repos, today)
    send_telegram(bot_token, chat_id, message)
    print(f"[info] 已推送 {len(repos)} 个仓库到 Telegram chat {chat_id}")


if __name__ == "__main__":
    main()
