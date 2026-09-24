"""最完整通用块教学：API 查询、严格契约、任务附件、进度与明确失败。

核心职责：
    将 API 返回的文本按本次输入中的选项整理，输出固定契约的结果。
    模型交互由 Prompt 包承担；服务负责组织流程，本文件不创建或修改流程。

学习顺序：
    1. Options / APIRequest / Input / APIResponse / Output：声明选项、外发请求、入口、响应与出口。
    2. normalize_text：普通辅助函数与显式业务错误。
    3. @block：唯一执行入口、全部静态声明字段与资源版本。
    4. normalize：平台注入 API/context，附件访问、异步请求和实际进度。

依赖与使用：
    仅用标准库和平台已有 Pydantic，不额外安装依赖或下载模型。
    在服务页加载本文件，选择其输入/输出契约，为节点绑定 API 连接与路径；
    API 接受 GET query 参数并返回 {"text": "..."}。完整步骤见同目录 README.md。
    输入示例：{"query": "greeting", "options": {"letterCase": "upper"}}。

修改建议：
    修改源码（含注释）后递增 version，重新加载并保存新服务实例。
    增减契约字段时同步检查服务端口、前后步骤及输入示例；不自动做字段映射。

【架构评估】
    单文件保留模型、辅助函数和一个注册入口，便于平台完整快照，无邻接源码依赖。
    API 地址、凭据、超时及请求路径均由平台配置，源码不硬编码部署环境。
    这是受信任本地代码示例，不是沙箱；输出、进度与异常各有独立职责。
"""
import re
from typing import Literal

from pydantic import Field, field_validator
from agent_platform.blocks import BlockAPI, BlockContext, block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.errors import ErrorResponse, PlatformError
from agent_platform.contracts.files import TaskFile


class Options(StrictModel):
    """业务选项属于每次调用的完整输入，不是 API 节点的连接配置。

    所有嵌套模型均继承 StrictModel：拒绝未知字段和隐式类型转换。
    Python 使用 snake_case；公开 JSON/Schema 默认使用 camelCase，例如 trimEdges。
    """

    trim_edges: bool = Field(default=True, description='去掉首尾空白')
    collapse_spaces: bool = Field(default=True, description='将连续空白合并为一个空格，包含换行')
    letter_case: Literal['preserve', 'lower', 'upper'] = Field(default='preserve', description='字母大小写转换')
    prefix: str = Field(default='', max_length=20, description='在处理后的文本前添加前缀')
    require_content: bool = Field(default=False, description='开启后，正文整理为空白时明确失败；前缀不能充当正文')


class APIRequest(StrictModel):
    """外发查询契约；入口复用同一字段规则，发送前再验证实际请求。"""

    query: str = Field(min_length=1, max_length=10000, description='发送给 API 的非空白查询文本')

    @field_validator('query')
    @classmethod
    def query_has_content(cls, value: str) -> str:
        """字段长度无法排除纯空白，补充运行时业务约束，但不偷偷修改查询内容。

        入口和外发请求共用此校验，失败不会请求 API。跨字段约束可使用
        model_validator；自定义校验不能完整表达为 JSON Schema，会影响静态契约
        兼容性，因此教学服务直接使用本块导出的 primaryContract。
        """
        if not value.strip():
            raise ValueError('查询文本不能只有空白')
        return value


class Input(APIRequest):
    """服务首步接收服务输入；其他普通步骤接收上一层完整输出。"""

    options: Options = Field(default_factory=Options, description='省略时创建本次调用独立的默认选项')
    # TaskFile 是平台生成的引用，不是路径或二进制；可空字段会生成可选上传控件。
    attachment: TaskFile | None = Field(default=None, description='可选任务附件；由任务页面选择并保存')


class APIResponse(StrictModel):
    """外部 JSON 也必须运行时校验；实际接口有响应外壳时在这里明确声明。"""

    text: str = Field(min_length=1, max_length=10000, description='API 返回的待处理文本')


class Output(StrictModel):
    """固定出口：平台验证并将完整结果交给下一步或作为服务结果返回。"""

    text: str = Field(description='处理结果；未开启 requireContent 时允许为空')
    character_count: int = Field(ge=0, description='Python len(text)，按 Unicode 码点计数，不是字节数或 token')
    changed: bool = Field(description='最终文本是否与 API 返回的原始文本不同')


def normalize_text(original: str, options: Options) -> str:
    """纯文本处理辅助函数：先整理正文、检查业务条件，最后加前缀。

    调用来源：唯一注册入口 normalize。这里不访问平台、网络或文件。
    输出：整理后的字符串；requireContent 开启且正文为空白时抛平台明确错误。
    """
    text = original.strip() if options.trim_edges else original
    if options.collapse_spaces:
        text = re.sub(r'\s+', ' ', text)
    if options.letter_case == 'lower':
        text = text.lower()
    elif options.letter_case == 'upper':
        text = text.upper()
    if options.require_content and not text.strip():
        # 错误码必须来自平台公开错误契约；message 不携带凭据或完整外部响应。
        # 不返回“错误文本”冒充正常 Output；平台记录失败并停止后续步骤。
        raise PlatformError(ErrorResponse(
            code='CONTRACT_VALIDATION_ERROR', stage='block.sample_normalize',
            message='API 返回的正文整理后为空白，无法满足 requireContent 要求',
            field_path=['options', 'requireContent'],
        ))
    return options.prefix + text


@block(
    id='sample-normalize',
    version='3.0.1',  # 相同 id/version 不能对应不同源码；归档也不会释放版本号。
    name='API 查询与文本整理',
    description='按 query 向已绑定 API 查询文本，再按 options 整理空白、大小写及前缀；输出文本、字符数和是否改变。可作服务首步，需要配置 API 连接与路径；无参考输入。',
    api=True,  # 需要 async 入口与关键字参数 api: BlockAPI；连接和路径在节点配置。
    # 全部参数必须直接写字面量；不接受变量、函数调用或 **kwargs 展开。
    dependencies=[],  # 标准库与平台内置 Pydantic 无需声明；第三方库应填写已验证版本。
    dependencySources=[],  # 可声明单一 HTTPS 索引，或含 package/url/sha256 的 wheel 来源。
    models=[],  # 模型声明字段为 name/version/url/sha256/filename；不得填写猜测的摘要。
)
async def normalize(value: NodeInput[Input, tuple[()]], *, api: BlockAPI, context: BlockContext) -> Output:
    """唯一执行入口：附件检查 → API 查询 → 文本整理 → 严格输出。

    输入：value 已通过平台入口校验；api/context 由平台注入，不能写进业务 JSON。
    输出：Output 是业务结果；context.progress 是进度，不加入出口契约。
    执行：API 请求失败、契约失败或业务错误直接向平台传播，不吞异常、不伪造成功。

    生命周期说明：
        普通无 API 块也可以使用同步 def；本例因 API 请求而使用 async def。
        平台没有 on_load/before_run/after_run/on_error/on_cancel 等注册钩子。
        前后处理写在入口内；普通资源用 with / try-finally 释放，但强制终止进程时
        不能保证执行 finally，不能用它承诺回滚外部 API 的写操作。
        平台管理取消、超时和服务重试；重试可能再次调用 API，每次调用使用新进程，
        不依赖模块全局变量跨任务保留状态，也不在块内自行重试整个业务。
    """
    # 未知总量的阶段只上报消息，不虚构百分比或随时间推进进度。
    context.progress('检查任务附件')
    if value.primary.attachment is not None:
        # 平台验证引用归属与摘要，返回任务副本；不要相信用户传来的本机路径。
        # 用 with 展示文件句柄清理：只读文件头，不在这个文本模板内解析 PDF/DOCX。
        path = context.file(value.primary.attachment)
        with path.open('rb') as attachment_file:
            attachment_file.read(16)
        context.progress('附件已检查')

    # 若扩展本例使用本地模型：先在 @block.models 声明真实文件，再调用
    # model_path = context.model('与声明中的 name 一致')
    # 将 model_path 显式传给推理库，不能改用库默认路径或隐式下载。
    # 当前 models=[]，故没有可调用的模型名称；这里是接入教学，不会执行模型推理。
    # 块只获得模型文件访问能力；调用 LLM 应使用平台 Prompt 包。

    context.progress('等待 API 响应')
    # GET 的 payload 是查询参数；POST/PUT/PATCH/DELETE 的 payload 是 JSON 请求体。
    # response_type 必填，返回值已通过严格校验；块不自行拼地址或添加认证 Header。
    # 仅发送 APIRequest 声明的字段；本地 options 和附件引用不进入外部请求。
    request = APIRequest(query=value.primary.query)
    response = await api.request('GET', request.model_dump(mode='json', by_alias=True), response_type=APIResponse)
    context.progress('API 响应已校验', current=1, total=3)

    text = normalize_text(response.text, value.primary.options)
    context.progress('文本整理已完成', current=2, total=3)
    result = Output(text=text, character_count=len(text), changed=text != response.text)

    # 三个阶段均已完成，才报告 3/3。这里只表示块内处理完成；平台仍需校验出口，
    # 后续节点也可能失败。平台保存最新进度，不把 progress 当成完整事件日志。
    context.progress('处理结果已生成', current=3, total=3)
    return result
