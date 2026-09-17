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
    $('global-budget').hidden = !content.budget;
    if (content.budget) {
      $('global-loop').value = content.budget.loopLimit;
      $('global-token').value = content.budget.tokenLimit;
      $('global-strict').checked = content.budget.strictTokenLimit;
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
      if (node.kind === 'package') card.append(button('配置 ' + node.nodeId, () => configure(node, resource)),
        el('p', content.nodeConfigurations[node.nodeId] ? '已配置，最终状态以拼图校验为准' : '无效：尚未配置参数、预算及环境'));
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
    if (resource.kind === 'package') {
      const defaults = resource.budgetDefaults;
      if (!content.budget) content.budget = {...defaults, strictTokenLimit:true};
      else { content.budget.loopLimit += defaults.loopLimit; content.budget.tokenLimit += defaults.tokenLimit; }
    }
    content.flow.push({kind:resource.kind,nodeId:'node_' + i,artifactRef:resource.resourceId,inputs:[]});changed();render();
  }
  for (const [id, key] of [['global-loop','loopLimit'],['global-token','tokenLimit'],['global-strict','strictTokenLimit']]) {
    $(id).onchange = () => { content.budget[key] = key === 'strictTokenLimit' ? $(id).checked : Number($(id).value); changed(); };
  }
  async function configure(node, resource) {
    const config = clone(content.nodeConfigurations[node.nodeId] || {parameters:{},budget:resource.budgetDefaults,capabilities:{}});
    const response = await window.agentPlatform.listEnvironments();
    if (!response.ok) { $('service-result').textContent = response.error.message; return; }
    const fields = [], caps = [];
    $('node-fields').replaceChildren(); $('node-capabilities').replaceChildren(); $('node-errors').replaceChildren();
    $('node-title').textContent = resource.name + ' · ' + node.nodeId;
    for (const [key, definition] of Object.entries(resource.schemas.configuration.properties || {})) {
      const budget = ['loopLimit','tokenLimit'].includes(key);
      const parent = budget ? config.budget : config.parameters;
      const label = el('label', `${key}${resource.schemas.configuration.required?.includes(key) ? ' *' : ''} · ${definition.description || definition.title || ''}`);
      const value = parent[key] ?? definition.default;
      let input;
      if (definition.enum) input = choices(definition.enum.map(v=>[JSON.stringify(v),String(v)]), value === undefined ? '' : JSON.stringify(value),()=>{});
      else {
        input = el(['object','array'].includes(definition.type) || definition.$ref || definition.anyOf ? 'textarea' : 'input');
        input.type = definition.type === 'boolean' ? 'checkbox' : ['integer','number'].includes(definition.type) ? 'number' : 'text';
        if (input.type === 'checkbox') input.checked = value ?? false;
        else input.value = value === undefined ? '' : input.tagName === 'TEXTAREA' ? JSON.stringify(value,null,2) : value;
      }
      input.dataset.field = key;
      fields.push(() => {
        if (input.type !== 'checkbox' && input.value === '') { delete parent[key]; return; }
        parent[key] = definition.enum || input.tagName === 'TEXTAREA' ? JSON.parse(input.value) : input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
      });
      label.append(input); $('node-fields').append(label);
    }
    for (const requirement of resource.requiredCapabilities) {
      const key = requirement.capabilityId, selected = config.capabilities[key];
      const label = el('label', `能力 ${key} · ${requirement.kind}`);
      const options = requirement.kind === 'block'
        ? resources.filter(r=>r.kind==='block').map(r=>[JSON.stringify({kind:'block',artifactRef:r.resourceId}),r.name])
        : response.data.flatMap(env=>env.connections.filter(c=>c.kind===requirement.kind).map(c=>[
          JSON.stringify({kind:requirement.kind,environmentId:env.environmentId,connectionId:c.connectionId}),env.name+' / '+c.connectionId+' / '+(c.model || 'API')]));
      const identity = selected ? requirement.kind === 'block' ? {kind:'block',artifactRef:selected.artifactRef} : {kind:requirement.kind,environmentId:selected.environmentId,connectionId:selected.connectionId} : null;
      const select = choices(options,identity ? JSON.stringify(identity) : '',()=>{});select.dataset.capability = key;label.append(select);
      let method, path;
      if (requirement.kind === 'api') {
        method = choices(['GET','POST','PUT','PATCH','DELETE'].map(v=>[v,v]),selected?.apiMethod || '',()=>{});
        path = el('input');path.placeholder = '/相对路径';path.value = selected?.apiPath || '';label.append(method,path);
      }
      caps.push(() => { if (!select.value) delete config.capabilities[key]; else {
        config.capabilities[key] = JSON.parse(select.value);
        if (method) Object.assign(config.capabilities[key],{apiMethod:method.value,apiPath:path.value});
      }}); $('node-capabilities').append(label);
    }
    $('node-form').onsubmit = async event => {
      event.preventDefault();$('node-errors').replaceChildren();
      try {
        fields.forEach(read=>read());caps.forEach(read=>read());
        const result = await window.agentPlatform.validateFlowNode({node,configuration:config,strictTokenLimit:content.budget?.strictTokenLimit ?? true});
        if (!result.ok) {
          $('node-errors').append(el('li',result.error.message + ' · ' + (result.error.fieldPath || []).join('.'))); return;
        }
        if (!result.data.valid) {
          for (const issue of result.data.issues) $('node-errors').append(el('li',issue.fieldPath.join('.')+' · '+issue.reason));return;
        }
        content.nodeConfigurations[node.nodeId] = clone(result.data.configuration);
        $('node-dialog').close();changed();render();
      } catch (error) { $('node-errors').append(el('li','参数 JSON 格式无效：'+error.message)); }
    };
    $('node-dialog').showModal();
  }
  $('node-close').onclick = () => $('node-dialog').close();
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
