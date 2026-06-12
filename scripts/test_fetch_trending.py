#!/usr/bin/env python3
"""format_message 的单元测试。运行:python scripts/test_fetch_trending.py"""

from fetch_trending import format_message

SAMPLE = [
    {
        "full_name": "owner/repo",
        "html_url": "https://github.com/owner/repo",
        "stargazers_count": 3210,
        "language": "Python",
        "description": "一句话描述",
    },
    {
        "full_name": "a/b",
        "html_url": "https://github.com/a/b",
        "stargazers_count": 12,
        "language": None,
        "description": None,
    },
    {
        "full_name": "x/y<z>",
        "html_url": "https://github.com/x/y",
        "stargazers_count": 1000000,
        "language": "Go",
        "description": "tag <b> & stuff",
    },
]


def test_basic_rendering():
    out = format_message(SAMPLE, "2026-06-13")
    assert "GitHub 每日热点 · 2026-06-13" in out
    assert "Top 3" in out
    assert '<a href="https://github.com/owner/repo">owner/repo</a>' in out
    assert "⭐ 3,210" in out
    assert "· Python" in out
    assert "一句话描述" in out


def test_missing_language_and_description():
    out = format_message(SAMPLE, "2026-06-13")
    # 缺失 language 降级为 —
    assert "· —" in out
    # 第二项无描述行:它后面紧跟第三项编号,不应出现空的描述缩进
    lines = out.splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("2. "))
    assert lines[idx + 1].startswith("3. ")


def test_description_zh_preferred():
    repos = [
        {
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
            "stargazers_count": 100,
            "language": "Python",
            "description": "English description",
            "description_zh": "中文描述",
        }
    ]
    out = format_message(repos, "2026-06-13")
    assert "中文描述" in out
    assert "English description" not in out


def test_html_escaping():
    out = format_message(SAMPLE, "2026-06-13")
    # 仓库名与描述中的尖括号 / & 被转义
    assert "y&lt;z&gt;" in out
    assert "tag &lt;b&gt; &amp; stuff" in out
    # star 千分位
    assert "⭐ 1,000,000" in out


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("所有测试通过")


if __name__ == "__main__":
    run()
