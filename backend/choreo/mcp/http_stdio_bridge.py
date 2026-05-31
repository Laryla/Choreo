#!/usr/bin/env python3
"""
MCP HTTP → stdio bridge.

用法：python http_stdio_bridge.py <url>

将 stdin 上的 MCP JSON-RPC 消息逐条 POST 到 HTTP MCP 端点，
把响应写回 stdout。每条消息独立请求，绕过 streamablehttp_client
的持久连接兼容问题。
"""
import json
import sys

import httpx


def main(url: str) -> None:
    with httpx.Client(
        timeout=30,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    ) as client:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                resp = client.post(url, json=msg)
                text = resp.text.strip()

                # 服务端返回 SSE 格式 (event: message\ndata: {...})
                if text.startswith("event:") or text.startswith("data:"):
                    for sse_line in text.splitlines():
                        if sse_line.startswith("data:"):
                            data = sse_line[5:].strip()
                            sys.stdout.write(data + "\n")
                            sys.stdout.flush()
                else:
                    sys.stdout.write(text + "\n")
                    sys.stdout.flush()

            except Exception as e:
                error = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(error) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python http_stdio_bridge.py <url>\n")
        sys.exit(1)
    main(sys.argv[1])
