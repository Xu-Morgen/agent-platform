/* 页面只编辑绑定，契约兼容性由后端权威预检决定。 */
const flowEditor = (() => {
  const $ = id => document.getElementById(id);
  const clone = value => structuredClone(value);
  let resources = [], draftId = '', revision = 0;
  const empty = () => ({name: '', inputContract: '', outputContract: '', flow: [], output: [], nodeConfigurations: {}, examples: []});
  let content = empty();
  function el(tag, text) { const item = document.createElement(tag); if (text) item.textContent = text; return item; }
  function button(text, action) { const item = el('button', text); item.type = 'button'; item.onclick = action; return item; }
  function choices(items, value, change) {
    const select = el('select'); select.add(new Option('请选择', ''));
    for (const [id, name] of items) select.add(new Option(name, id));
    // 保留失效引用，防止删除或移动节点后静默重新接线。
    if (value && !items.some(([id]) => id === value)) select.add(new Option('不可用引用：' + value, value));
    select.value = value || ''; select.onchange = () => change(select.value); return select;
  }
  function contracts() {
    return resources.flatMap(r => r.kind === 'contract' ? [[r.resourceId, r.name, r.schemas.value]]
      : [['input', '输入'], ['output', '输出']].map(([key, name]) => [r[key + 'Contract'], r.name + ' · ' + name, r.schemas[key]]));
  }
  function schema(ref) { return contracts().find(([id]) => id === ref)?.[2] || {}; }
  function paths(value, root = value, prefix = [], depth = 0) {
    if (depth > 8) return [];
    if (value.$ref) value = root.$defs?.[value.$ref.split('/').pop()] || {};
    return [prefix, ...Object.entries(value.properties || {}).flatMap(([key, child]) => paths(child, root, [...prefix, key], depth + 1))];
  }
  function sourceOptions(nodes) {
    const ports = [[{kind:'input', path:[]}, '服务输入', content.inputContract], ...nodes.map(n => [
      {kind:'node', nodeId:n.nodeId, path:[]}, n.nodeId, resources.find(r => r.resourceId === n.artifactRef)?.outputContract])];
    return ports.flatMap(([source, title, ref]) => paths(schema(ref)).map(path => [JSON.stringify({...source, path}), title + (path.length ? '.' + path.join('.') : '（完整值）')]));
  }
  function bindings(target, values, contract, nodes) {
    target.replaceChildren();
    values.forEach((binding, i) => {
      const row = el('div'); row.className = 'binding-row';
      const label = el('span', '入口 ← 来源');
      const destinations = paths(schema(contract)).map(path => [JSON.stringify(path), path.join('.') || '完整输入']);
      const dest = choices(destinations, JSON.stringify(binding.target), value => { if (value) { binding.target = JSON.parse(value); changed(); } });
      dest.setAttribute('aria-label', '目标端口');
      const options = sourceOptions(nodes); options.push(['constant', '常量（JSON）']);
      const source = choices(options, binding.source.kind === 'constant' ? 'constant' : JSON.stringify(binding.source), value => {
        if (!value) return;
        binding.source = value === 'constant' ? {kind:'constant', value:null} : JSON.parse(value); changed(); render();
      }); source.setAttribute('aria-label', '来源端口');
      row.append(label, dest, source);
      if (binding.source.kind === 'constant') {
        const input = el('input'); input.value = JSON.stringify(binding.source.value); input.setAttribute('aria-label', '常量 JSON');
        input.onchange = () => { try { binding.source.value = JSON.parse(input.value); input.setCustomValidity(''); changed(); } catch { input.setCustomValidity('请输入合法 JSON'); input.reportValidity(); } }; row.append(input);
      }
      row.append(button('删除接线', () => { values.splice(i,1); changed(); render(); })); target.append(row);
    });
    target.append(button('添加接线', () => { values.push({target:[],source:{kind:'input',path:[]}}); changed(); render(); }));
  }
  function issues(result) {
    $('flow-issues').replaceChildren();
    for (const issue of result.issues || []) {
      const item = el('li', `${issue.nodeId || '服务'} · ${(issue.fieldPath || []).join('.')} · ${issue.reason}`);
      item.dataset.nodeId = issue.nodeId || ''; $('flow-issues').append(item);
    }
    $('service-result').textContent = result.valid ? '拼图校验通过' : '拼图未通过校验，请按节点及端口修正';
  }
  async function validate() {
    const current = revision;
    const response = await window.agentPlatform.validateFlow({content: clone(content)});
    if (revision !== current) return;
    if (response.ok) issues(response.data); else $('service-result').textContent = response.error.message;
    return response;
  }
  let timer;
  function changed() { revision++; $('service-result').textContent = '草稿已修改，等待校验'; clearTimeout(timer); timer = setTimeout(validate, 250); }
  function render() {
    $('service-name').value = content.name;
    for (const [id,key] of [['flow-input','inputContract'],['flow-output','outputContract']]) {
      const select = choices(contracts(), content[key], value => { content[key] = value; changed(); render(); });
      select.id = id; $(id).replaceWith(select);
    }
    $('flow-nodes').replaceChildren();
    content.flow.forEach((node, index) => {
      const resource = resources.find(r => r.resourceId === node.artifactRef);
      const card = el('fieldset'); card.dataset.nodeId = node.nodeId;
      card.append(el('legend', `${index + 1}. ${resource?.name || '资源未加载'} · ${node.nodeId}`), el('p', resource?.description));
      card.append(button('上移', () => move(index,-1)), button('下移', () => move(index,1)), button('删除节点', () => {
        content.flow.splice(index,1); delete content.nodeConfigurations[node.nodeId]; changed(); render();
      }));
      const ports = el('div'); bindings(ports,node.inputs,resource?.inputContract,content.flow.slice(0,index)); card.append(ports);
      const detail = el('details'); detail.append(el('summary','输入／输出契约'),el('pre',JSON.stringify(resource?.schemas,null,2)));card.append(detail);
      if (node.kind === 'package') card.append(el('p', '包节点尚未配置（配置窗将在下一任务交付）'));
      $('flow-nodes').append(card);
    });
    bindings($('flow-output-bindings'),content.output,content.outputContract,content.flow);
  }
  function move(index, delta) {
    const next = index + delta; if (next < 0 || next >= content.flow.length) return;
    [content.flow[index],content.flow[next]] = [content.flow[next],content.flow[index]]; changed(); render();
  }
  function add(resource) {
    let i = 1; while (content.flow.some(n => n.nodeId === 'node_' + i)) i++;
    content.flow.push({kind:resource.kind,nodeId:'node_' + i,artifactRef:resource.resourceId,inputs:[]});changed();render();
  }
  async function refresh() {
    const result = await window.agentPlatform.listResources();
    if (!result.ok) { $('load-result').textContent = result.error.message; return; }
    resources = result.data; $('module-library').replaceChildren();
    for (const resource of resources) {
      const item = el('article'); item.append(el('strong',resource.name),el('p',resource.description));
      if (resource.kind !== 'contract') item.append(button('插入 ' + resource.name, () => add(resource)));
      $('module-library').append(item);
    }
    await refreshDrafts(); render();
  }
  async function refreshDrafts() {
    const result = await window.agentPlatform.listDrafts(); if (!result.ok) return;
    $('draft-select').replaceChildren(new Option('新建草稿',''));
    for (const doc of result.data) $('draft-select').add(new Option(doc.content.name || doc.draftId,doc.draftId));
    $('draft-select').value = draftId;
  }
  $('load-form').onsubmit = async event => {
    event.preventDefault(); const body = {kind:$('load-kind').value,path:$('load-path').value};
    if (body.kind === 'contract') body.symbol = $('load-symbol').value;
    const response = await window.agentPlatform.loadResource(body);
    $('load-result').textContent = response.ok ? '已加载 ' + response.data.name : response.error.message;
    if (response.ok) await refresh();
  };
  $('service-name').oninput = () => { content.name = $('service-name').value; changed(); };
  $('flow-validate').onclick = validate;
  $('draft-save').onclick = async () => {
    const body = {content:clone(content)};
    const result = draftId ? await window.agentPlatform.updateDraft(draftId,body) : await window.agentPlatform.createDraft(body);
    if (!result.ok) { $('draft-result').textContent = result.error.message; return; }
    draftId = result.data.draftId; await refreshDrafts(); $('draft-result').textContent = '草稿已保存 ' + draftId;
  };
  $('draft-new').onclick = () => { draftId = ''; content = empty(); $('draft-select').value = ''; changed();render(); };
  $('draft-select').onchange = async () => {
    const id = $('draft-select').value; if (!id) return;
    const result = await window.agentPlatform.getDraft(id);
    if (!result.ok) { $('draft-result').textContent = result.error.message; return; }
    draftId = id; content = {...empty(),...clone(result.data.content)}; changed();render();
  };
  render();
  return {refresh, validate};
})();
