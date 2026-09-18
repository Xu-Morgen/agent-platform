"""单进程后端启动入口。"""

import argparse

import asyncio

from agent_platform.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Agent Platform 后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--control-fd", type=int, default=None)
    parser.add_argument('--data-dir', default=None, help='应用存储目录，默认与桌面相同')
    parser.add_argument('--memory', action='store_true', help='仅供开发：显式使用内存且不启动 PostgreSQL')
    args = parser.parse_args()
    if args.memory and args.data_dir:
        parser.error('--memory 与 --data-dir 不能同时使用')
    if not 0 <= args.port <= 65535:
        parser.error("端口必须介于 0 与 65535 之间")
    asyncio.run(serve(args.host, args.port, args.control_fd, data_dir=args.data_dir, memory=args.memory))


if __name__ == "__main__":
    main()
