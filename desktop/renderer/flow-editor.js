/* 页面只编辑绑定，契约兼容性由后端权威预检决定。 */
const flowEditor = (() => {
  const $ = id => document.getElementById(id);
  const clone = value => structuredClone(value);
  let resources = [], draftId = '', revision = 0;
  const empty = () => ({name: '', inputContract: '', outputContract: '', flow: [], output: [], nodeConfigurations: {}, examples: []});
  let content = empty();
  const kindNames = {block:'通用块', package:'模型交互', if:'条件分支', repeat:'固定循环', while:'条件循环'};
  const controls = [
    {kind:'if', name:'条件分支', description:'根据布尔条件，选择「成立」或「否则」路径。'},
    {kind:'repeat', name:'固定循环', description:'按指定次数重复执行，携带每轮的处理结果。'},
    {kind:'while', name:'条件循环', description:'条件成立时重复执行；达到上限仍成立则报错停止。'},
  ];
  let insertion = null;
  function nodeName(node) { return resources.find(r=>r.resourceId===node.artifactRef)?.name || kindNames[node.kind] || node.nodeId; }
  function resolveSchema(value, root) { return value?.$ref ? root.$defs?.[value.$ref.split('/').pop()] || {} : value || {}; }
  function fieldSchema(ref, path) {
    const root = schema(ref);
    return path.reduce((value, key)=>resolveSchema(value,root).properties?.[key] || {}, root);
  }
  function typeName(value, root, depth=0) {
    if(depth>8)return '嵌套数据';
    value = resolveSchema(value, root);
    if (value.enum) return value.enum.map(v=>JSON.stringify(v)).join(' | ');
    if (value.anyOf) return value.anyOf.map(v=>typeName(v,root,depth+1)).join(' | ');
    if (value.type === 'array') return typeName(value.items,root,depth+1) + '[]';
    return value.type || '未声明类型';
  }
  function pathLabel(ref, path, whole='完整数据') {
    return (path.length ? path.join('.') : whole) + ' · ' + typeName(fieldSchema(ref,path),schema(ref));
  }
  function portPreview(parent, ref) {
    parent.replaceChildren(); parent.classList.add('port-preview');
    if (!ref) { parent.append(el('p','选择数据结构后显示字段及类型。')); return; }
    const root=schema(ref), value=resolveSchema(root,root);
    if (!Object.keys(root).length) { parent.append(el('p','数据结构不可用，请重新加载对应资源。')); return; }
    const fields=Object.entries(value.properties || {});
    if (!fields.length) { parent.append(el('code',typeName(value,root))); return; }
    for (const [key,definition] of fields) {
      const row=el('div');row.className='port-field';
      row.append(el('code',key),el('span',typeName(definition,root)),el('small',value.required?.includes(key)?'必填':'可选'));
      const description=definition.description || resolveSchema(definition,root).description;
      if(description)row.append(el('p',description));
      parent.append(row);
    }
  }
  function renderLibrary(target, query, choose) {
    target.replaceChildren();
    const groups=[['处理模块',resources.filter(r=>r.kind!=='contract')],['流程控制',controls]];
    let count=0;
    for(const [title,items] of groups) {
      const matches=items.filter(r=>(r.name+' '+(r.description||'')+' '+kindNames[r.kind]).toLowerCase().includes(query.toLowerCase().trim()));
      if(!matches.length)continue;
      target.append(el('h4',title));
      for(const resource of matches) {
        const item=button('',()=>choose(resource));item.className='module-tile';item.dataset.kind=resource.kind;
        item.append(el('span',kindNames[resource.kind]),el('strong',resource.name),el('small',resource.description || '添加到流程中配置输入与输出'),el('b','＋'));
        target.append(item);count++;
      }
    }
    if(!count)target.append(el('p','没有匹配的拼图块。请换个关键词或加载本地资源。'));
    if(!query && !resources.some(r=>r.kind!=='contract'))target.append(el('p','还没有处理模块，请在下方加载本地通用块或业务包。'));
  }
  function openInsert(nodes,index,label) {
    insertion={nodes,index};$('insert-context').textContent=label;
    $('insert-search').value=''; renderInsertOptions();$('insert-dialog').showModal();$('insert-search').focus();
  }
  function renderInsertOptions() {
    renderLibrary($('insert-options'),$('insert-search').value,resource=>{
      const {nodes,index}=insertion;$('insert-dialog').close();add(resource,nodes,index);
    });
  }
  function insertPoint(parent,nodes,index) {
    const row=el('div');row.className='flow-connector';
    const label=index===0?'在此路径的开头添加拼图块':'在 '+nodeName(nodes[index-1])+' 之后添加拼图块';
    const control=button('＋',()=>openInsert(nodes,index,label));control.title=label;control.setAttribute('aria-label',label);
    row.append(control);parent.append(row);
  }
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
  function sourceValue(source) {
    return JSON.stringify({kind:source.kind,...(source.nodeId ? {nodeId:source.nodeId} : {}),path:source.path || []});
  }
  function sourceOptions(nodes) {
    const ports = [[{kind:'input', path:[]}, '服务输入', content.inputContract], ...nodes.map(n => [
      {kind:n.kind === 'carry' ? 'carry' : 'node', nodeId:n.nodeId, path:[]}, n.kind === 'carry' ? n.nodeId + ' · 本轮携带值' : nodeName(n)+' ['+n.nodeId+'] 的输出', outputRef(n)])];
    return ports.flatMap(([source, title, ref]) => paths(schema(ref)).map(path => [sourceValue({...source, path}), title + ' / ' + pathLabel(ref,path)]));
  }
  function bindings(target, values, contract, nodes, destination='当前节点输入') {
    target.replaceChildren();
    if(!values.length) { const hint=el('p','尚未指定数据来源。添加映射，将服务输入或前面节点的输出传入这里。');hint.className='flow-hint';target.append(hint); }
    values.forEach((binding, i) => {
      const row = el('div'); row.className = 'binding-row';
      const destinations = paths(schema(contract)).map(path => [JSON.stringify(path), pathLabel(contract,path)]);
      const dest = choices(destinations, JSON.stringify(binding.target), value => { if (value) { binding.target = JSON.parse(value); changed(); } });
      dest.setAttribute('aria-label', destination+'字段');
      const options = sourceOptions(nodes); options.push(['constant', '固定值（JSON）']);
      const source = choices(options, binding.source.kind === 'constant' ? 'constant' : sourceValue(binding.source), value => {
        if (!value) return;
        binding.source = value === 'constant' ? {kind:'constant', value:null} : JSON.parse(value); changed(); render();
      }); source.setAttribute('aria-label', '数据来源');
      const from=el('label','从哪里取值');from.append(source);
      const to=el('label','传给哪里 · '+destination);to.append(dest);
      const arrow=el('span','→');arrow.className='binding-arrow';arrow.setAttribute('aria-hidden','true');
      row.append(from,arrow,to);
      if (binding.source.kind === 'constant') {
        const label=el('div','固定值 · JSON');const input = el('input'); input.value = JSON.stringify(binding.source.value); input.setAttribute('aria-label', '常量 JSON');
        input.onchange = () => { try { binding.source.value = JSON.parse(input.value); input.setCustomValidity(''); changed(); } catch { input.setCustomValidity('请输入合法 JSON'); input.reportValidity(); } };label.append(input);from.append(label);
      }
      const remove=button('×', () => { values.splice(i,1); changed(); render(); });remove.className='remove-binding';remove.setAttribute('aria-label','删除第 '+(i+1)+' 条映射');
      row.append(remove); target.append(row);
    });
    target.append(button('＋ 添加数据映射', () => { values.push({target:[],source:{kind:'input',path:[]}}); changed(); render(); }));
  }
  function issues(result) {
    $('flow-issues').replaceChildren();
    document.querySelectorAll('.flow-node.has-issue').forEach(card=>card.classList.remove('has-issue'));
    for (const issue of result.issues || []) {
      const item = el('li', `${issue.nodeId || '服务'} · ${(issue.fieldPath || []).join('.')} · ${issue.reason}`);
      item.dataset.nodeId = issue.nodeId || '';
      const card=Array.from(document.querySelectorAll('.flow-node')).find(card=>card.dataset.nodeId===issue.nodeId || card.dataset.conditionId===issue.nodeId);
      if(card){card.classList.add('has-issue');item.append(button('定位节点',()=>{card.scrollIntoView({behavior:'smooth',block:'center'});card.querySelector('details').open=true;card.focus({preventScroll:true});}));}
      $('flow-issues').append(item);
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
  function render(focusNode) {
    const openDetails=new Set(Array.from(document.querySelectorAll('#flow-nodes details[open]')).map(item=>item.dataset.detailKey));
    $('service-name').value = content.name;
    $('flow-example').value = content.examples.length ? JSON.stringify(content.examples[0].input,null,2) : '';
    for (const [id,key] of [['flow-input','inputContract'],['flow-output','outputContract']]) {
      const select = choices(contracts(), content[key], value => { content[key] = value; changed(); render(); });
      select.id = id; $(id).replaceWith(select);
    }
    $('global-budget').hidden = !content.budget;
    if (content.budget) {
      $('global-loop').value = content.budget.loopLimit;
      $('global-token').value = content.budget.tokenLimit;
    }
    $('flow-nodes').replaceChildren();
    sequence($('flow-nodes'), content.flow, []);
    bindings($('flow-output-bindings'),content.output,content.outputContract,content.flow,'服务返回结果');
    portPreview($('flow-input-preview'),content.inputContract);portPreview($('flow-output-preview'),content.outputContract);
    for(const detail of document.querySelectorAll('#flow-nodes details')) {
      detail.dataset.detailKey ||= detail.closest('.flow-node').dataset.nodeId+':'+detail.firstElementChild.textContent;
      detail.open=openDetails.has(detail.dataset.detailKey);
    }
    for(const card of document.querySelectorAll('.flow-node')) {
      if(card.dataset.nodeId===focusNode)card.querySelector('.node-details').open=true;
      if(card.dataset.nodeId===focusNode){card.scrollIntoView({behavior:'smooth',block:'center'});card.focus({preventScroll:true});}
    }
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
    bindings(body,values,contract,scope,label.startsWith('输入 ·')?'当前节点输入':label);section.append(body);parent.append(section);
  }
  function sequence(parent, nodes, inherited) {
    parent.classList.add('flow-sequence');
    if(!nodes.length){const hint=el('p','点击 ＋ 添加这条路径的第一步');hint.className='empty-sequence';parent.append(hint);}
    nodes.forEach((node,index)=>{
      insertPoint(parent,nodes,index);
      const scope=[...inherited,...nodes.slice(0,index)];
      const resource=resources.find(r=>r.resourceId===node.artifactRef);
      const card=el('article');card.className='flow-node';card.tabIndex=-1;card.dataset.nodeId=node.nodeId;card.dataset.kind=node.kind;
      if(node.kind==='while')card.dataset.conditionId=node.condition.nodeId;
      const header=el('div');header.className='node-header';
      const icon=el('span',({block:'▦',package:'✦',if:'⑂',repeat:'↻',while:'↻'})[node.kind]);icon.className='node-icon';
      const title=el('div');title.className='node-title';title.append(el('small',kindNames[node.kind]+' · '+node.nodeId),el('h4',nodeName(node)));
      const actions=el('div');actions.className='node-actions';
      for(const [text,delta] of [['↑',-1],['↓',1]]) {
        const move=button(text,()=>{const next=index+delta;[nodes[index],nodes[next]]=[nodes[next],nodes[index]];changed();render(node.nodeId);});
        move.disabled=index+delta<0||index+delta>=nodes.length;move.setAttribute('aria-label',(delta<0?'上移':'下移')+' '+nodeName(node));actions.append(move);
      }
      const remove=button('×',()=>{
        for(const child of allNodes([node]))delete content.nodeConfigurations[child.nodeId];
        nodes.splice(index,1);if(!allNodes().some(n=>n.kind==='package'))delete content.budget;changed();render();
      });remove.setAttribute('aria-label','删除 '+nodeName(node));actions.append(remove);header.append(icon,title,actions);card.append(header);
      const description=el('p',resource ? resource.description || '按输入数据执行处理，将结果提供给后续节点。' : controls.find(r=>r.kind===node.kind)?.description || '资源不可用，请重新加载。');description.className='node-description';card.append(description);
      const summary=el('div');summary.className='node-port-summary';
      let inputText=node.inputs?.length ? node.inputs.map(({source})=>{
        const origin=scope.find(n=>n.nodeId===source.nodeId);
        const name=source.kind==='input'?'服务输入':source.kind==='constant'?'固定值':source.kind==='carry'?'本轮携带值':origin?nodeName(origin)+' ['+source.nodeId+']':source.nodeId+'（不可用）';
        return name+(source.path?.length?' / '+source.path.join('.'):'');
      }).join('、'):'待指定来源';
      if(node.kind==='if')inputText='条件 → 成立 / 否则';
      if(node.body)inputText='初始值 → 每轮处理 → 更新携带值';
      summary.append(el('span','输入 · '+inputText),el('span','输出 · '+(contracts().find(([id])=>id===outputRef(node))?.[1] || '待选择数据结构')));card.append(summary);
      const detail=el('details');detail.className='node-details';detail.append(el('summary','配置输入、输出与参数'));card.append(detail);
      if(node.kind==='block'||node.kind==='package') {
        bindingSection(detail,'输入 · 这个节点需要什么',node.inputs,resource?.inputContract,scope);
        const inputPreview=el('div');portPreview(inputPreview,resource?.inputContract);detail.append(inputPreview);
        detail.append(el('h5','输出 · 执行后可供后续节点使用'));const outputPreview=el('div');portPreview(outputPreview,resource?.outputContract);detail.append(outputPreview);
        const raw=el('details');raw.className='raw-schema';raw.append(el('summary','查看完整契约 JSON'),el('pre',JSON.stringify(resource?.schemas,null,2)));detail.append(raw);
        if(node.kind==='package'||resource?.apiRequired){
          const configured=!!content.nodeConfigurations[node.nodeId];const status=el('p',configured?'参数已配置 · 兼容性以校验结果为准':'待配置 · '+(node.kind==='package'?'模型连接、参数与预算':'API 连接与请求路径'));status.className='configuration-status';card.append(status);
          const configButton=button('配置'+(node.kind==='package'?'模型与参数':' API 连接'),()=>configure(node,resource));configButton.disabled=!resource;detail.append(configButton);
        }
      } else if(node.kind==='if') {
        const condition=el('label','判断依据 · 选择前面条件块输出的布尔值（true / false）');
        condition.append(choices(sourceOptions(scope),sourceValue(node.condition),v=>{if(v){node.condition=JSON.parse(v);changed();render();}}));detail.append(condition);
        contractChoice(detail,'两条分支汇合后的输出结构',node.outputContract,v=>node.outputContract=v);
        const branches=el('div');branches.className='flow-branches';
        for(const [key,title] of [['thenBranch','成立 · true'],['elseBranch','否则 · false']]){
          const branch=el('div');branch.className='flow-branch';branch.dataset.branch=key;branch.append(el('h5',title));
          const branchNodes=el('div');sequence(branchNodes,node[key].nodes,scope);branch.append(branchNodes);
          const output=el('details');output.className='branch-output';output.dataset.detailKey=node.nodeId+':'+key;output.append(el('summary','本分支返回什么'));
          bindingSection(output,'分支出口',node[key].output,node.outputContract,[...scope,...node[key].nodes]);branch.append(output);branches.append(branch);
        }
        card.append(branches,el('div','⑂ 分支汇合 · 统一输出给下一步'));card.lastChild.className='flow-merge';
      } else {
        const key=node.kind==='repeat'?'count':'maxIterations';const label=el('label',node.kind==='repeat'?'重复次数 · 0 表示跳过':'最大执行次数 · 防止无限循环');
        const input=el('input');input.type='number';input.min=node.kind==='repeat'?'0':'1';input.step='1';input.value=node[key]??'';input.dataset.count=key;
        input.onchange=()=>{if(input.value==='')delete node[key];else node[key]=Number(input.value);changed();render();};label.append(input);detail.append(label);
        contractChoice(detail,'轮次之间传递的数据结构',node.carry.contract,v=>node.carry.contract=v);
        detail.append(el('p','初始值用于第一轮；循环体读取「本轮携带值」，每轮结束用「下轮携带值」更新。循环结束后输出最后的携带值。'));
        bindingSection(detail,'循环初始值',node.carry.initial,node.carry.contract,scope);
        const inner=[...scope,{kind:'carry',nodeId:node.nodeId,contract:node.carry.contract}];
        if(node.kind==='while'){
          const condition=el('label','每轮执行前判断 · 输出必须为布尔值');condition.append(choices(resources.filter(r=>r.kind==='block').map(r=>[r.resourceId,r.name]),node.condition.artifactRef,v=>{node.condition.artifactRef=v;delete content.nodeConfigurations[node.condition.nodeId];changed();render();}));detail.append(condition);
          const conditionResource=resources.find(r=>r.resourceId===node.condition.artifactRef);
          if(conditionResource?.apiRequired)detail.append(button('配置条件块 API',()=>configure(node.condition,conditionResource)));
          bindingSection(detail,'条件块输入',node.condition.inputs,conditionResource?.inputContract,inner);
        }
        const body=el('div');body.className='loop-body';body.dataset.branch='body';body.append(el('h5','↻ 循环体 · '+(node.kind==='repeat'?'执行 '+(node.count??'—')+' 次':'条件成立时执行，最多 '+node.maxIterations+' 次')));
        const bodyNodes=el('div');sequence(bodyNodes,node.body,inner);body.append(bodyNodes);card.append(body);
        const update=el('details');update.className='loop-update';update.append(el('summary','↻ 设置下轮携带值'));
        bindingSection(update,'下轮携带值',node.carry.update,node.carry.contract,[...inner,...node.body]);card.append(update);
      }
      parent.append(card);
    });
    insertPoint(parent,nodes,nodes.length);
  }
  function add(resource,nodes=content.flow,index=nodes.length) {
    const nodeId=newId(),kind=resource.kind;
    if(kind==='package') {
      const defaults=resource.budgetDefaults;
      if(!content.budget)content.budget={...defaults};
      else {content.budget.loopLimit+=defaults.loopLimit;content.budget.tokenLimit+=defaults.tokenLimit;}
    }
    let node={kind,nodeId,artifactRef:resource.resourceId,inputs:[]};
    if(kind==='if')node={kind,nodeId,condition:{kind:'input',path:[]},outputContract:'',thenBranch:{nodes:[],output:[]},elseBranch:{nodes:[],output:[]}};
    if(kind==='repeat'||kind==='while') {
      node={kind,nodeId,carry:{contract:'',initial:[],update:[]},body:[]};
      if(kind==='repeat')node.count=0;
      else {node.maxIterations=1;node.condition={kind:'block',nodeId:nodeId+'_condition',artifactRef:'',inputs:[]};}
    }
    nodes.splice(index,0,node);changed();render(nodeId);
  }
  for (const [id, key] of [['global-loop','loopLimit'],['global-token','tokenLimit']]) {
    $(id).onchange = () => { content.budget[key] = Number($(id).value); changed(); };
  }
  async function configure(node, resource) {
    const isPackage = node.kind === 'package';
    const connectionKind = isPackage ? 'model' : 'api';
    const config = clone(content.nodeConfigurations[node.nodeId] || (isPackage ? {parameters:{},budget:resource.budgetDefaults,model:null,maxOutputTokens:512} : {api:null}));
    const response = await window.agentPlatform.listEnvironments();
    if (!response.ok) { $('service-result').textContent = response.error.message; return; }
    const fields = [];
    $('node-fields').replaceChildren(); $('node-capabilities').replaceChildren(); $('node-errors').replaceChildren();
    $('node-title').textContent = resource.name + ' · ' + node.nodeId;
    if (isPackage) config.budget ||= clone(resource.budgetDefaults);
    const parameterSchema = resource.schemas.configuration;
    const groups = isPackage ? [
      {title:'业务参数', parent:config.parameters, schema:parameterSchema},
      {title:'节点累计预算', parent:config.budget, schema:{properties:{
        loopLimit:{type:'integer',minimum:1,title:'最大调用次数'},
        tokenLimit:{type:'integer',minimum:1,title:'最大累计 token'},
      }}},
      {title:'模型调用', parent:config, schema:{properties:{
        maxOutputTokens:{type:'integer',minimum:1,default:512,title:'单次输出 token 上限'},
      }}},
    ] : [];
    for (const {title,parent,schema} of groups) {
      $('node-fields').append(el('strong',title));
      for (const [key, definition] of Object.entries(schema.properties || {})) {
        const label = el('label', `${key}${schema.required?.includes(key) ? ' *' : ''} · ${definition.description || definition.title || ''}`);
        const value = parent[key] ?? definition.default;
        let input;
        if (definition.enum) input = choices(definition.enum.map(v=>[JSON.stringify(v),String(v)]), value === undefined ? '' : JSON.stringify(value),()=>{});
        else {
          input = el(['object','array'].includes(definition.type) || definition.$ref || definition.anyOf ? 'textarea' : 'input');
          input.type = definition.type === 'boolean' ? 'checkbox' : ['integer','number'].includes(definition.type) ? 'number' : 'text';
          if (input.type === 'checkbox') input.checked = value ?? false;
          else input.value = value === undefined ? '' : input.tagName === 'TEXTAREA' ? JSON.stringify(value,null,2) : value;
        }
        if (definition.minimum !== undefined) input.min = definition.minimum;
        input.dataset.field = key;
        fields.push(() => {
          if (input.type !== 'checkbox' && input.value === '') { delete parent[key]; return; }
          parent[key] = definition.enum || input.tagName === 'TEXTAREA' ? JSON.parse(input.value) : input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
        });
        label.append(input); $('node-fields').append(label);
      }
    }
    const label = el('label', isPackage ? '模型连接' : 'API 连接');
    const options = response.data.flatMap(env=>env.connections.filter(c=>c.kind===connectionKind).map(c=>[
      JSON.stringify({environmentId:env.environmentId,connectionId:c.connectionId}),env.name+' / '+c.connectionId+' / '+(isPackage ? c.model : c.baseUrl)]));
    const binding = config[connectionKind];
    const select = choices(options, binding ? JSON.stringify({environmentId:binding.environmentId,connectionId:binding.connectionId}) : '',()=>{});
    select.dataset.field = connectionKind;label.append(select);$('node-capabilities').append(label);
    let apiPath;
    if (!isPackage) {
      const pathLabel = el('label', '请求路径 *');
      apiPath = el('input');apiPath.type = 'text';apiPath.required = true;
      apiPath.dataset.field = 'apiPath';apiPath.placeholder = '例如 /lookup';
      apiPath.value = binding?.path || '';
      pathLabel.append(apiPath);$('node-capabilities').append(pathLabel,
        el('p', '相对于所选连接的 Base URL；查询参数由块输入生成，不填入路径。'));
    }
    $('node-form').onsubmit = async event => {
      event.preventDefault();$('node-errors').replaceChildren();
      try {
        fields.forEach(read=>read());
        config[connectionKind] = select.value ? JSON.parse(select.value) : null;
        if (!isPackage && config.api) config.api.path = apiPath.value;
        const result = await window.agentPlatform.validateFlowNode({node,configuration:config});
        if (!result.ok) {
          const branch = isPackage ? 'NodeConfiguration' : 'BlockConfiguration';
          const issues = (result.error.issues || []).filter(issue => issue.fieldPath.includes(branch));
          if (issues.length) {
            for (const issue of issues) $('node-errors').append(el('li',
              issue.fieldPath.slice(issue.fieldPath.indexOf(branch) + 1).join('.') + ' · ' + issue.reason));
            return;
          }
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
  $('module-search').oninput=()=>renderLibrary($('module-library'),$('module-search').value,resource=>add(resource));
  $('insert-search').oninput=renderInsertOptions;
  $('insert-close').onclick=()=>$('insert-dialog').close();
  $('node-close').onclick = () => $('node-dialog').close();
  async function refresh() {
    const result = await window.agentPlatform.listResources();
    if (!result.ok) { $('load-result').textContent = result.error.message; return; }
    resources = result.data; renderLibrary($('module-library'),$('module-search').value,resource=>add(resource));
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
    if(!$('flow-example').reportValidity())return;
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
  $('flow-example').onchange = () => {
    try {
      content.examples = $('flow-example').value.trim() ? [{name:'页面输入样例',input:JSON.parse($('flow-example').value)}] : [];
      $('flow-example').setCustomValidity('');changed();
    } catch { $('flow-example').setCustomValidity('输入样例 JSON 格式无效');$('flow-example').reportValidity(); }
  };
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
  renderLibrary($('module-library'),'',resource=>add(resource));
  render();
  return {refresh, validate};
})();
