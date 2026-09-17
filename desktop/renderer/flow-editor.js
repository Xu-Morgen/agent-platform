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
      {kind:n.kind === 'carry' ? 'carry' : 'node', nodeId:n.nodeId, path:[]}, n.kind === 'carry' ? n.nodeId + ' 携带值' : n.nodeId, outputRef(n)])];
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
    sequence($('flow-nodes'), content.flow, []);
    bindings($('flow-output-bindings'),content.output,content.outputContract,content.flow);
  }
  function outputRef(node) {
    return node.kind === 'if' ? node.outputContract : node.carry ? node.carry.contract : node.kind === 'carry' ? node.contract : resources.find(r=>r.resourceId===node.artifactRef)?.outputContract;
  }
  function allNodes(nodes = content.flow) {
    return nodes.flatMap(n=>[n,...(n.kind === 'if' ? [...allNodes(n.thenBranch.nodes),...allNodes(n.elseBranch.nodes)] : n.body ? [...(n.condition?.nodeId ? [n.condition] : []),...allNodes(n.body)] : [])]);
  }
  function newId() { let i=1;const ids=new Set(allNodes().map(n=>n.nodeId));while(ids.has('node_'+i))i++;return 'node_'+i; }
  function contractChoice(parent, label, value, update) {
    const item=el('label',label);item.append(choices(contracts(),value,v=>{update(v);changed();render()}));parent.append(item);
  }
  function bindingSection(parent, label, values, contract, scope) {
    const section=el('fieldset');section.append(el('legend',label));const body=el('div');body.dataset.bindingSection=label;
    bindings(body,values,contract,scope);section.append(body);parent.append(section);
  }
  function sequence(parent, nodes, inherited) {
    nodes.forEach((node,index)=>{
      const scope=[...inherited,...nodes.slice(0,index)];
      const resource=resources.find(r=>r.resourceId===node.artifactRef);
      const card=el('fieldset');card.dataset.nodeId=node.nodeId;card.dataset.kind=node.kind;
      card.append(el('legend',`${index+1}. ${resource?.name || node.kind} · ${node.nodeId}`));
      for(const [title,delta] of [['上移',-1],['下移',1]]) card.append(button(title,()=>{
        const next=index+delta;if(next<0||next>=nodes.length)return;
        [nodes[index],nodes[next]]=[nodes[next],nodes[index]];changed();render();
      }));
      card.append(button('删除节点',()=>{
        for(const child of allNodes([node]))delete content.nodeConfigurations[child.nodeId];
        nodes.splice(index,1);if(!allNodes().some(n=>n.kind==='package'))delete content.budget;changed();render();
      }));
      if(node.kind==='block'||node.kind==='package') {
        card.append(el('p',resource?.description));const ports=el('div');bindings(ports,node.inputs,resource?.inputContract,scope);card.append(ports);
        const detail=el('details');detail.append(el('summary','输入／输出契约'),el('pre',JSON.stringify(resource?.schemas,null,2)));card.append(detail);
        if(node.kind==='package')card.append(button('配置 '+node.nodeId,()=>configure(node,resource)),el('p',content.nodeConfigurations[node.nodeId]?'已配置，最终状态以拼图校验为准':'无效：尚未配置参数、预算及环境'));
      } else if(node.kind==='if') {
        const condition=el('label','条件块输出（严格 bool）');
        condition.append(choices(sourceOptions(scope),JSON.stringify(node.condition),v=>{if(v){node.condition=JSON.parse(v);changed()}}));card.append(condition);
        contractChoice(card,'分支共同出口契约',node.outputContract,v=>node.outputContract=v);
        for(const [key,title] of [['thenBranch','成立分支'],['elseBranch','否则分支']]){
          const branch=el('fieldset');branch.dataset.branch=key;branch.append(el('legend',title));
          sequence(branch,node[key].nodes,scope);
          bindingSection(branch,'分支出口',node[key].output,node.outputContract,[...scope,...node[key].nodes]);card.append(branch);
        }
      } else {
        const key=node.kind==='repeat'?'count':'maxIterations';const label=el('label',node.kind==='repeat'?'固定次数（允许 0）':'最大次数（必须大于 0）');
        const input=el('input');input.type='number';input.min=node.kind==='repeat'?'0':'1';input.step='1';input.value=node[key]??'';input.dataset.count=key;
        input.onchange=()=>{if(input.value==='')delete node[key];else node[key]=Number(input.value);changed()};label.append(input);card.append(label);
        contractChoice(card,'循环携带值契约',node.carry.contract,v=>node.carry.contract=v);
        bindingSection(card,'循环初始值',node.carry.initial,node.carry.contract,scope);
        const inner=[...scope,{kind:'carry',nodeId:node.nodeId,contract:node.carry.contract}];
        if(node.kind==='while'){
          const condition=el('label','前置条件块');condition.append(choices(resources.filter(r=>r.kind==='block').map(r=>[r.resourceId,r.name]),node.condition.artifactRef,v=>{node.condition.artifactRef=v;changed();render()}));card.append(condition);
          bindingSection(card,'条件块输入',node.condition.inputs,resources.find(r=>r.resourceId===node.condition.artifactRef)?.inputContract,inner);
        }
        const body=el('fieldset');body.dataset.branch='body';body.append(el('legend','循环体'));sequence(body,node.body,inner);card.append(body);
        bindingSection(card,'下轮携带值',node.carry.update,node.carry.contract,[...inner,...node.body]);
      }
      parent.append(card);
    });
    const toolbar=el('div');toolbar.className='insert-toolbar';
    const select=choices([...resources.filter(r=>r.kind!=='contract').map(r=>[r.resourceId,r.name]),...['if','repeat','while'].map(k=>[k,k])],'',()=>{});
    select.setAttribute('aria-label','插入模块或容器');toolbar.append(select,button('插入节点',()=>{if(select.value)add(resources.find(r=>r.resourceId===select.value)||{kind:select.value},nodes)}));parent.append(toolbar);
  }
  function add(resource,nodes=content.flow) {
    const nodeId=newId(),kind=resource.kind;
    if(kind==='package') {
      const defaults=resource.budgetDefaults;
      if(!content.budget)content.budget={...defaults,strictTokenLimit:true};
      else {content.budget.loopLimit+=defaults.loopLimit;content.budget.tokenLimit+=defaults.tokenLimit;}
    }
    let node={kind,nodeId,artifactRef:resource.resourceId,inputs:[]};
    if(kind==='if')node={kind,nodeId,condition:{kind:'input',path:[]},outputContract:'',thenBranch:{nodes:[],output:[]},elseBranch:{nodes:[],output:[]}};
    if(kind==='repeat'||kind==='while') {
      node={kind,nodeId,carry:{contract:'',initial:[],update:[]},body:[]};
      if(kind==='repeat')node.count=0;
      else {node.maxIterations=1;node.condition={kind:'block',nodeId:nodeId+'_condition',artifactRef:'',inputs:[]};}
    }
    nodes.push(node);changed();render();
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
    await refreshDrafts(); await refreshSaved(); render();
  }
  async function refreshDrafts() {
    const result = await window.agentPlatform.listDrafts(); if (!result.ok) return;
    $('draft-select').replaceChildren(new Option('新建草稿',''));
    for (const doc of result.data) $('draft-select').add(new Option(doc.content.name || doc.draftId,doc.draftId));
    $('draft-select').value = draftId;
  }
  let savedServices = [];
  async function refreshSaved(selected = $('service-select').value) {
    const result = await window.agentPlatform.listServices();
    if (!result.ok) { $('service-result').textContent=result.error.message;return; }
    savedServices=result.data;$('service-select').replaceChildren(new Option('新建服务',''));
    for(const service of savedServices)$('service-select').add(new Option(service.name+' · '+service.current.version,service.serviceId));
    $('service-select').value=selected;
    const current=savedServices.find(s=>s.serviceId===selected);
    $('service-current').textContent=current ? `${current.serviceId} · ${current.activeInstanceId} · 当前版本 ${current.current.version}` : '保存后生成稳定服务入口';
    $('service-history').replaceChildren();
    if(!current)return;
    const history=await window.agentPlatform.serviceHistory(selected);
    if(!history.ok){$('history-result').textContent=history.error.message;return;}
    for(const version of history.data){
      const row=el('li',`${version.version} · ${version.changeKind} · ${version.instanceId} `);
      row.dataset.instanceId=version.instanceId;
      row.append(button('查看只读拼图',()=>viewHistory(selected,version.instanceId)),button('复制为编辑草稿',async()=>{
        const copied=await window.agentPlatform.copyServiceVersion(selected,version.instanceId);
        if(!copied.ok){$('history-result').textContent=copied.error.message;return;}
        draftId=copied.data.draftId;content={...empty(),...clone(copied.data.content)};
        await refreshDrafts();changed();render();$('history-result').textContent='已复制为草稿 '+draftId;
      }));
      const activate=button(version.instanceId===current.activeInstanceId?'当前版本':'回退到此版本',async()=>{
        const result=await window.agentPlatform.activateService(selected,version.instanceId);
        if(!result.ok){$('history-result').textContent=result.error.message;return;}
        await refreshSaved(selected);await refreshServices();$('history-result').textContent='已回退 '+version.version+' · '+version.instanceId;
      });activate.disabled=version.instanceId===current.activeInstanceId;row.append(activate);$('service-history').append(row);
    }
  }
  async function viewHistory(serviceId,instanceId){
    const result=await window.agentPlatform.getServiceVersion(serviceId,instanceId);
    if(!result.ok){$('history-result').textContent=result.error.message;return;}
    const history=result.data, target=$('history-view');target.replaceChildren();
    target.append(el('h4','只读实例 '+instanceId),el('p',`版本 ${history.version.version} · ${history.version.changeKind} · 编译器 ${history.compilerVersion}`));
    function tree(nodes,parent){for(const node of nodes){
      const item=el('fieldset');item.append(el('legend',node.nodeId+' · '+node.kind));
      const own={...node};delete own.body;delete own.thenBranch;delete own.elseBranch;
      item.append(el('pre',JSON.stringify({node:own,configuration:history.flow.nodeConfigurations[node.nodeId]},null,2)));
      if(node.kind==='if')for(const key of ['thenBranch','elseBranch']){const branch=el('fieldset');branch.append(el('legend',key),el('pre',JSON.stringify(node[key].output,null,2)));tree(node[key].nodes,branch);item.append(branch);}
      if(node.body)tree(node.body,item);parent.append(item);
    }}
    tree(history.flow.flow,target);
    const detail=el('details');detail.append(el('summary','完整快照、契约、参数和预算'),el('pre',JSON.stringify(history,null,2)));target.append(detail);
  }
  $('service-refresh').onclick=()=>refreshSaved();
  $('service-select').onchange=async()=>{
    const id=$('service-select').value;
    if(id){const result=await window.agentPlatform.serviceSchema(id);if(!result.ok){$('service-result').textContent=result.error.message;return;}
      content=clone(result.data.flow);draftId='';changed();render();
    }
    await refreshSaved(id);
  };
  $('instance-save').onclick=async()=>{
    const control=$('instance-save');control.disabled=true;
    try{
      const snapshot=clone(content), id=$('service-select').value;
      const validation=await window.agentPlatform.validateFlow({content:snapshot});
      if(!validation.ok){$('service-result').textContent=validation.error.message;return;}
      issues(validation.data);if(!validation.data.valid)return;
      const body={name:snapshot.name,flow:snapshot};
      const result=id?await window.agentPlatform.saveServiceVersion(id,body):await window.agentPlatform.createService(body);
      if(!result.ok){$('service-result').textContent=result.error.message+' · '+(result.error.fieldPath||[]).join('.');return;}
      await refreshSaved(result.data.serviceId);await refreshServices();
      $('service-result').textContent=`已保存版本 ${result.data.current.version}（${result.data.current.changeKind}），立即生效`;
    }finally{control.disabled=false;}
  };
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
  $('draft-new').onclick = () => { $('service-select').value = ''; refreshSaved(''); draftId = ''; content = empty(); $('draft-select').value = ''; changed();render(); };
  $('draft-select').onchange = async () => {
    const id = $('draft-select').value; if (!id) return;
    const result = await window.agentPlatform.getDraft(id);
    if (!result.ok) { $('draft-result').textContent = result.error.message; return; }
    draftId = id; content = {...empty(),...clone(result.data.content)}; changed();render();
  };
  render();
  return {refresh, validate};
})();
