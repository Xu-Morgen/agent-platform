"""已编译拼图实例的会话快照仓储。"""
from ..registry.validation import invalid


class SnapshotRepository:
    def __init__(self):
        self._items = {}

    def add(self, snapshot):
        if snapshot.instance_id in self._items:
            raise invalid('实例标识已存在', ['instanceId'], code='VERSION_CONFLICT')
        self._items[snapshot.instance_id] = snapshot

    def get(self, instance_id):
        if instance_id not in self._items:
            raise invalid('实例不存在', ['instanceId'], code='RECORD_NOT_FOUND')
        return self._items[instance_id]
