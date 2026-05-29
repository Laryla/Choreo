#!/usr/bin/env python3
"""Choreo 测试脚本 - 统计最近 commit 信息"""

import subprocess
import json
from collections import Counter
from datetime import datetime

print("=" * 50)
print("🧪 Choreo 测试脚本执行成功！")
print("=" * 50)

# 获取最近的 commit 记录
result = subprocess.run(
    ["git", "log", "--oneline", "--since=1 week ago", "--format=%H|%s|%an|%ad", "--date=short"],
    capture_output=True, text=True, cwd="."
)

commits = []
for line in result.stdout.strip().split("\n"):
    if line:
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({
                "hash": parts[0][:7],
                "message": parts[1],
                "author": parts[2],
                "date": parts[3]
            })

print(f"\n📊 最近一周共 {len(commits)} 个 commit：")
print("-" * 50)

# 按类型统计
types = Counter()
for c in commits:
    t = c["message"].split(":")[0] if ":" in c["message"] else "other"
    types[t] += 1

print("\n📋 Commit 类型统计：")
for t, count in types.most_common():
    print(f"   {t}: {count} 个")

print("\n📝 最近 5 条 commit：")
for c in commits[:5]:
    print(f"   [{c['date']}] {c['hash']} - {c['message']}")

print("\n✅ 测试完成！Choreo 工作正常 🚀")
