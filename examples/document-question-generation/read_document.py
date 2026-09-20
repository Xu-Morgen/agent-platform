"""单文件文档读取块。依赖与模型由平台准备，运行阶段只使用本地资源。"""
import time
import zipfile
from functools import lru_cache
from typing import Annotated

from pydantic import Field
from agent_platform.blocks import BlockContext, block
from agent_platform.contracts.base import StrictModel
from agent_platform.contracts.errors import ErrorResponse, PlatformError
from agent_platform.contracts.files import TaskFile

MAX_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_PAGES = 100
MAX_SIDE = 6000
MAX_PIXELS = 20_000_000
MAX_SECONDS = 240
NonBlank = Annotated[str, Field(min_length=1, pattern=r'\S')]


class Input(StrictModel):
    document: TaskFile


class Output(StrictModel):
    file_name: NonBlank
    text: NonBlank


def fail(reason, page=None, code='DOCUMENT_READ_ERROR'):
    where = f'第 {page} 页：' if page is not None else ''
    raise PlatformError(ErrorResponse(code=code, stage='block.read_document', message=where + reason))


def check(deadline, page=None):
    # 平台父进程每 50ms 检查取消并终止本工作进程；此处负责逐项超时边界。
    if time.monotonic() > deadline:
        fail('文档处理超过 240 秒限制', page, 'BLOCK_TIMEOUT')


@lru_cache(maxsize=1)
def engine(paths):
    from rapidocr_onnxruntime import RapidOCR
    # 显式传入全部模型，不使用库默认路径或自动下载。
    if any(not path.is_file() for path in paths):
        fail('OCR 模型未就绪', code='DEPENDENCY_ERROR')
    return RapidOCR(det_model_path=str(paths[0]), rec_model_path=str(paths[1]),
                    cls_model_path=str(paths[2]), intra_op_num_threads=1, inter_op_num_threads=1,
                    text_score=0.0)


def ordered_lines(result):
    # 几何位置按自顶向下、自左向右组织；复杂多栏仍需人工核对。
    return sorted(result, key=lambda item: (min(point[1] for point in item[0]), min(point[0] for point in item[0])))


def read_pdf(path, context, deadline):
    import pymupdf
    parts = []
    try:
        document = pymupdf.open(path)
    except Exception:
        fail('PDF 损坏或无法打开')
    with document:
        if not document.is_pdf or document.needs_pass or (document.metadata or {}).get('encryption'):
            fail('文件不是有效 PDF 或已加密')
        if document.is_repaired:
            fail('PDF 结构损坏；拒绝以修复后的部分内容继续')
        total = len(document)
        if total == 0 or total > MAX_PAGES:
            fail('PDF 必须包含 1～100 页', code='DOCUMENT_LIMIT_EXCEEDED')
        for index, page in enumerate(document):
            number = index + 1
            check(deadline, number)
            try:
                text = page.get_text('text', sort=True).strip()
                # 任意实际显示的图片/矢量图或异常字形均视为需要补全，不以页眉判定整页。
                visual = bool(page.get_image_info() or page.get_drawings())
                needs_ocr = visual or not text or '\ufffd' in text or '\x00' in text
                if needs_ocr:
                    width, height = page.rect.width * 2, page.rect.height * 2
                    if width <= 0 or height <= 0 or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                        fail('144 DPI 渲染尺寸超过 6000 边长或 2000 万像素限制', number, 'DOCUMENT_LIMIT_EXCEEDED')
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False)
                    try:
                        # 仅几乎纯白且无文字层的页面可视为空白。低清晰度有内容页不能静默跳过。
                        blank = not text and min(pix.samples) >= 250
                        if blank:
                            text = ''
                        else:
                            ocr = engine(tuple(context.model(name) for name in ('det', 'rec', 'cls')))
                            result, _ = ocr(pix.tobytes('png'))
                            check(deadline, number)
                            if not result or any(not str(item[1]).strip() or float(item[2]) < 0.5 for item in result):
                                fail('页面有内容但 OCR 无结果或置信度不足，请提供清晰资料', number)
                            # 整页 OCR 替代文字层；不再拼接原文字，防止混合页重复正文。
                            text = '\n'.join(item[1].strip() for item in ordered_lines(result))
                    finally:
                        del pix
                if text:
                    parts.append(f'--- 第 {number} 页 ---\n{text}')
                context.progress('页面已完成' if text else '空白页已跳过', current=number, total=total)
            except PlatformError:
                raise
            except Exception:
                fail('页面解析或 OCR 失败', number)
            check(deadline, number)
    return '\n\n'.join(parts)


def read_docx(path, context, deadline):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                fail('DOCX 解压内容超过 100 MiB', code='DOCUMENT_LIMIT_EXCEEDED')
        document = Document(path)
        # 这些节点含有无法由段落/表格忠实表达的内容，拒绝部分提取。
        unsupported = {'drawing', 'pict', 'object', 'oMath', 'oMathPara', 'altChunk',
                       'txbxContent', 'footnoteReference', 'endnoteReference', 'ins', 'del', 'sdt'}
        if any(element.tag.rsplit('}', 1)[-1] in unsupported for element in document.element.iter()):
            fail('DOCX 含图片、公式、嵌入对象、脚注、修订或内容控件，当前无法保证完整提取；请先转换为 PDF')
        def content(container):
            lines = []
            for item in container.iter_inner_content():
                check(deadline)
                if isinstance(item, Paragraph):
                    if item.text.strip():
                        lines.append(item.text)
                elif isinstance(item, Table):
                    seen = set()
                    for row in item.rows:
                        cells = []
                        for cell in row.cells:
                            # 合并单元格只输出一次；递归保留嵌套表格所在位置。
                            if cell._tc not in seen:
                                seen.add(cell._tc)
                                cells.append('\n'.join(content(cell)))
                            else:
                                cells.append('')
                        lines.append('\t'.join(cells))
            return lines
        result = '\n'.join(content(document))
        check(deadline)
        context.progress('DOCX 正文与表格已完成（无固定分页）', current=1, total=1)
        return result
    except PlatformError:
        raise
    except Exception:
        fail('DOCX 损坏、加密或正文结构无法读取')


@block(
    id='read-document', version='1.0.0', name='读取完整文档',
    description='读取 PDF/DOCX 正文；扫描及混合 PDF 本地 OCR，全文一次性输出。',
    dependencies=['rapidocr-onnxruntime==1.4.4', 'onnxruntime==1.23.2', 'PyMuPDF==1.26.7', 'python-docx==1.2.0'],
    dependencySources=[{'kind': 'index', 'url': 'https://pypi.org/simple'}],
    models=[
        {'name': 'det', 'version': 'PP-OCRv4-mobile-v3.9.2',
         'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.onnx',
         'sha256': 'd2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9', 'filename': 'det.onnx'},
        {'name': 'rec', 'version': 'PP-OCRv4-mobile-v3.9.2',
         'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile.onnx',
         'sha256': '48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b', 'filename': 'rec.onnx'},
        {'name': 'cls', 'version': 'PP-OCRv4-mobile-v3.9.2',
         'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
         'sha256': 'e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c', 'filename': 'cls.onnx'},
    ],
)
def read_document(value: Input, *, context: BlockContext) -> Output:
    deadline = time.monotonic() + MAX_SECONDS
    path = context.file(value.document)
    if value.document.size > MAX_BYTES or path.stat().st_size > MAX_BYTES:
        fail('文件超过 50 MiB', code='FILE_TOO_LARGE')
    text = (read_pdf(path, context, deadline) if value.document.format == 'pdf'
            else read_docx(path, context, deadline))
    check(deadline)
    if not text.strip():
        fail('文档正文为空，不能生成题目')
    return Output(file_name=value.document.original_name, text=text)
