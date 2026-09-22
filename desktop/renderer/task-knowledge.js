// 只根据契约标注提供选择控件；输入引用在提交时由后端固定为不可变修订。
(() => {
  let schema = {}, bases = [], generation = 0;
  const selected = new Map(), host = document.querySelector('#task-knowledge');
  const json = document.querySelector('#task-input');
  const fields = value => window.taskFiles.fields(schema, value, 'x-platform-knowledge');
  function resolve(node) {
    return node.$ref ? { ...(schema.$defs?.[node.$ref.split('/').pop()] || {}), ...node } : node;
  }
  function hasKnowledge(node) {
    return node && typeof node === 'object' && (node['x-platform-knowledge'] || Object.values(node).some(hasKnowledge));
  }
  // 样例只展示必填业务字段。可选参数交给契约默认值，知识库引用由控件补齐。
  function businessExample(node, value, ancestors = []) {
    if (node['x-platform-knowledge']) return undefined;
    if (node.$ref && ancestors.includes(node.$ref)) return value;
    const next = node.$ref ? [...ancestors, node.$ref] : ancestors;
    node = resolve(node);
    if (node['x-platform-knowledge']) return undefined;
    if (node.type === 'object' && node.properties) {
      const result = {};
      for (const key of node.required || []) {
        const child = businessExample(node.properties[key] || {}, value?.[key], next);
        if (child !== undefined) result[key] = child;
      }
      return result;
    }
    if (node.type === 'array' && node.items) return (Array.isArray(value) ? value : []).map(item => businessExample(node.items, item, next) ?? {});
    if (value !== undefined) return structuredClone(value);
    if (node.default !== undefined) return structuredClone(node.default);
    if (node.const !== undefined) return node.const;
    if (node.enum?.length) return node.enum[0];
    return node.type === 'string' ? '' : node.type === 'boolean' ? false : ['integer', 'number'].includes(node.type) ? 0 : null;
  }
  function render() {
    host.replaceChildren();
    let value = {}; try { value = JSON.parse(json.value); } catch { /* 必填引用控件不依赖 JSON 是否已填写。 */ }
    for (const field of fields(value)) {
      const key = JSON.stringify(field.path), row = document.createElement('label');
      row.textContent = `${field.path.length ? field.path.join('.') + ' · ' : ''}知识库${field.required ? '（必选）' : '（可选）'}：`;
      const picker = document.createElement('select'); picker.append(new Option('请选择知识库', ''));
      for (const base of bases.filter(item => !item.archived)) picker.append(new Option(base.name, base.knowledgeId));
      picker.value = selected.get(key)?.knowledgeId || '';
      picker.required = field.required;
      picker.addEventListener('change', () => { if (picker.value) selected.set(key, { knowledgeId: picker.value, revisionId: null }); else selected.delete(key); });
      row.append(picker); host.append(row);
    }
    if (host.children.length) { const note = document.createElement('p'); note.textContent = '只需填写上方业务内容并选择知识库，平台会在提交时自动添加引用并固定当前修订，无需填写知识库 ID。'; host.append(note); }
  }
  window.taskKnowledge = {
    async setSchema(value, example) {
      const token = ++generation; schema = value; bases = []; selected.clear();
      if (hasKnowledge(schema)) {
        json.value = JSON.stringify(businessExample(schema, example) ?? {}, null, 2);
        json.dispatchEvent(new Event('input'));
      }
      render();
      if (!hasKnowledge(schema)) return;
      const response = await window.agentPlatform.listKnowledge();
      if (token !== generation) return;
      if (response.ok) { bases = response.data; render(); }
      else host.textContent = response.error.message;
    },
    example(value) {
      return hasKnowledge(schema) ? businessExample(schema, value) ?? {} : value;
    },
    input(value) {
      for (const field of fields(value)) {
        const reference = selected.get(JSON.stringify(field.path));
        if (!reference && field.required) throw new Error(`请选择知识库：${field.path.join('.') || '知识库'}`);
        // 页面由选择控件负责引用；不能使用样例或粘贴 JSON 中遗留的知识库 ID。
        if (!field.path.length) value = reference ?? null;
        else {
          let target = value;
          for (const part of field.path.slice(0, -1)) {
            if (target[part] == null && !reference) { target = null; break; }
            target = target[part] ??= {};
          }
          if (!target) continue;
          if (reference) target[field.path.at(-1)] = reference;
          else delete target[field.path.at(-1)];
        }
      }
      return value;
    },
    evidence(run) {
      const container = document.querySelector('#task-evidence'); container.replaceChildren();
      if (!(run.knowledgeBindings || []).length) return;
      const heading = document.createElement('h4'); heading.textContent = '知识库修订与采用证据'; container.append(heading);
      for (const reference of run.knowledgeBindings) { const p = document.createElement('p'); p.textContent = `${reference.knowledgeId} · ${reference.revisionId}`; container.append(p); }
      if (run.embeddingSnapshot) {
        const model = document.createElement('p');
        model.textContent = `本地语义模型：${run.embeddingSnapshot.manifest.name} · ${run.embeddingSnapshot.modelId}`;
        container.append(model);
      }
      for (const record of run.semanticSearches || []) {
        const details = document.createElement('details'), title = document.createElement('summary'), pre = document.createElement('pre');
        const stats = record.result.stats;
        title.textContent = `语义检索：${record.query} · 候选 ${record.result.candidates.length} · 新编码 ${stats.encodedFragments} · 缓存命中 ${stats.cacheHits} · 推理 ${stats.inferenceSeconds.toFixed(3)} 秒`;
        pre.textContent = JSON.stringify(record, null, 2);
        details.append(title, pre); container.append(details);
      }
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
