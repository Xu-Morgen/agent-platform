"""单进程后端启动入口。"""

import argparse

import uvicorn

from agent_platform.application import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Agent Platform 后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口必须介于 0 与 65535 之间")
    uvicorn.run(create_app(), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
