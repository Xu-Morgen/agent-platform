"""在导入源码前读取唯一 @block 声明；只接受 AST 字面量。"""
import ast
from pydantic import ValidationError
from ..blocks.single import BlockMetadata
from .validation import invalid, validation_error


def _block_entry(source: bytes):
    tree = ast.parse(source)
    aliases = set()
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in ('agent_platform.blocks', 'agent_platform.blocks.single'):
            aliases.update(a.asname or a.name for a in node.names if a.name == 'block')
        elif isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names
                           if a.name in ('agent_platform.blocks', 'agent_platform.blocks.single'))

    def is_block(fn):
        return ((isinstance(fn, ast.Name) and fn.id in aliases)
                or (isinstance(fn, ast.Attribute) and fn.attr == 'block' and ast.unparse(fn.value) in modules))

    declarations = [(node, decorator) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for decorator in node.decorator_list if isinstance(decorator, ast.Call) and is_block(decorator.func)]
    if len(declarations) != 1:
        raise invalid('单文件须在顶层恰好声明一个 @block；从 agent_platform.blocks 显式导入', ['entry'])
    return declarations[0]


def entry_source(source: bytes) -> str:
    """从已固定源码读取入口，不执行或推断 Python 条件。"""
    import io
    import tokenize
    encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
    node, _ = _block_entry(source)
    return ast.get_source_segment(source.decode(encoding), node)


def read_declaration(source: bytes) -> BlockMetadata:
    _, declaration = _block_entry(source)
    if declaration.args or any(k.arg is None for k in declaration.keywords):
        raise invalid('@block 只接受具名的字面量参数，不支持展开或表达式', ['entry'])
    values = {}
    allowed = {'id', 'version', 'name', 'description', 'dependencies', 'dependencySources', 'models', 'api', 'semanticSearch', 'ocr'}
    for keyword in declaration.keywords:
        if keyword.arg not in allowed or keyword.arg in values:
            raise invalid('@block 参数无效或重复', [keyword.arg])
        try:
            values[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError):
            raise invalid('@block 声明只能使用字面量，不能引用变量或调用函数', [keyword.arg]) from None
    if 'semanticSearch' in values:
        values['uses_semantic_search'] = values.pop('semanticSearch')
    if 'ocr' in values:
        values['uses_ocr'] = values.pop('ocr')
    if 'api' in values:
        values['uses_api'] = values.pop('api')
    try:
        return BlockMetadata.model_validate(values)
    except ValidationError as exc:
        raise validation_error(exc) from None
