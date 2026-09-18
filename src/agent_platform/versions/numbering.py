"""按实际内容分类；分配序列独立于当前激活实例，回退不复用编号。"""
from dataclasses import dataclass
import json


def signatures(snapshot):
    draft = snapshot.draft.model_dump(mode='json', by_alias=True)
    structural = {key: draft[key] for key in ('inputContract', 'outputContract', 'flow')}
    structural['compiler'] = snapshot.compiler_version
    structural['modules'] = {ref: value.content.digest for ref, value in snapshot.catalog._artifacts.items()}
    structural['contracts'] = {ref: value.schema for ref, value in snapshot.catalog._contracts.items()}
    configuration = {'nodes': draft['nodeConfigurations'], 'budget': draft['budget'], 'retryLimit': draft['retryLimit']}
    return json.dumps(structural, sort_keys=True), json.dumps(configuration, sort_keys=True)


@dataclass(frozen=True)
class VersionNumber:
    revision: int
    major: int
    minor: int
    change_kind: str

    @property
    def version(self):
        return f'{self.major}.{self.minor}'


class VersionAllocator:
    def __init__(self):
        self._last = {}

    def allocate(self, service_id, current, candidate):
        last = self._last.get(service_id)
        if last is None:
            number = VersionNumber(1, 1, 0, 'initial')
        else:
            old_code, old_config = signatures(current)
            new_code, new_config = signatures(candidate)
            major = old_code != new_code
            config = old_config != new_config
            number = VersionNumber(last.revision + 1, last.major + int(major),
                                   0 if major else last.minor + 1,
                                   'breaking' if major and config else 'major' if major else 'minor')
        self._last[service_id] = number
        return number
