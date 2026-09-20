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
  // 只有确定能由文件控件完整构造的契约才隐藏 JSON；数组和分支仍需用户提供结构。
  function fileOnly(schema, node = schema, ancestors = []) {
    if (node['x-platform-file']) return true;
    if (node.$ref) {
      if (ancestors.includes(node.$ref)) return false;
      return fileOnly(schema, schema.$defs?.[node.$ref.split('/').pop()] || {}, [...ancestors, node.$ref]);
    }
    const children = Object.values(node.properties || {});
    return node.type === 'object' && node.additionalProperties === false && children.length > 0 &&
      !node.anyOf && !node.oneOf && !node.allOf && children.every(child => fileOnly(schema, child, ancestors));
  }
  if (typeof module !== 'undefined') { module.exports = { fields, fileOnly }; return; }
  let schema = {}, generation = 0, pending = 0, onlyFiles = false;
  const saved = new Map();
  const host = document.querySelector('#task-files');
  const input = document.querySelector('#task-input');
  const changed = () => window.dispatchEvent(new Event('task-files-change'));
  function render() {
    host.replaceChildren();
    let value;
    try { value = onlyFiles ? {} : JSON.parse(input.value); } catch { return; }
    for (const field of fields(schema, value)) {
      const key = JSON.stringify(field.path), row = document.createElement('p');
      const label = document.createElement('span');
      const reference = saved.get(key);
      label.textContent = `${field.path.join('.') || '任务文件'}${field.required ? '（必填）' : '（可选）'}：` +
        (reference ? `${reference.originalName} · ${reference.size} 字节 · 已保存 ` : '未选择 ');
      const select = document.createElement('input');
      select.hidden = true;
      select.type = 'file';select.accept = field.formats.map(format => `.${format}`).join(',');
      select.setAttribute('aria-label', `${field.path.join('.') || '任务文件'}${reference ? '：替换文件' : '：选择文件'}`);
      select.disabled = pending > 0;
      select.onchange = async () => {
        const file = select.files?.[0];
        if (!file) return;
        const current = generation;
        pending++; changed(); render();
        window.dispatchEvent(new CustomEvent('task-files-notice', { detail: `正在保存 ${file.name}…` }));
        try {
          const response = await window.agentPlatform.uploadTaskFile(file);
          if (current !== generation) { if (response.ok && response.data) await window.agentPlatform.removeTaskFile(response.data.fileId); return; }
          if (!response.ok) { window.dispatchEvent(new CustomEvent('task-files-error', { detail: response.error.message })); return; }
          if (!response.data) throw new Error('文件保存响应为空，请重新选择文件');
          if (!field.formats.includes(response.data.format)) {
            await window.agentPlatform.removeTaskFile(response.data.fileId);
            window.dispatchEvent(new CustomEvent('task-files-error', { detail: '所选文件格式不符合此字段要求' }));return;
          }
          saved.set(key, response.data);
          window.dispatchEvent(new CustomEvent('task-files-notice', { detail: `已保存文件：${response.data.originalName}` }));
          if (reference) await window.agentPlatform.removeTaskFile(reference.fileId);
        } catch (error) {
          if (current === generation) window.dispatchEvent(new CustomEvent('task-files-error', { detail: error.message || '文件保存失败，请重试' }));
        } finally { pending--; changed(); render(); }
      };
      const choose = document.createElement('button');
      choose.type = 'button';choose.textContent = reference ? '替换文件' : `选择 ${field.formats.map(format => format.toUpperCase()).join(' / ')}`;
      choose.disabled = pending > 0;choose.onclick = () => select.click();
      row.append(label, choose, select);
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
      generation++;schema = value;saved.clear();onlyFiles = fileOnly(schema);
      document.querySelector('#task-json-input').hidden = onlyFiles;
      document.querySelector('#task-input-kind').textContent = onlyFiles ? '文件' : fields(schema).length ? 'JSON + 文件' : 'JSON';
      input.disabled = onlyFiles;input.required = !onlyFiles;
      input.setCustomValidity('');render();changed();
    },
    input() {
      let value = onlyFiles ? {} : JSON.parse(input.value);
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
