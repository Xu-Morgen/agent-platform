"""单进程后端启动入口。"""

import argparse

import asyncio

from agent_platform.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Agent Platform 后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--control-fd", type=int, default=None)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口必须介于 0 与 65535 之间")
    asyncio.run(serve(args.host, args.port, args.control_fd))


if __name__ == "__main__":
    main()
