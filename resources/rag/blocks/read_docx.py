"""标准库 DOCX 读取：段落顺序、制表/换行转空格、连续空白折叠；不伪造页码。"""
import zipfile
import xml.etree.ElementTree as ET
from hashlib import sha256
from agent_platform.blocks import block
from agent_platform.blocks.context import BlockContext
from agent_platform.contracts.node_input import NodeInput
from agent_platform.contracts.knowledge import DocumentReadRequest, Evidence
from agent_platform.contracts.retrieval import DocumentSelection, ParsedCorpus
from agent_platform.contracts.errors import PlatformError, ErrorResponse

READER = 'rag-read-docx@1.0.0:paragraph-whitespace-v1'
NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


@block(id='rag-read-docx', version='1.0.0', name='读取 DOCX 段落', description='受控获取原件，按规范化段落与字符区间定位；表格中的段落同样参与。达到字符或片段上限标明范围受限。无参考输入。')
async def run(value: NodeInput[DocumentSelection, tuple[()]], *, context: BlockContext) -> ParsedCorpus:
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
        scanned.append(document.version_id)
        for number, paragraph in enumerate(root.iter(NAMESPACE + 'p'), 1):
            text = ''.join(node.text or '' if node.tag == NAMESPACE + 't' else ' '
                           for node in paragraph.iter() if node.tag in (NAMESPACE + 't', NAMESPACE + 'tab', NAMESPACE + 'br', NAMESPACE + 'cr'))
            text = ' '.join(text.split())
            for offset in range(0, len(text), limits.fragment_characters):
                if used >= limits.max_characters or len(fragments) >= limits.max_fragments:
                    limited = True
                    break
                fragment = text[offset:offset + min(limits.fragment_characters, limits.max_characters - used)]
                if len(fragment) < min(limits.fragment_characters, len(text) - offset):
                    limited = True
                locator = f'paragraph:{number}:characters:{offset + 1}-{offset + len(fragment)}'
                fragment_id = sha256(f'{document.version_id}:{READER}:{locator}'.encode()).hexdigest()
                fragments.append(Evidence(reference=selection.reference, document_id=document.document_id,
                    version_id=document.version_id, fragment_id=fragment_id, text=fragment,
                    sha256=sha256(fragment.encode()).hexdigest(), locator=locator, reader=READER))
                used += len(fragment)
            if limited and (used >= limits.max_characters or len(fragments) >= limits.max_fragments):
                break
        context.progress('DOCX 段落读取', current=document_index + 1, total=len(selection.documents))
    return ParsedCorpus(selection=selection, scanned_versions=scanned, fragments=fragments, scope_limited=limited)
