"""通用块只注册、查询与验证；不调用其业务入口。"""
from dataclasses import dataclass
from .snapshots import ContentSnapshot, capture
from .validation import invalid, load_symbol, validation_error
from ..contracts.blocks import BlockManifest
from pydantic import ValidationError


@dataclass(frozen=True)
class BlockArtifact:
    manifest_json: str
    content: ContentSnapshot

    @property
    def manifest(self):
        return BlockManifest.model_validate_json(self.manifest_json)


class BlockRegistry:
    def __init__(self):
        self._items = {}

    def load(self, directory) -> BlockArtifact:
        content = capture(directory)
        try:
            manifest = BlockManifest.model_validate_json(content.read_resource('block.json'))
            load_symbol(content, manifest.entry, ['entry'])
            load_symbol(content, manifest.input_model, ['inputModel'], model=True)
            load_symbol(content, manifest.output_model, ['outputModel'], model=True)
            key = (manifest.block_id, manifest.version)
            existing = self._items.get(key)
            if existing:
                if existing.content.digest != content.digest:
                    raise invalid('同一块版本已有不同内容', ['version'], code='VERSION_CONFLICT')
                content.close()
                return existing
            artifact = BlockArtifact(manifest.model_dump_json(), content)
            self._items[key] = artifact
            return artifact
        except ValidationError as exc:
            content.close()
            raise validation_error(exc) from None
        except Exception:
            content.close()
            raise

    def get(self, block_id, version) -> BlockArtifact:
        if (block_id, version) not in self._items:
            raise invalid('通用块版本未注册', ['blockId'], code='DEPENDENCY_ERROR')
        return self._items[block_id, version]
