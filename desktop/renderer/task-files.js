/* 按公开契约标注生成文件控件，其他字段继续使用 JSON 输入。 */
(() => {
  function fields(schema, input = {}) {
    const result = [];
    function walk(node, path, value, required, ancestors = []) {
      if (node['x-platform-file']) { result.push({ path, required, formats: node['x-platform-file'].formats }); return; }
      if (node.$ref) {
        if (ancestors.includes(node.$ref)) return;
        walk(schema.$defs?.[node.$ref.split('/').pop()] || {}, path, value, required, [...ancestors, node.$ref]);
      }
      for (const [key, child] of Object.entries(node.properties || {})) {
        walk(child, [...path, key], value?.[key], required && (node.required || []).includes(key), ancestors);
      }
      if (node.items && Array.isArray(value)) value.forEach((item, index) => walk(node.items, [...path, index], item, true, ancestors));
      for (const child of [...(node.anyOf || []), ...(node.oneOf || []), ...(node.allOf || [])]) {
        if (child.type !== 'null') walk(child, path, value, required && !(node.anyOf || []).some(c => c.type === 'null'), ancestors);
      }
    }
    walk(schema, [], input, true);
    return [...new Map(result.map(field => [JSON.stringify(field.path), field])).values()];
  }
  if (typeof module !== 'undefined') { module.exports = { fields }; return; }
  let schema = {}, generation = 0, pending = 0;
  const saved = new Map();
  const host = document.querySelector('#task-files');
  const input = document.querySelector('#task-input');
  const changed = () => window.dispatchEvent(new Event('task-files-change'));
  function render() {
    host.replaceChildren();
    let value;
    try { value = JSON.parse(input.value); } catch { return; }
    for (const field of fields(schema, value)) {
      const key = JSON.stringify(field.path), row = document.createElement('p');
      const label = document.createElement('span');
      const reference = saved.get(key);
      label.textContent = `${field.path.join('.') || '任务文件'}${field.required ? '（必填）' : '（可选）'}：` +
        (reference ? `${reference.originalName} · ${reference.size} 字节 · 已保存 ` : '未选择 ');
      const select = document.createElement('button');select.type = 'button';select.textContent = reference ? '替换文件' : '选择 PDF / DOCX';select.disabled = pending > 0;
      select.onclick = async () => {
        const current = generation;
        pending++; changed(); render();
        label.textContent = '正在选择并保存文件…';
        try {
          const response = await window.agentPlatform.selectTaskFile();
          if (current !== generation) { if (response.ok && response.data) await window.agentPlatform.removeTaskFile(response.data.fileId); return; }
          if (!response.ok) { window.dispatchEvent(new CustomEvent('task-files-error', { detail: response.error.message })); return; }
          if (!response.data) { window.dispatchEvent(new CustomEvent('task-files-notice', { detail: '已取消选择，保留原附件。' }));return; }
          if (!field.formats.includes(response.data.format)) {
            await window.agentPlatform.removeTaskFile(response.data.fileId);
            window.dispatchEvent(new CustomEvent('task-files-error', { detail: '所选文件格式不符合此字段要求' }));return;
          }
          saved.set(key, response.data);
          if (reference) await window.agentPlatform.removeTaskFile(reference.fileId);
        } finally { pending--; changed(); render(); }
      };
      row.append(label, select);
      if (reference) {
        const remove = document.createElement('button');remove.type = 'button';remove.textContent = '移除';remove.disabled = pending > 0;
        remove.onclick = async () => { saved.delete(key);render();await window.agentPlatform.removeTaskFile(reference.fileId); };
        row.append(remove);
      }
      host.append(row);
    }
    if (pending) { const status = document.createElement('p');status.textContent = '正在选择并保存文件，请等待保存完成。';host.append(status); }
  }
  window.taskFiles = {
    get pending() { return pending > 0; },
    setSchema(value) {
      generation++;schema = value;saved.clear();render();changed();
    },
    input(value) {
      if (pending) throw new Error('文件尚未保存完成');
      for (const field of fields(schema, value)) {
        const reference = saved.get(JSON.stringify(field.path));
        if (!reference) {
          if (field.required) throw new Error(`请先选择并保存文件：${field.path.join('.')}`);
          continue;
        }
        if (!field.path.length) value = reference;
        else {
          let parent = value;
          for (const key of field.path.slice(0, -1)) parent = parent[key] ??= {};
          parent[field.path.at(-1)] = reference;
        }
      }
      return value;
    },
  };
  input.addEventListener('input', render);
})();
