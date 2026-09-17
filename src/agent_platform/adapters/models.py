"""按任务固定环境中的协议选择适配器，允许同一实例使用不同模型协议。"""
import asyncio
from .ollama import OllamaAdapter
from .openai_chat import OpenAIChatAdapter


class ModelAdapters:
    def __init__(self, credentials):
        self.adapters = {'ollama-chat':OllamaAdapter(credentials),
                         'openai-chat':OpenAIChatAdapter(credentials)}

    def for_connection(self, connection):
        return self.adapters[connection.model_adapter]

    async def close(self):
        await asyncio.gather(*(adapter.close() for adapter in self.adapters.values()))
