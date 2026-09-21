// 文档逐项导入；用 textContent 展示文件名、错误和元数据。
(() => {
  const api = window.agentPlatform;
  const el = id => document.querySelector(`#knowledge-${id}`);
  let bases = [], offset = 0, next = null, revision = null, busy = false;
  const checked = response => { if (!response.ok) throw new Error(response.error.message); return response.data; };
  const current = () => bases.find(item => item.knowledgeId === el('select').value);
  function controls() {
    for (const input of document.querySelectorAll('[data-page="knowledge"] input, [data-page="knowledge"] button, #knowledge-select')) input.disabled = busy;
    el('upload').disabled = busy || !current() || current().archived;
    el('prev').disabled = busy || offset === 0;
    el('next').disabled = busy || next === null;
  }
  async function action(work) {
    if (busy) return;
    busy = true; controls(); el('status').textContent = '';
    try { await work(); } catch (error) { el('status').textContent = error.message; }
    finally { busy = false; controls(); }
  }
  function button(text, handler) {
    const node = document.createElement('button'); node.type = 'button'; node.textContent = text;
    node.addEventListener('click', () => action(handler)); return node;
  }
  async function documents() {
    const base = current(); el('documents').replaceChildren(); next = null;
    if (!base) { el('page').textContent = ''; return; }
    const page = checked(await api.knowledgeDocuments(base.knowledgeId, { offset, limit: 20, ...(revision ? { revisionId: revision } : {}) }));
    revision = page.reference.revisionId; next = page.nextOffset;
    el('revision').textContent = `知识库 ${base.knowledgeId} · 当前查看修订 ${revision}`;
    el('page').textContent = ` 共 ${page.total} 份 · 第 ${Math.floor(offset / 20) + 1} 页 `;
    for (const item of page.items) {
      const card = document.createElement('article'); card.className = 'settings-card';
      const title = document.createElement('h4'); title.textContent = item.originalName; card.append(title);
      const metadata = document.createElement('p'); metadata.textContent = `原件可读取 · ${item.size} 字节 · ${item.versionId} · SHA-256 ${item.sha256}`; card.append(metadata);
      card.append(button('获取原件', async () => checked(await api.downloadKnowledgeOriginal(base.knowledgeId, item.versionId))));
      card.append(button('版本记录', async () => {
        const versions = checked(await api.knowledgeVersions(base.knowledgeId, item.documentId));
        const list = document.createElement('ul');
        for (const version of versions) {
          const row = document.createElement('li'); row.textContent = `${version.createdAt} · ${version.originalName} · ${version.versionId} · ${version.size} 字节 · ${version.sha256} `;
          row.append(button('获取此版本', async () => checked(await api.downloadKnowledgeOriginal(base.knowledgeId, version.versionId)))); list.append(row);
        }
        card.querySelector('ul')?.remove(); card.append(list);
      }));
      if (!base.archived) {
        const replace = document.createElement('label'); replace.textContent = '替换版本 ';
        const file = document.createElement('input'); file.type = 'file'; file.accept = '.docx';
        file.addEventListener('change', () => action(async () => {
          if (!file.files[0]) return;
          checked(await api.uploadKnowledgeDocument(base.knowledgeId, file.files[0], item.documentId));
          revision = null; await load(base.knowledgeId);
        })); replace.append(file); card.append(replace);
        card.append(button('移出知识库', async () => {
          checked(await api.removeKnowledgeDocument(base.knowledgeId, item.documentId));
          offset = 0; revision = null; await load(base.knowledgeId);
        }));
      }
      el('documents').append(card);
    }
  }
  async function load(selected = el('select').value) {
    bases = checked(await api.listKnowledge());
    el('select').replaceChildren(new Option('新建知识库', ''));
    for (const base of bases) el('select').add(new Option(`${base.name}${base.archived ? '（已归档）' : ''}`, base.knowledgeId));
    el('select').value = selected;
    el('name').value = current()?.name || ''; el('archived').checked = current()?.archived || false;
    el('revision').textContent = ''; await documents();
  }
  el('select').addEventListener('change', () => action(async () => { offset = 0; revision = null; await load(); }));
  el('refresh').addEventListener('click', () => action(async () => { offset = 0; revision = null; await load(); }));
  el('form').addEventListener('submit', event => {
    event.preventDefault(); action(async () => {
      const value = current() ? checked(await api.updateKnowledge(current().knowledgeId, { name: el('name').value, archived: el('archived').checked }))
        : checked(await api.createKnowledge({ name: el('name').value }));
      revision = null; offset = 0; await load(value.knowledgeId);
    });
  });
  el('upload').addEventListener('change', () => {
    const files = Array.from(el('upload').files), id = current()?.knowledgeId;
    action(async () => {
      el('import-results').replaceChildren();
      for (const file of files) {
        const row = document.createElement('li'); row.textContent = `${file.name}：导入中…`; el('import-results').append(row);
        try { const version = checked(await api.uploadKnowledgeDocument(id, file)); row.textContent = `${file.name}：原件已保存 · ${version.versionId}`; }
        catch (error) { row.textContent = `${file.name}：导入失败 · ${error.message}`; }
      }
      el('upload').value = ''; revision = null; offset = 0; await load(id);
    });
  });
  el('prev').addEventListener('click', () => action(async () => { offset = Math.max(0, offset - 20); await documents(); }));
  el('next').addEventListener('click', () => action(async () => { if (next !== null) offset = next; await documents(); }));
  window.knowledgeManager = { refresh: () => action(load) };
})();
