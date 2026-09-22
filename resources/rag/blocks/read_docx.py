"""PDF/DOCX 正文读取；PDF 按页提取并在需要时本地 OCR，DOCX 按段落定位。"""
import zipfile
import time
import math
from functools import lru_cache
from contextlib import closing
import xml.etree.ElementTree as ET
from hashlib import sha256
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import DocumentReadRequest, Evidence
from agent_platform.contracts.retrieval import DocumentSelection, ParsedCorpus
from agent_platform.contracts.errors import PlatformError, ErrorResponse

MAX_PAGES = 100
MAX_SIDE = 6000
MAX_PIXELS = 20_000_000
MAX_SECONDS = 240
READER = 'rag-read-docx@2.0.0:pdf-page-ocr-docx-paragraph-whitespace-v1'
NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def fail(reason, page=None, code='DOCUMENT_READ_ERROR'):
    where = f'第 {page} 页：' if page is not None else ''
    raise PlatformError(ErrorResponse(code=code, stage='rag.read', message=where + reason))


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


def empty_ocr_box(item, pix):
    # 检测框边缘可能擦到相邻字形；空识别且内部像素全白才视为空白误检。
    if str(item[1]).strip():
        return False
    points = item[0]
    left = max(0, math.floor(min(point[0] for point in points)) + 1)
    top = max(0, math.floor(min(point[1] for point in points)) + 1)
    right = min(pix.width, math.ceil(max(point[0] for point in points)) - 1)
    bottom = min(pix.height, math.ceil(max(point[1] for point in points)) - 1)
    return left < right and top < bottom and all(
        min(pix.pixel(x, y)) >= 250
        for y in range(top, bottom) for x in range(left, right)
    )


def read_pdf(path, context, deadline):
    import pymupdf
    try:
        document = pymupdf.open(path)
    except Exception:
        fail('PDF 损坏或无法打开')
    with document:
        if not document.is_pdf:
            fail('文件不是有效 PDF')
        # 带权限加密标记的 PDF 也可能无需打开密码；以实际打开状态判断。
        if document.needs_pass:
            fail('PDF 需要打开密码；请提供无需密码即可打开的文件')
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
                            # PDF 渲染已应用页面旋转；保持呈现方向，避免分类器误翻转正常文字行。
                            result, _ = ocr(pix.tobytes('png'), use_cls=False)
                            check(deadline, number)
                            result = [item for item in (result or []) if not empty_ocr_box(item, pix)]
                            if not result or any(not str(item[1]).strip() or float(item[2]) < 0.5 for item in result):
                                fail('页面有内容但 OCR 无结果或置信度不足，请提供清晰资料', number)
                            # 整页 OCR 替代文字层；不再拼接原文字，防止混合页重复正文。
                            text = '\n'.join(item[1].strip() for item in ordered_lines(result))
                    finally:
                        del pix
                if text:
                    yield f'page:{number}', ' '.join(text.split())
                context.progress('页面已完成' if text else '空白页已跳过', current=number, total=total)
            except PlatformError:
                raise
            except Exception:
                fail('页面解析或 OCR 失败', number)
            check(deadline, number)



def read_docx(path):
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > 50 * 1024 * 1024:
                raise PlatformError(ErrorResponse(code='DOCUMENT_LIMIT_EXCEEDED', stage='rag.read', message='DOCX 正文 XML 超过读取上限'))
            xml = archive.read(info)
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                raise ValueError('不支持实体声明')
            root = ET.fromstring(xml)
            if root.tag != NAMESPACE + 'document':
                raise ValueError('DOCX 根元素无效')
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, OSError, RuntimeError):
        raise PlatformError(ErrorResponse(code='DOCUMENT_CORRUPTED', stage='rag.read', message='DOCX 正文损坏或不受支持')) from None
    for number, paragraph in enumerate(root.iter(NAMESPACE + 'p'), 1):
        text = ''.join(node.text or '' if node.tag == NAMESPACE + 't' else ' '
                       for node in paragraph.iter() if node.tag in (NAMESPACE + 't', NAMESPACE + 'tab', NAMESPACE + 'br', NAMESPACE + 'cr'))
        yield f'paragraph:{number}', ' '.join(text.split())


@block(
    id='rag-read-docx', version='2.0.0', name='读取 PDF/DOCX 正文',
    description='受控读取知识库 PDF/DOCX，PDF 按页定位并支持本地 OCR，DOCX 按段落定位。达到字符或片段上限标明范围受限。须准备声明的依赖与模型，无参考输入。',
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
async def run(value: NodeInput[DocumentSelection, tuple[()]], *, context: BlockContext) -> ParsedCorpus:
    deadline = time.monotonic() + MAX_SECONDS
    selection = value.primary
    limits = selection.request.limits
    fragments, scanned, used = [], [], 0
    limited = selection.scope_limited
    for document_index, document in enumerate(selection.documents):
        if used >= limits.max_characters or len(fragments) >= limits.max_fragments:
            limited = True
            break
        path = await context.knowledge_file(DocumentReadRequest(reference=selection.reference,
            version_id=document.version_id, max_bytes=limits.max_file_bytes))
        paragraphs = read_pdf(path, context, deadline) if document.format == 'pdf' else read_docx(path)
        scanned.append(document.version_id)
        with closing(paragraphs):
            for location, text in paragraphs:
                check(deadline)
                for offset in range(0, len(text), limits.fragment_characters):
                    if used >= limits.max_characters or len(fragments) >= limits.max_fragments:
                        limited = True
                        break
                    fragment = text[offset:offset + min(limits.fragment_characters, limits.max_characters - used)]
                    if len(fragment) < min(limits.fragment_characters, len(text) - offset):
                        limited = True
                    locator = f'{location}:characters:{offset + 1}-{offset + len(fragment)}'
                    fragment_id = sha256(f'{document.version_id}:{READER}:{locator}'.encode()).hexdigest()
                    fragments.append(Evidence(reference=selection.reference, document_id=document.document_id,
                        version_id=document.version_id, fragment_id=fragment_id, text=fragment,
                        sha256=sha256(fragment.encode()).hexdigest(), locator=locator, reader=READER))
                    used += len(fragment)
                if limited and (used >= limits.max_characters or len(fragments) >= limits.max_fragments):
                    break
        context.progress('文档正文读取', current=document_index + 1, total=len(selection.documents))
    return ParsedCorpus(selection=selection, scanned_versions=scanned, fragments=fragments, scope_limited=limited)
