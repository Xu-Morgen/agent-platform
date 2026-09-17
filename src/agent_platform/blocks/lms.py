"""只解固定 LMS 外壳；业务类型由绑定块的输出契约决定。"""
from pydantic import JsonValue
from ..contracts.base import StrictModel
from ..contracts.errors import ErrorResponse, PlatformError
from ..runtime.validation import validate


class LMSResponse(StrictModel):
    code: str
    msg: str | None = None
    sub_code: str | None = None
    sub_msg: str | None = None
    biz_data: JsonValue = None


def unwrap(value: LMSResponse, output_model):
    value = validate(LMSResponse, value, 'blocks.lms.input')
    if value.code != '10000':
        raise PlatformError(ErrorResponse(code='UPSTREAM_BUSINESS_ERROR', stage='blocks.lms.response',
            message='上游业务失败', details={'upstream_code': value.code, 'upstream_msg': value.msg,
            'upstream_sub_code': value.sub_code, 'upstream_sub_msg': value.sub_msg}), 502)
    return validate(output_model, value.biz_data, 'blocks.lms.output')
