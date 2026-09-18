/* 页面只编辑绑定，契约兼容性由后端权威预检决定。 */
const flowEditor = (() => {
  const $ = id => document.getElementById(id);
  const clone = value => structuredClone(value);
  let resources = [], draftId = '', revision = 0;
  const empty = () => ({name: '', inputContract: '', outputContract: '', flow: [], nodeConfigurations: {}, examples: [], retryLimit: 3});
  let content = empty();
  const kindNames = {block:'通用块', package:'业务包', contract:'契约', if:'条件分支', repeat:'固定循环', while:'条件循环'};
  const controls = [
    {kind:'if', name:'条件分支', description:'根据布尔条件，选择「成立」或「否则」路径。'},
    {kind:'repeat', name:'固定循环', description:'按指定次数重复执行，携带每轮的处理结果。'},
    {kind:'while', name:'条件循环', description:'条件成立时重复执行；达到上限仍成立则报错停止。'},
  ];
  let insertion = null;
  function nodeName(node) { return resources.find(r=>r.resourceId===node.artifactRef)?.name || kindNames[node.kind] || node.nodeId; }
  function resolveSchema(value, root) { return value?.$ref ? root.$defs?.[value.$ref.split('/').pop()] || {} : value || {}; }
  function typeName(value, root, depth=0) {
    if(depth>8)return '嵌套数据';
    value = resolveSchema(value, root);
    if (value.enum) return value.enum.map(v=>JSON.stringify(v)).join(' | ');
    if (value.anyOf) return value.anyOf.map(v=>typeName(v,root,depth+1)).join(' | ');
    if (value.type === 'array') return typeName(value.items,root,depth+1) + '[]';
    return value.type || '未声明类型';
  }
  function portPreview(parent, ref) {
    parent.replaceChildren(); parent.classList.add('port-preview');
    if (!ref) { parent.append(el('p','请选择契约；加载业务包、通用块或契约文件后，这里会列出可选契约。')); return; }
    const root=schema(ref), value=resolveSchema(root,root);
    if (!Object.keys(root).length) { parent.append(el('p','契约不可用，请重新加载对应业务包、通用块或契约文件。')); return; }
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
    const groups=[['业务包',resources.filter(r=>r.kind==='package')],['通用块',resources.filter(r=>r.kind==='block')],['流程控制',controls]];
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
    if(target.id === 'module-library') {
      const section=el('details');section.className='resource-import';
      section.append(el('summary','契约'));
      section.append(el('p','业务包和通用块自带输入、输出契约，也可以单独加载契约文件。在流程的输入、输出处选择，契约无需添加为处理步骤。'));
      const available=contracts();
      if(!available.length)section.append(el('p','暂无契约，请先加载业务包、通用块或契约文件。'));
      for(const [ref,name] of available) {
        const item=el('details');item.append(el('summary',name));
        const preview=el('div');portPreview(preview,ref);item.append(preview);section.append(item);
      }
      target.append(section);
    }
    if(!count)target.append(el('p','没有匹配项。请换个关键词或加载业务包、通用块。'));
    if(!query && !resources.some(r=>r.kind!=='contract'))target.append(el('p','还没有业务包或通用块，请在下方加载。'));
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
    const label=index===0?'在此路径的开头添加业务包或通用块':'在 '+nodeName(nodes[index-1])+' 之后添加业务包或通用块';
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
    return resources.flatMap(r => r.kind === 'contract' ? [[r.resourceId, '契约 · ' + r.name, r.schemas.value]]
      : [['input', '输入'], ['output', '输出']].map(([key, name]) => [r[key + 'Contract'], kindNames[r.kind] + ' · ' + r.name + ' · ' + name + '契约', r.schemas[key]]));
  }
  function schema(ref) { return contracts().find(([id]) => id === ref)?.[2] || {}; }
  function sourceValue(source) {
    return JSON.stringify({kind:source.kind,...(source.nodeId ? {nodeId:source.nodeId} : {})});
  }
  function sourceOptions(nodes) {
    const ports = [[{kind:'input'}, '服务输入', content.inputContract], ...nodes.map(n => [
      {kind:n.kind === 'carry' ? 'carry' : 'node', nodeId:n.nodeId}, n.kind === 'carry' ? n.nodeId + ' · 本轮携带值' : nodeName(n)+' ['+n.nodeId+'] 的输出', outputRef(n)])];
    return ports.map(([source, title, ref]) => [sourceValue(source), title + ' · 完整数据 · ' + typeName(schema(ref),schema(ref))]);
  }
  function bindings(target, values, contract, nodes, destination='当前节点输入') {
    target.replaceChildren();
    const binding = values[0];
    const options = sourceOptions(nodes);options.push(['constant','固定完整数据（JSON）']);
    const selected = binding ? binding.source.kind === 'constant' ? 'constant' : sourceValue(binding.source) : '';
    const label = el('label','数据来源 · 完整传给'+destination);
    const select = choices(options, selected, value=>{
      values.splice(0,values.length,...(value ? [{source:value === 'constant' ? {kind:'constant',value:null} : JSON.parse(value)}] : []));
      changed();render();
    });
    select.setAttribute('aria-label',destination+'数据来源');label.append(select);target.append(label);
    const hint=el('p','完整数据必须符合接收方契约。字段名称、类型或结构不兼容时会报错，请添加通用块完成转换。');hint.className='flow-hint';target.append(hint);
    if (binding?.source.kind === 'constant') {
      const label=el('label','完整数据 · JSON');const input=el('textarea');input.value=JSON.stringify(binding.source.value,null,2);
      input.onchange=()=>{try {binding.source.value=JSON.parse(input.value);input.setCustomValidity('');changed();} catch {input.setCustomValidity('请输入合法 JSON');input.reportValidity();}};
      label.append(input);target.append(label);
    }
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
    if (inputEvents.defer('flow-render',()=>render(focusNode),$('flow-nodes'))) return;
    const openDetails=new Set(Array.from(document.querySelectorAll('#flow-nodes details[open]')).map(item=>item.dataset.detailKey));
    inputEvents.setValue($('service-name'), content.name);
    inputEvents.setValue($('flow-retry-limit'), content.retryLimit);
    inputEvents.setValue($('flow-example'), content.examples.length ? JSON.stringify(content.examples[0].input,null,2) : '');
    for (const [id,key] of [['flow-input','inputContract'],['flow-output','outputContract']]) {
      const select = choices(contracts(), content[key], value => { content[key] = value; changed(); render(); });
      select.id = id; $(id).replaceWith(select);
    }
    $('global-budget').hidden = !content.budget;
    if (content.budget) {
      inputEvents.setValue($('global-loop'), content.budget.loopLimit);
      inputEvents.setValue($('global-token'), content.budget.tokenLimit);
    }
    $('flow-nodes').replaceChildren();
    sequence($('flow-nodes'), content.flow, []);
    $('flow-node-count').textContent = allNodes().length + ' 个节点';
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
  function sequence(parent, nodes, inherited, incoming='服务完整输入') {
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
      const previousInput=index ? nodeName(nodes[index-1])+' 的完整输出' : incoming;
      let inputText=previousInput;
      if(node.kind==='if')inputText='条件 → 成立 / 否则';
      if(node.body)inputText='初始值 → 每轮处理 → 更新携带值';
      summary.append(el('span','输入 · '+inputText),el('span','输出 · '+(contracts().find(([id])=>id===outputRef(node))?.[1] || '待选择契约')));card.append(summary);
      const detail=el('details');detail.className='node-details';detail.append(el('summary',node.kind==='block'||node.kind==='package'?'查看固定契约与配置参数':'配置条件或循环'));card.append(detail);
      if(node.kind==='block'||node.kind==='package') {
        detail.append(el('h5','输入契约 · 自动接收'+previousInput));
        const inputPreview=el('div');portPreview(inputPreview,resource?.inputContract);detail.append(inputPreview);
        detail.append(el('p','输入输出类型由'+kindNames[node.kind]+'固定声明。运行时输出不符合契约时，按服务设置重新调用本步骤；下一步不会执行。预算不足或取消时立即停止。'));
        detail.append(el('h5','输出契约 · 执行后可供后续步骤使用'));const outputPreview=el('div');portPreview(outputPreview,resource?.outputContract);detail.append(outputPreview);
        const raw=el('details');raw.className='raw-schema';raw.append(el('summary','查看完整契约 JSON'),el('pre',JSON.stringify(resource?.schemas,null,2)));detail.append(raw);
        if(node.kind==='package'||resource?.apiRequired){
          const configured=!!content.nodeConfigurations[node.nodeId];const status=el('p',configured?'参数已配置 · 兼容性以校验结果为准':'待配置 · '+(node.kind==='package'?'模型连接、参数与预算':'API 连接与请求路径'));status.className='configuration-status';card.append(status);
          const configButton=button('配置'+(node.kind==='package'?'模型与参数':' API 连接'),()=>configure(node,resource));configButton.disabled=!resource;detail.append(configButton);
        }
      } else if(node.kind==='if') {
        const condition=el('label','判断依据 · 选择前面通用块输出的布尔值（true / false）');
        condition.append(choices(sourceOptions(scope),sourceValue(node.condition),v=>{if(v){node.condition=JSON.parse(v);changed();render();}}));detail.append(condition);
        contractChoice(detail,'契约 · 分支输出契约',node.outputContract,v=>node.outputContract=v);
        const branches=el('div');branches.className='flow-branches';
        for(const [key,title] of [['thenBranch','成立 · true'],['elseBranch','否则 · false']]){
          const branch=el('div');branch.className='flow-branch';branch.dataset.branch=key;branch.append(el('h5',title));
          const branchNodes=el('div');sequence(branchNodes,node[key].nodes,scope,previousInput);branch.append(branchNodes);
          const output=el('details');output.className='branch-output';output.dataset.detailKey=node.nodeId+':'+key;output.append(el('summary','本分支返回什么'));
          bindingSection(output,'分支出口',node[key].output,node.outputContract,[...scope,...node[key].nodes]);branch.append(output);branches.append(branch);
        }
        card.append(branches,el('div','⑂ 分支汇合 · 统一输出给下一步'));card.lastChild.className='flow-merge';
      } else {
        const key=node.kind==='repeat'?'count':'maxIterations';const label=el('label',node.kind==='repeat'?'重复次数 · 0 表示跳过':'最大执行次数 · 防止无限循环');
        const input=el('input');input.type='number';input.min=node.kind==='repeat'?'0':'1';input.step='1';input.value=node[key]??'';input.dataset.count=key;
        input.onchange=()=>{if(input.value==='')delete node[key];else node[key]=Number(input.value);changed();render();};label.append(input);detail.append(label);
        contractChoice(detail,'契约 · 循环传递契约',node.carry.contract,v=>node.carry.contract=v);
        detail.append(el('p','初始值用于第一轮；循环体读取「本轮携带值」，每轮结束用「下轮携带值」更新。循环结束后输出最后的携带值。'));
        bindingSection(detail,'循环初始值',node.carry.initial,node.carry.contract,scope);
        const inner=[...scope,{kind:'carry',nodeId:node.nodeId,contract:node.carry.contract}];
        if(node.kind==='while'){
          const condition=el('label','每轮执行前判断 · 输出必须为布尔值');condition.append(choices(resources.filter(r=>r.kind==='block').map(r=>[r.resourceId,r.name]),node.condition.artifactRef,v=>{node.condition.artifactRef=v;delete content.nodeConfigurations[node.condition.nodeId];changed();render();}));detail.append(condition);
          const conditionResource=resources.find(r=>r.resourceId===node.condition.artifactRef);
          if(conditionResource?.apiRequired)detail.append(button('配置通用块 API',()=>configure(node.condition,conditionResource)));
          detail.append(el('p','条件通用块自动接收本轮完整携带值。'));
          const preview=el('div');portPreview(preview,conditionResource?.inputContract);detail.append(preview);
        }
        const body=el('div');body.className='loop-body';body.dataset.branch='body';body.append(el('h5','↻ 循环体 · '+(node.kind==='repeat'?'执行 '+(node.count??'—')+' 次':'条件成立时执行，最多 '+node.maxIterations+' 次')));
        const bodyNodes=el('div');sequence(bodyNodes,node.body,inner,'本轮完整携带值');body.append(bodyNodes);card.append(body);
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
    let node={kind,nodeId,artifactRef:resource.resourceId};
    if(kind==='if')node={kind,nodeId,condition:{kind:'input'},outputContract:'',thenBranch:{nodes:[],output:[]},elseBranch:{nodes:[],output:[]}};
    if(kind==='repeat'||kind==='while') {
      node={kind,nodeId,carry:{contract:'',initial:[],update:[]},body:[]};
      if(kind==='repeat')node.count=0;
      else {node.maxIterations=1;node.condition={kind:'block',nodeId:nodeId+'_condition',artifactRef:''};}
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
    $('node-title').textContent = kindNames[node.kind] + ' · ' + resource.name + ' · ' + node.nodeId;
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
  inputEvents.onInput($('module-search'),()=>renderLibrary($('module-library'),$('module-search').value,resource=>add(resource)));
  inputEvents.onInput($('insert-search'),renderInsertOptions);
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
    savedServices=result.data;$('service-select').replaceChildren(new Option('保存为新服务',''));
    for(const service of savedServices)$('service-select').add(new Option(service.name+' · '+service.current.version,service.serviceId));
    $('service-select').value=selected;
    const current=savedServices.find(s=>s.serviceId===selected);
    $('service-current').textContent=current ? `当前版本 ${current.current.version} · 保存将为此服务生成新版本 · ${current.serviceId}` : '当前流程将保存为新服务，成功后生成稳定调用入口。';
    $('service-history').replaceChildren();
    $('history-view').replaceChildren();$('history-result').textContent='';
    if(!current){const hint=el('li','选择已保存的服务后，在这里查看版本记录。');hint.className='field-hint';$('service-history').append(hint);return;}
    const history=await window.agentPlatform.serviceHistory(selected);
    if(!history.ok){$('history-result').textContent=history.error.message;return;}
    for(const version of history.data){
      const row=el('li');row.className='version-card';
      const isActive=version.instanceId===current.activeInstanceId;
      row.dataset.instanceId=version.instanceId;row.dataset.active=String(isActive);
      const changeNames={initial:'首次创建',minor:'次版本更新',major:'主版本更新',breaking:'整体更新'};
      const heading=el('div');heading.className='version-heading';heading.append(el('strong','版本 '+version.version),el('span',changeNames[version.changeKind] || version.changeKind));
      if(isActive){const badge=el('span','当前使用');badge.className='current-version';heading.append(badge);}
      row.append(heading,el('code',version.instanceId));
      const actions=el('div');actions.className='version-actions';
      actions.append(button('查看快照',()=>viewHistory(selected,version.instanceId)),button('复制为草稿',async()=>{
        const copied=await window.agentPlatform.copyServiceVersion(selected,version.instanceId);
        if(!copied.ok){$('history-result').textContent=copied.error.message;return;}
        draftId=copied.data.draftId;content={...empty(),...clone(copied.data.content)};
        await refreshDrafts();changed();render();$('history-result').textContent='已复制为草稿 '+draftId;
      }));
      const activate=button(version.instanceId===current.activeInstanceId?'当前版本':'回退到此版本',async()=>{
        const result=await window.agentPlatform.activateService(selected,version.instanceId);
        if(!result.ok){$('history-result').textContent=result.error.message;return;}
        await refreshSaved(selected);await refreshServices();$('history-result').textContent='已回退 '+version.version+' · '+version.instanceId;
      });activate.disabled=isActive;actions.append(activate);row.append(actions);$('service-history').append(row);
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
    if(!$('flow-example').reportValidity() || !$('flow-retry-limit').reportValidity())return;
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
  function renderLoadKind() {
    const kind = $('load-kind').value;
    const hints = {
      block: ['samples/blocks/minimal.py', '通用块：选择一个 Python 文件。加载后可添加处理步骤，并选择它的输入、输出契约。'],
      package: ['samples/packages/minimal', '业务包：选择包含 package.json 的目录。加载后配置模型连接和参数，并选择它的输入、输出契约。'],
      contract: ['samples/contracts/minimal.py', '契约：选择 Python 文件，并填写其中的契约类名。例如 minimal.py 中的 Text，规定输入为 {"text":"内容"}。契约不执行处理步骤。'],
    };
    $('load-path').placeholder = hints[kind][0];
    $('load-hint').textContent = hints[kind][1];
    $('load-symbol-label').hidden = kind !== 'contract';
    $('load-symbol').required = kind === 'contract';
    $('load-symbol').disabled = kind !== 'contract';
  }
  $('load-kind').onchange = renderLoadKind;
  renderLoadKind();
  function loadStatus(state, message) {
    $('load-result').dataset.state = state;
    $('load-result').textContent = message;
  }
  function loadError(error) {
    const fields = {path:'本地路径',symbol:'契约类名',entry:'通用块函数',imports:'代码依赖',contractRefs:'契约',prompt:'Prompt',version:'版本'};
    const location = path => (path || []).map(key=>fields[key] || key).join(' → ');
    const details = (error.issues || []).map(issue=>location(issue.fieldPath)+'：'+issue.reason);
    if (!details.length && error.fieldPath?.length) details.push('检查位置：'+location(error.fieldPath));
    return [error.message, ...details].join('\n');
  }
  let loadingResource = false;
  async function loadLocalResource() {
    if (loadingResource) return;
    const body = {kind:$('load-kind').value,path:$('load-path').value.trim()};
    if (!body.path) { loadStatus('pending','尚未选择路径，请选择或填写本地路径。'); return; }
    if (body.kind === 'contract') {
      body.symbol = $('load-symbol').value.trim();
      if (!body.symbol) {
        loadStatus('pending','已选择契约文件，尚未加载。请填写文件中的契约类名（例如 Text），再点击“加载资源”。\n路径：'+body.path);
        $('load-symbol').focus();return;
      }
    }
    loadingResource = true;
    const controls = ['load-kind','load-path','load-symbol','load-browse','load-submit'].map($);
    const disabled = controls.map(control=>control.disabled);
    controls.forEach(control=>control.disabled=true);
    loadStatus('loading','正在读取并校验'+kindNames[body.kind]+'…\n路径：'+body.path);
    try {
      const response = await window.agentPlatform.loadResource(body);
      if (!response.ok) {
        loadStatus('error','加载失败：'+loadError(response.error)+'\n路径：'+body.path);return;
      }
      const listed = await window.agentPlatform.listResources();
      if (!listed.ok) {
        loadStatus('error','已录入 '+response.data.name+'，但列表刷新失败：'+loadError(listed.error));return;
      }
      resources = listed.data;
      $('module-search').value = '';
      renderLibrary($('module-library'),'',resource=>add(resource));render();
      loadStatus('success','已录入'+kindNames[body.kind]+'：'+response.data.name+'\n路径：'+body.path+'\n'+
        (body.kind === 'contract' ? '现在可在输入契约、输出契约中选择。' : '现在可在左侧点击添加到流程。'));
    } catch {
      loadStatus('error','未能确认加载结果：桌面与后端通信失败，请重试加载（相同资源不会重复录入）。\n路径：'+body.path);
    } finally {
      controls.forEach((control,index)=>control.disabled=disabled[index]);
      loadingResource = false;
    }
  }
  $('load-browse').onclick = async () => {
    const button = $('load-browse'), kind = $('load-kind').value;
    button.disabled = true;
    $('load-kind').disabled = true;
    try {
      const response = await window.agentPlatform.selectResourcePath(kind);
      if (!response.ok) { loadStatus('error',loadError(response.error)); return; }
      if (!response.data.path) {
        loadStatus('pending','已取消选择，保留原路径，未发起加载。');return;
      }
      $('load-path').value = response.data.path;
      await loadLocalResource();
    } catch {
      loadStatus('error','无法打开路径选择窗口，请重启桌面应用后重试，或手动填写路径。');
    } finally { button.disabled = false; $('load-kind').disabled = false; }
  };
  $('load-form').onsubmit = async event => {
    event.preventDefault();await loadLocalResource();
  };
  for (const id of ['load-path','load-symbol']) $(id).oninput = () => loadStatus('pending','内容已修改，尚未加载。填写完成后点击“加载资源”。');
  $('load-kind').onchange = () => { renderLoadKind();loadStatus('pending','已切换为'+kindNames[$('load-kind').value]+'，请选择对应路径后加载。'); };
  $('flow-retry-limit').onchange = () => { content.retryLimit = Number($('flow-retry-limit').value); changed(); };
  inputEvents.onInput($('service-name'), () => { content.name = $('service-name').value; changed(); });
  inputEvents.onInput($('flow-example'), () => {
    try {
      content.examples = $('flow-example').value.trim() ? [{name:'页面输入样例',input:JSON.parse($('flow-example').value)}] : [];
      $('flow-example').setCustomValidity('');changed();
    } catch { $('flow-example').setCustomValidity('输入样例 JSON 格式无效'); }
  });
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
