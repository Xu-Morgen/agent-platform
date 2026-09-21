"""平台设置保存后不修改当前执行器；后端下次启动读取已保存值。"""
from ..contracts.settings import PlatformSettings, PlatformSettingsView


class SettingsRepository:
    def __init__(self, store):
        self.store = store
        document = store.read('settings').get('platform')
        self.saved = PlatformSettings.model_validate(document) if document is not None else PlatformSettings()
        if document is None:
            self.store.write([('settings', 'platform', self.saved.model_dump(mode='json'))])
        self.active_run_concurrency = self.saved.run_concurrency

    def get(self):
        self.store.check()
        return PlatformSettingsView(
            **self.saved.model_dump(), active_run_concurrency=self.active_run_concurrency,
            restart_required=self.saved.run_concurrency != self.active_run_concurrency,
            persistent=self.store.durable)

    def save(self, value):
        value = PlatformSettings.model_validate(value.model_dump())
        self.store.write([('settings', 'platform', value.model_dump(mode='json'))])
        self.saved = value
        return self.get()
