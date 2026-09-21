// 只根据契约标注提供选择控件；输入引用在提交时由后端固定为不可变修订。
(() => {
  let schema = {}, bases = [], generation = 0;
  const selected = new Map(), host = document.querySelector('#task-knowledge');
  const json = document.querySelector('#task-input');
  const fields = value => window.taskFiles.fields(schema, value, 'x-platform-knowledge');
  function render() {
    host.replaceChildren();
    let value; try { value = JSON.parse(json.value); } catch { return; }
    for (const field of fields(value)) {
      const key = JSON.stringify(field.path), row = document.createElement('label');
      row.textContent = `${field.path.join('.') || '知识库'}：`;
      const picker = document.createElement('select'); picker.append(new Option('使用 JSON 中的引用或选择知识库', ''));
      for (const base of bases.filter(item => !item.archived)) picker.append(new Option(base.name, base.knowledgeId));
      picker.value = selected.get(key)?.knowledgeId || '';
      picker.addEventListener('change', () => { if (picker.value) selected.set(key, { knowledgeId: picker.value, revisionId: null }); else selected.delete(key); });
      row.append(picker); host.append(row);
    }
    if (host.children.length) { const note = document.createElement('p'); note.textContent = '选择后在提交时固定当前修订。需要历史修订时，在 JSON 中提供 revisionId 并保持下拉框未选择。'; host.append(note); }
  }
  window.taskKnowledge = {
    async setSchema(value) {
      const token = ++generation; schema = value; selected.clear(); render();
      if (!fields({}).length) return;
      const response = await window.agentPlatform.listKnowledge();
      if (token !== generation) return;
      if (response.ok) { bases = response.data; render(); }
      else host.textContent = response.error.message;
    },
    input(value) {
      for (const field of fields(value)) {
        const reference = selected.get(JSON.stringify(field.path));
        if (!reference) continue;
        if (!field.path.length) value = reference;
        else { let target = value; for (const part of field.path.slice(0, -1)) target = target[part] ??= {}; target[field.path.at(-1)] = reference; }
      }
      return value;
    },
    evidence(run) {
      const container = document.querySelector('#task-evidence'); container.replaceChildren();
      if (!(run.knowledgeBindings || []).length) return;
      const heading = document.createElement('h4'); heading.textContent = '知识库修订与采用证据'; container.append(heading);
      for (const reference of run.knowledgeBindings) { const p = document.createElement('p'); p.textContent = `${reference.knowledgeId} · ${reference.revisionId}`; container.append(p); }
      for (const record of run.evidence || []) {
        const details = document.createElement('details'), title = document.createElement('summary');
        title.textContent = `查询：${record.query} · 候选 ${record.candidates.length} · 选用 ${record.selected.length} · ${record.scopeLimited ? '扫描范围受限' : '声明范围内扫描完成'}`;
        details.append(title);
        const provenance = document.createElement('p'); provenance.textContent = `登记节点 ${record.nodeId} · 资源源码 ${record.resourceDigest}`; details.append(provenance);
        for (const item of record.selected) {
          const p = document.createElement('p'); p.textContent = `${item.documentId} · ${item.versionId} · ${item.locator} · ${item.reader}`;
          const text = document.createElement('pre'); text.textContent = item.text;
          const download = document.createElement('button'); download.type = 'button'; download.textContent = '获取引用原件';
          download.addEventListener('click', async () => { const result = await window.agentPlatform.downloadKnowledgeOriginal(item.reference.knowledgeId, item.versionId); if (!result.ok) download.textContent = result.error.message; });
          details.append(p, text, download);
        }
        const raw = document.createElement('details'), rawTitle = document.createElement('summary'), pre = document.createElement('pre');
        rawTitle.textContent = '完整候选、参数及定位记录'; pre.textContent = JSON.stringify(record, null, 2); raw.append(rawTitle, pre); details.append(raw); container.append(details);
      }
    },
  };
  json.addEventListener('input', render);
})();
