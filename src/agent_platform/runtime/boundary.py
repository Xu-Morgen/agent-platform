"""节点、能力和终态共同使用的策略入口；I4 注入预算与取消。"""
from contextvars import ContextVar
from inspect import isawaitable

current_boundary = ContextVar('current_boundary', default=None)


class Boundary:
    def __init__(self, policies=(), observer=None):
        self.policies = tuple(policies)
        self.observer = observer

    async def check(self, phase, step_id):
        if self.observer:
            result = self.observer(phase, step_id)
            if isawaitable(result):
                await result
        # 失败和取消的清理永远不被预算策略拦截。
        if phase == 'cleanup':
            return
        for policy in self.policies:
            result = policy(phase, step_id)
            if isawaitable(result):
                await result


async def checkpoint(phase, step_id):
    boundary = current_boundary.get()
    if boundary:
        await boundary.check(phase, step_id)
