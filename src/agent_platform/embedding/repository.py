"""不可变本地模型文件与默认选择；向量不进入仓储。"""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import RLock

from ..contracts.embedding import EmbeddingModel, EmbeddingSelection, EmbeddingSnapshot
from .adapter import read_manifest, verify_files, failure


class EmbeddingRepository:
    def __init__(self, store, processes, root=None):
        self.store, self.processes = store, processes
        self.lock = RLock()
        self.import_lock = asyncio.Lock()
        self.temporary = None
        if root is None:
            if store.durable:
                from ..storage.local import default_data_directory
                root = Path(os.environ.get('AGENT_PLATFORM_DATA_DIR', default_data_directory())) / 'embedding-models'
            else:
                self.temporary = TemporaryDirectory(prefix='agent-embedding-')
                root = self.temporary.name
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.models = {key: EmbeddingModel.model_validate(value) for key, value in store.read('embedding_models').items()}
        self.selection = EmbeddingSelection.model_validate(store.read('settings').get('embedding', {}))
        # 启动恢复核对持久文件，历史身份不随文件损坏改变。
        for key, model in self.models.items():
            try:
                if read_manifest(self.root / key) != model.manifest:
                    raise failure('EMBEDDING_NOT_READY', '应用模型清单与持久记录不一致')
                verify_files(self.root / key, model.manifest)
            except Exception as exc:
                model.status = 'unavailable'
                model.error = getattr(getattr(exc, 'error', None), 'message', '应用模型文件不可读取')
                store.write([('embedding_models', key, model.model_dump(mode='json'))])

    def list(self):
        with self.lock:
            return [model.model_copy(deep=True) for model in self.models.values()]

    def get(self, model_id):
        with self.lock:
            if model_id not in self.models:
                raise failure('EMBEDDING_NOT_READY', '模型尚未导入，请在平台设置中导入本地模型目录')
            return self.models[model_id].model_copy(deep=True)

    def fixed(self):
        with self.lock:
            if self.selection.model_id is None:
                raise failure('EMBEDDING_NOT_SELECTED', '请在平台设置中选择就绪的本地 embedding 模型')
            model = self.get(self.selection.model_id)
            if model.status != 'ready':
                raise failure('EMBEDDING_NOT_READY', '默认模型不可用，请恢复应用模型文件或导入另一版本')
            return EmbeddingSnapshot(model_id=model.model_id, manifest=model.manifest)

    def select(self, value):
        with self.lock:
            if value.model_id is not None:
                model = self.get(value.model_id)
                if model.status != 'ready':
                    raise failure('EMBEDDING_NOT_READY', '所选模型未就绪')
            self.store.write([('settings', 'embedding', value.model_dump(mode='json'))])
            self.selection = value.model_copy(deep=True)
            return self.selection

    async def check(self, model_id):
        model = self.get(model_id)
        session = self.processes.session(self.root / model_id,
            EmbeddingSnapshot(model_id=model_id, manifest=model.manifest))
        try:
            result = await session.call('diagnostic')
            model.status, model.error = 'ready', None
            return result
        except Exception as exc:
            model.status = 'unavailable'
            model.error = getattr(getattr(exc, 'error', None), 'message', '模型检查失败')
            raise
        finally:
            await session.close()
            with self.lock:
                self.store.write([('embedding_models', model_id, model.model_dump(mode='json'))])
                self.models[model_id] = model

    async def import_directory(self, directory, progress=lambda message: None):
        async with self.import_lock:
            source = Path(directory)
            progress('检查清单与文件摘要')
            manifest = await asyncio.to_thread(read_manifest, source)
            size = await asyncio.to_thread(verify_files, source, manifest)
            model_id = manifest.identity()
            # 同一身份不覆盖历史文件；损坏的已有副本应明确报错。
            if model_id in self.models:
                await self.check(model_id)
                return self.get(model_id)
            with TemporaryDirectory(prefix='.import-', dir=self.root) as temporary:
                target = Path(temporary)
                def copy():
                    for item in (manifest.weights, manifest.tokenizer, manifest.configuration):
                        path = target / item.path
                        path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source / item.path, path)
                    (target / 'embedding.json').write_text(manifest.model_dump_json(by_alias=True, indent=2))
                    verify_files(target, manifest)
                progress('复制到应用模型目录')
                copying = asyncio.create_task(asyncio.to_thread(copy))
                try:
                    await asyncio.shield(copying)
                except asyncio.CancelledError:
                    await copying
                    raise
                progress('验证 CPU 模型加载与小样例编码')
                snapshot = EmbeddingSnapshot(model_id=model_id, manifest=manifest)
                session = self.processes.session(target, snapshot)
                try:
                    await session.call('diagnostic')
                finally:
                    await session.close()
                model = EmbeddingModel(**snapshot.model_dump(), size_bytes=size,
                    imported_at=datetime.now(timezone.utc).isoformat(), status='ready')
                with self.lock:
                    destination = self.root / model_id
                    if destination.exists():
                        # 上次文件发布后、元数据提交前退出：仅接纳完整同身份文件。
                        if read_manifest(destination) != manifest:
                            raise failure('EMBEDDING_NOT_READY', '已存在的模型目录身份冲突')
                        verify_files(destination, manifest)
                    else:
                        target.rename(destination)
                    self.store.write([('embedding_models', model_id, model.model_dump(mode='json'))])
                    self.models[model_id] = model
                return model

    def close(self):
        if self.temporary:
            self.temporary.cleanup()
