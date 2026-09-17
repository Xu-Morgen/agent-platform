from agent_platform.blocks import block
from agent_platform.contracts.base import StrictModel
from agent_platform.blocks.lms import LMSResponse, unwrap


class Payload(StrictModel):
    text: str


@block(id='lms-text', version='1.0.0', name='LMS 文本解包', description='校验成功码并解包 bizData.text；其他数据结构需声明对应输出模型')
def unpack(value: LMSResponse) -> Payload:
    return unwrap(value, Payload)
