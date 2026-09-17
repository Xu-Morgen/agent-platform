"""包与实例契约相同，但不符合平台模型协议时必须保存前拒绝。"""
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from agent_platform.application import create_app
from agent_platform.contracts.environments import EnvironmentWrite
from agent_platform.contracts.services import ServiceWrite
from agent_platform.contracts.errors import PlatformError

app = create_app()
env = app.state.environments.save(EnvironmentWrite(name='未调用', connections=[{'connectionId':'model','kind':'model','baseUrl':'http://localhost','model':'synthetic'}]))
with TemporaryDirectory() as directory:
    shutil.copytree('examples/execution/model-package', directory, dirs_exist_ok=True)
    path = Path(directory, 'package.json')
    manifest = json.loads(path.read_text())
    manifest['requiredCapabilities'][0]['inputModel'] = 'models:Message'
    path.write_text(json.dumps(manifest))
    app.state.packages.load(directory)
    loaded = app.state.definitions.load('examples/execution/model-instance')
    definition = loaded.definition.model_dump(by_alias=True)
    definition['environmentRefs'] = [env.environment_id]
    definition['capabilityBindings'][0].update(environmentId=env.environment_id, inputModel='models:Message')
    try:
        app.state.services.save(ServiceWrite(name='无效',definition_load_id=loaded.load_id,definition=definition))
    except PlatformError as exc:
        assert exc.status_code == 422 and exc.error.field_path[-1] == 'input_model'
    else: raise AssertionError()
assert not app.state.services.list()
print('模型绑定：包与实例同时误声明 Message 仍在保存前拒绝，未创建服务')
