/* 页面只编辑绑定，契约兼容性由后端权威预检决定。 */
const flowEditor = (() => {
  const $ = id => document.getElementById(id);
  const clone = value => structuredClone(value);
  let resources = [], draftId = '', revision = 0;
  let contractGroups = [], serviceComponents = [], libraryTab = 'all', insertTab = 'all';
  let contractSelection = null, contractTab = 'all';
  const empty = () => ({name: '', inputContract: '', outputContract: '', flow: [], nodeConfigurations: {}, examples: [], retryLimit: 3});
  let content = empty();
  const kindNames = {block:'通用块', package:'业务包', contract:'契约', service:'服务', if:'条件分支', repeat:'固定循环', while:'条件循环', foreach:'数组遍历', switch:'枚举分支'};
  const controls = [
    {kind:'foreach', name:'数组遍历', description:'按数组实际长度顺序执行，汇总每项输出；超限在首项前停止。'},
    {kind:'switch', name:'枚举分支', description:'Python 路由块返回有限字符串枚举，每次只执行一个出口。'},
    {kind:'if', name:'条件分支', description:'根据布尔条件，选择「成立」或「否则」路径。'},
    {kind:'repeat', name:'固定循环', description:'按指定次数重复执行，携带每轮的处理结果。'},
    {kind:'while', name:'条件循环', description:'条件成立时重复执行；达到上限仍成立则报错停止。'},
  ];
  let insertion = null;
  function component(node) { return serviceComponents.find(r=>r.instanceId===node.instanceId&&r.serviceId===node.serviceId); }
  function nodeName(node) { return (node.kind==='service' ? component(node)?.name : resources.find(r=>r.resourceId===node.artifactRef)?.name) || kindNames[node.kind] || node.nodeId; }
  function tabs(target, items, current, change) {
    target.replaceChildren();
    for(const [value,label] of items){const control=button(label,()=>change(value));control.setAttribute('role','tab');control.setAttribute('aria-selected',String(value===current));target.append(control);}
  }
  const resourceTabs=[['all','全部'],['package','包'],['block','块'],['contract','契约'],['service','服务'],['control','控制']];
  function renderTabs() {
    tabs($('module-tabs'),resourceTabs,libraryTab,value=>{libraryTab=value;renderTabs();renderLibrary($('module-library'),$('module-search').value,r=>add(r));});
    tabs($('insert-tabs'),resourceTabs.filter(([key])=>key!=='contract'),insertTab,value=>{insertTab=value;renderTabs();renderInsertOptions();});
  }
  function contractGroup(ref){return contractGroups.find(group=>group.contractId===ref||group.aliases.includes(ref));}
  function contractLabel(ref){
    const root=schema(ref),value=resolveSchema(root,root),fields=Object.entries(value.properties||{});
    return fields.length ? fields.slice(0,4).map(([key,definition])=>key+': '+typeName(definition,root)).join(' · ')+(fields.length>4?' …':'') : typeName(value,root);
  }
  function contractPicker(value, change) {
    const control=button(value?contractLabel(value):'选择契约 · 查看内容',()=>{
      contractSelection={value,change};contractTab='all';$('contract-search').value='';renderContractOptions();$('contract-dialog').showModal();$('contract-search').focus();
    });control.className='contract-picker';control.dataset.contractId=value||'';return control;
  }
  function contractCard(group, select) {
    const card=el('article');card.className='contract-card';card.dataset.contractId=group.contractId;
    const origins=new Map();
    for(const source of group.sources){
      if(!origins.has(source.resourceId))origins.set(source.resourceId,{...source,roles:[]});
      const role=source.direction==='primary'?'主数据输入':source.direction==='output'?'输出结果':'独立契约';
      if(!origins.get(source.resourceId).roles.includes(role))origins.get(source.resourceId).roles.push(role);
    }
    const sources=el('section');sources.className='contract-origins';sources.setAttribute('aria-label','契约来源');
    sources.append(el('h4',origins.size>1?`契约来源 · ${origins.size} 个资源共用`:'契约来源'));
    for(const source of origins.values()){
      const item=el('div');item.className='contract-origin';
      item.append(el('strong',source.name));
      const version=source.kind==='contract'?'内容版本 '+source.version.slice(0,12):'v'+source.version;
      item.append(el('p',`${kindNames[source.kind]} · ${version} · ${source.roles.join(' / ')}${source.archived?' · 已归档':''}`));
      const resource=resources.find(resource=>resource.resourceId===source.resourceId);
      if(resource?.description)item.append(el('p',resource.description));
      sources.append(item);
    }
    card.append(sources,el('h4','数据结构'));
    const preview=el('div');portPreview(preview,group.contractId);card.append(preview);
    if(group.runtimeValidation)card.append(el('p','校验身份独立 · 未合并为共享契约'));
    const raw=el('details');raw.append(el('summary','完整结构与约束'),el('pre',JSON.stringify(group.schema,null,2)));card.append(raw);
    if(select){const selected=contractGroup(contractSelection.value)?.contractId===group.contractId;card.append(button(selected?'使用此契约（当前）':'使用此契约',()=>{select(group.contractId);}));}
    return card;
  }
  function filteredContracts(query, tab, current='') {
    const visible=new Set(latestResources().map(resource=>resource.resourceId));
    return contractGroups.map(group=>({...group,sources:group.sources.filter(source=>visible.has(source.resourceId))})).filter(group=>group.sources.length &&
      (tab==='all'||group.sources.some(source=>source.kind===tab)) &&
      (JSON.stringify(group.schema)+' '+group.sources.map(s=>s.name+' '+s.version).join(' ')).toLowerCase().includes(query.trim().toLowerCase()));
  }
  function renderContractOptions(){
    tabs($('contract-tabs'),resourceTabs.filter(([key])=>['all','package','block','contract'].includes(key)),contractTab,value=>{contractTab=value;renderContractOptions();});
    const target=$('contract-options');target.replaceChildren();
    for(const group of filteredContracts($('contract-search').value,contractTab,contractSelection.value))target.append(contractCard(group,ref=>{const choose=contractSelection.change;$('contract-dialog').close();choose(ref);}));
    if(!target.childElementCount)target.append(el('p','没有匹配的契约。'));
  }
  function resolveSchema(value, root) { return value?.$ref ? root.$defs?.[value.$ref.split('/').pop()] || {} : value || {}; }
  function typeName(value, root, depth=0) {
    if(depth>8)return '嵌套数据';
    value = resolveSchema(value, root);
    if (Object.hasOwn(value,'const'))return JSON.stringify(value.const);
    if (value.enum) return value.enum.map(v=>JSON.stringify(v)).join(' | ');
    if (value.anyOf) return value.anyOf.map(v=>typeName(v,root,depth+1)).join(' | ');
    if (value.type === 'array') return value.prefixItems ? '['+value.prefixItems.map(item=>typeName(item,root,depth+1)).join(', ')+']' : typeName(value.items,root,depth+1) + '[]';
    return value.type || '未声明类型';
  }
  function portPreview(parent, ref) {
    parent.replaceChildren(); parent.classList.add('port-preview');
    if (!ref) { parent.append(el('p','请选择契约；加载业务包、通用块或契约文件后，这里会列出可选契约。')); return; }
    const root=schema(ref), value=resolveSchema(root,root);
    if (!Object.keys(root).length) { parent.append(el('p','契约不可用，请重新加载对应业务包、通用块或契约文件。')); return; }
    if(value.description)parent.append(el('p',value.description));
    function fields(target,current,depth=0,seen=[]) {
      const resolved=resolveSchema(current,root);
      if(depth>6 || current.$ref&&seen.includes(current.$ref)){target.append(el('p','更深层结构请查看完整契约 JSON。'));return;}
      const nextSeen=current.$ref?[...seen,current.$ref]:seen;
      for(const [key,definition] of Object.entries(resolved.properties||{})) {
        const row=el('div');row.className='port-field';
        row.append(el('code',key),el('span',typeName(definition,root)),el('small',resolved.required?.includes(key)?'必填':'可选'));
        const description=definition.description || resolveSchema(definition,root).description;
        if(description)row.append(el('p',description));target.append(row);
        const nested=resolveSchema(definition,root);
        if(nested.properties || nested.items || nested.prefixItems || nested.anyOf || nested.oneOf){
          const detail=el('details');detail.className='nested-contract';detail.append(el('summary','展开 '+key+' 的字段与说明'));
          fields(detail,definition,depth+1,nextSeen);target.append(detail);
        }
      }
      const variants=resolved.anyOf||resolved.oneOf||resolved.prefixItems||(resolved.items?[resolved.items]:[]);
      variants.forEach((variant,index)=>{const entry=resolveSchema(variant,root);target.append(el('strong',entry.title||'结构 '+(index+1)),el('p',variant.description||entry.description||typeName(variant,root)));fields(target,variant,depth+1,nextSeen);});
      if(!resolved.properties&&!variants.length)target.append(el('code',typeName(resolved,root)));
    }
    fields(parent,value);
  }

  function resourceSeries(resource) {
    // resourceId 固定为 kind:声明标识:version:digest；同名资源不一定属于同一系列。
    return resource.resourceId.split(':').slice(0,2).join(':');
  }
  function latestResources(includeArchived=false) {
    const latest=new Map();
    for(const resource of resources.filter(resource=>resource.kind==='package'||resource.kind==='block')){
      const key=resourceSeries(resource),previous=latest.get(key);
      if(!previous||compareVersions(resource.version,previous.version)>0)latest.set(key,resource);
    }
    return resources.filter(resource=>(resource.kind==='contract'||latest.get(resourceSeries(resource))?.resourceId===resource.resourceId)&&
      (includeArchived||!resource.archived));
  }
  function compareVersions(left, right) {
    const parse=value=>{const split=value.indexOf('-');return [
      (split<0 ? value : value.slice(0,split)).split('.').map(BigInt),
      split<0 ? null : value.slice(split+1).split('.'),
    ];};
    const [a,ap]=parse(left),[b,bp]=parse(right);
    for(let i=0;i<3;i++)if(a[i]!==b[i])return a[i]>b[i]?1:-1;
    if(ap===null||bp===null)return ap===bp?0:ap===null?1:-1;
    for(let i=0;i<Math.max(ap.length,bp.length);i++) {
      if(ap[i]===bp[i])continue;
      if(ap[i]===undefined||bp[i]===undefined)return ap[i]===undefined?-1:1;
      const an=/^\d+$/.test(ap[i]),bn=/^\d+$/.test(bp[i]);
      if(an&&bn){const x=BigInt(ap[i]),y=BigInt(bp[i]);if(x!==y)return x>y?1:-1;continue;}
      if(an!==bn)return an?-1:1;
      return ap[i]>bp[i]?1:-1;
    }
    return 0;
  }
  let adviceModels = [], adviceRequest = 0;
  async function refreshAdviceModels() {
    const result=await window.agentPlatform.listEnvironments();
    adviceModels=result.ok?result.data.flatMap(env=>env.connections.filter(c=>c.kind==='model'&&c.model).map(c=>({environmentId:env.environmentId,connectionId:c.connectionId,label:env.name+' / '+c.connectionId+' · '+c.model}))):[];
    renderLibrary($('module-library'),$('module-search').value,r=>add(r));
    if($('insert-dialog').open)renderInsertOptions();
    render();
  }
  function adviceButton(resource) {
    if(!resource || !['block','package'].includes(resource.kind) || !adviceModels.length)return null;
    const control=button('用 AI 解释',()=>openAdvice(resource));control.className='resource-advice-button';
    control.setAttribute('aria-label','用 AI 解释 '+resource.name);return control;
  }
  function openAdvice(resource) {
    const dialog=$('advice-dialog'),output=$('advice-output'),generate=$('advice-generate');
    const session=++adviceRequest;
    $('advice-title').textContent='用 AI 解释 · '+resource.name;
    output.replaceChildren(el('p','选择模型后生成解释，将结合点击生成时的当前草稿。'));
    const select=$('advice-model');select.replaceChildren();
    adviceModels.forEach((model,index)=>select.add(new Option(model.label,String(index))));
    generate.disabled=!adviceModels.length;generate.textContent='生成解释';
    generate.onclick=async()=>{
      const model=adviceModels[Number(select.value)];if(!model)return;
      const snapshot=clone(content),snapshotRevision=revision;
      generate.disabled=true;select.disabled=true;generate.textContent='正在解释…';
      output.replaceChildren(el('p','正在分析资源用途、当前草稿与可放置的位置…'));
      try {
        const response=await window.agentPlatform.explainResource({resourceId:resource.resourceId,model:{environmentId:model.environmentId,connectionId:model.connectionId},content:snapshot});
        if(session!==adviceRequest)return;
        if(!response.ok){output.replaceChildren(el('p',response.error.message));return;}
        const {advice,usage}=response.data;
        output.replaceChildren(el('h4','这个'+kindNames[resource.kind]+'有什么用'),el('p',advice.purpose));
        output.append(el('h4','当前草稿适用性 · '+({suitable:'适合',conditional:'有前提',unsuitable:'不适合',unknown:'信息不足'})[advice.suitability]),el('p',advice.assessment));
        output.append(el('h4','建议放置位置'));
        if(!advice.placements.length)output.append(el('p','暂无可推荐的位置。'));
        const findNode=(nodes,id)=>{for(const n of nodes){if(n.nodeId===id)return n;const found=findNode([...(n.body||[]),...(n.thenBranch?.nodes||[]),...(n.elseBranch?.nodes||[]),...(n.condition?[n.condition]:[]),...(n.router?[n.router]:[]),...(n.cases||[]).flatMap(c=>c.nodes)],id);if(found)return found;}};
        for(const place of advice.placements){
          const anchor=place.nodeId?findNode(snapshot.flow,place.nodeId):null;
          const label=place.position==='start'?'顶层流程开头':(anchor?nodeName(anchor):place.nodeId)+'（'+place.nodeId+'）'+(place.position==='before'?'之前':'之后');
          output.append(el('strong',label),el('p',place.reason));
        }
        if(advice.requirements.length){output.append(el('h4','使用前需要满足'));const list=el('ul');advice.requirements.forEach(text=>list.append(el('li',text)));output.append(list);}
        output.append(el('p',usage.quality==='exact'?`本次用量：输入 ${usage.inputTokens} / 输出 ${usage.outputTokens} token`:'供应商未提供准确用量'));
        if(snapshotRevision!==revision)output.append(el('p','草稿已变化，以上解释基于生成时的快照，请重新生成。'));
      } catch {if(session===adviceRequest)output.replaceChildren(el('p','解释请求失败，请检查模型连接后重试。'));}
      finally {if(session===adviceRequest){generate.disabled=false;select.disabled=false;generate.textContent='重新生成';}}
    };
    select.disabled=false;dialog.showModal();
  }
  $('advice-close').onclick=()=>$('advice-dialog').close();
  $('advice-dialog').addEventListener('close',()=>{adviceRequest++;});

  function renderLibrary(target, query, choose) {
    target.replaceChildren();
    const activeTab=target.id==='module-library'?libraryTab:insertTab;
    const visible=latestResources();
    const reusable=new Map();
    for(const item of serviceComponents)if(!reusable.has(item.serviceId)||item.current)reusable.set(item.serviceId,item);
    const groups=[['业务包',visible.filter(r=>r.kind==='package'),'package'],['通用块',visible.filter(r=>r.kind==='block'),'block'],['服务',[...reusable.values()].filter(r=>r.serviceId!==$('service-select').value).map(r=>({...r,kind:'service'})),'service'],['流程控制',controls,'control']];
    let count=0;
    for(const [title,items,category] of groups) {
      if(activeTab!=='all'&&activeTab!==category)continue;
      const matches=items.filter(r=>(r.name+' '+(r.description||'')+' '+(r.version||'')+' '+kindNames[r.kind]).toLowerCase().includes(query.toLowerCase().trim()));
      if(title!=='流程控制'&&title!=='服务')matches.sort((a,b)=>a.name.localeCompare(b.name,'zh-CN') ||
        resourceSeries(a).localeCompare(resourceSeries(b)) || compareVersions(b.version,a.version));
      if(!matches.length)continue;
      target.append(el('h4',title));
      for(const resource of matches) {
        const item=button('',()=>choose(resource));item.className='module-tile';item.dataset.kind=resource.kind;
        item.append(el('span',kindNames[resource.kind]),el('strong',resource.name+(resource.version ? ' · v'+resource.version : '')));
        if(resource.kind==='service') {
          item.append(el('small',resource.current?'当前版本 · 添加后可选择历史版本':'可复用历史版本 · 添加后可切换版本'),el('small',resource.instanceId));
        } else if(resource.version) {
          const version=el('span','最新已导入');version.className='resource-version';version.dataset.latest='true';
          item.append(version,el('small','ID：'+resource.resourceId.split(':')[1]));
          item.dataset.resourceId=resource.resourceId;
        }
        item.append(el('small',resource.description || '添加到流程中配置输入与输出'),el('b','＋'));
        if(resource.kind==='block'||resource.kind==='package')referenceSummary(item,resource);
        const wrapper=el('div');wrapper.className='resource-choice';wrapper.append(item);
        const explain=adviceButton(resource);if(explain)wrapper.append(explain);
        target.append(wrapper);count++;
      }
    }
    if(target.id === 'module-library') {
      const section=el('details');section.className='resource-import';
      section.append(el('summary','契约'));
      section.append(el('p','业务包和通用块自带输入、输出契约，也可以单独加载契约文件。在流程的输入、输出处选择，契约无需添加为处理步骤。'));
      const available=(activeTab==='all'||activeTab==='contract')?filteredContracts(query,'all'):[];
      if(!available.length)section.append(el('p','暂无契约，请先加载业务包、通用块或契约文件。'));
      for(const group of available) {
        section.append(contractCard(group));count++;
      }
      if(activeTab==='all'||activeTab==='contract'){section.open=activeTab==='contract';target.append(section);}
      const management=el('details');management.className='resource-import';
      management.append(el('summary','管理资源 · 归档 / 恢复'),el('p','包和块只展示同一 ID 的最新已导入版本，旧版本不展示。归档最新版不会显示旧版。独立契约仍可手动归档；已有流程、实例和任务引用保持不变。'));
      for(const resource of latestResources(true)) {
        const row=el('p');
        row.append(el('span',`${kindNames[resource.kind]} · ${resource.name} · ${resource.kind === 'contract' ? resource.version.slice(0,12) : 'v'+resource.version}${resource.archived ? ' · 已归档' : ''} `));
        const toggle=button(resource.archived ? '恢复' : '归档',async()=>{
          toggle.disabled=true;
          try {
            const result=await window.agentPlatform.archiveResource(resource.resourceId,{archived:!resource.archived});
            if(!result.ok){loadStatus('error',result.error.message);return;}
            resources=resources.map(r=>r.resourceId===resource.resourceId ? result.data : r);
            await refreshChoices();
            renderLibrary($('module-library'),$('module-search').value,r=>add(r));render();
            loadStatus('success',`${resource.name} 已${result.data.archived ? '归档' : '恢复'}。`);
          } catch { loadStatus('error','资源状态更新失败，请刷新后重试。'); }
          finally { toggle.disabled=false; }
        });
        row.append(toggle);management.append(row);
      }
      target.append(management);
    }
    if(!count)target.append(el('p','没有匹配项。请换个关键词或加载业务包、通用块。'));
    if(!query && !visible.some(r=>r.kind!=='contract'))target.append(el('p','暂无可选的最新业务包或通用块，请加载资源或恢复已归档的最新版。'));
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
    return [...contractGroups.map(group=>[group.contractId,group.schema.title||'共享契约',group.schema]),...resources.flatMap(r => r.kind === 'contract' ? [[r.resourceId, '契约 · ' + r.name + ' · ' + r.version.slice(0,12) + (r.archived ? ' · 已归档' : ''), r.schemas.value]]
      : [['primary', '主数据输入'], ['output', '输出']].map(([key, name]) => [r[key + 'Contract'], kindNames[r.kind] + ' · ' + r.name + ' · v' + r.version + (r.archived ? ' · 已归档' : '') + ' · ' + name + '契约', r.schemas[key]]).filter(([ref])=>ref)),
      ...serviceComponents.flatMap(r=>[[r.inputContract,r.name+' 输入',r.schemas.input],[r.outputContract,r.name+' 输出',r.schemas.output]])];
  }
  function schema(ref, seen = new Set()) {
    if(!ref || seen.has(ref))return {};
    seen.add(ref);
    if(ref.startsWith('collection:')){
      const item=schema(ref.slice(11),seen),{$defs,...value}=item;
      return {type:'object',properties:{items:{type:'array',items:value}},required:['items'],additionalProperties:false,...($defs?{$defs}:{})};
    }
    if(ref.startsWith('item:')){
      const node=allNodes().find(n=>n.nodeId===ref.slice(5));
      if(!node)return {};
      const root=sourceSchema(node.source,seen);
      const array=arrayFields(root).find(([path])=>JSON.stringify(path)===JSON.stringify(node.arrayPath));
      return array?{...array[1].items,...(root.$defs?{$defs:root.$defs}:{})}:{};
    }
    return contracts().find(([id]) => id === ref)?.[2] || {};
  }
  function sourceSchema(source, seen=new Set()) {
    if(source?.kind==='input')return schema(content.inputContract,seen);
    const node=allNodes().find(n=>n.nodeId===source?.nodeId);
    return schema(source?.kind==='item'?'item:'+source.nodeId:outputRef(node||{}),seen);
  }
  function arrayFields(root) {
    const fields=[];
    function visit(raw,path,seen){
      if(raw.$ref && seen.has(raw.$ref))return;
      const next=new Set(seen);if(raw.$ref)next.add(raw.$ref);
      const value=resolveSchema(raw,root);
      if(value.type==='array'&&value.items){fields.push([path,value]);return;}
      if(value.type==='object')for(const key of value.required||[])if(value.properties?.[key])visit(value.properties[key],[...path,key],next);
    }
    visit(root,[],new Set());return fields;
  }
  function sourceValue(source) {
    return JSON.stringify({kind:source.kind,...(source.nodeId ? {nodeId:source.nodeId} : {})});
  }
  function sourceOptions(nodes) {
    const ports = [[{kind:'input'}, '服务输入', content.inputContract], ...nodes.map(n => [
      {kind:['carry','item'].includes(n.kind) ? n.kind : 'node', nodeId:n.nodeId}, ['carry','item'].includes(n.kind) ? n.nodeId + (n.kind==='item'?' · 当前元素':' · 本轮携带值') : nodeName(n)+' ['+n.nodeId+'] 的输出', outputRef(n)])];
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
      const select = contractPicker(content[key], value => { content[key] = value; changed(); render(); });
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
    return node.kind==='service' ? component(node)?.outputContract : ['if','switch'].includes(node.kind) ? node.outputContract : node.kind==='foreach' ? 'collection:'+node.itemOutputContract : node.kind==='item' ? 'item:'+node.nodeId : node.carry ? node.carry.contract : node.kind === 'carry' ? node.contract : resources.find(r=>r.resourceId===node.artifactRef)?.outputContract;
  }
  function allNodes(nodes = content.flow) {
    return nodes.flatMap(n=>[n,...(n.condition?.nodeId?[n.condition]:[]),...(n.router?.nodeId?[n.router]:[]),
      ...allNodes(n.thenBranch?.nodes||[]),...allNodes(n.elseBranch?.nodes||[]),
      ...(n.cases||[]).flatMap(c=>allNodes(c.nodes)),...allNodes(n.body||[])]);
  }
  function newId() { let i=1;const ids=new Set(allNodes().map(n=>n.nodeId));while(ids.has('node_'+i))i++;return 'node_'+i; }
  function contractChoice(parent, label, value, update) {
    const item=el('label',label);item.append(contractPicker(value,v=>{update(v);changed();render()}));parent.append(item);
  }
  function bindingSection(parent, label, values, contract, scope) {
    const section=el('fieldset');section.append(el('legend',label));const body=el('div');body.dataset.bindingSection=label;
    bindings(body,values,contract,scope,label.startsWith('输入 ·')?'当前节点输入':label);section.append(body);parent.append(section);
  }
  function referenceDeclaration(resource) {
    const root=resource?.schemas?.input || {}, entry=resolveSchema(root,root);
    const declaration=resolveSchema(entry.properties?.references,root);
    return {root,entry,declaration,slots:declaration.prefixItems || []};
  }
  function referenceSummary(parent, resource) {
    const {root,entry,declaration,slots}=referenceDeclaration(resource);
    const summary=el('span');summary.className='reference-summary';
    if(!entry.properties?.references){summary.append(el('small','参考输入 · 声明不可用'));parent.append(summary);return;}
    summary.append(el('strong',slots.length?`参考输入 · ${slots.length} 项（按位置顺序）`:'参考输入 · 0 项，无需参考'));
    if(slots.length){
      const explanation=declaration.description || entry.description;
      if(explanation)summary.append(el('small',explanation));
      slots.forEach((slot,index)=>{
        const resolved=resolveSchema(slot,root),item=el('span');item.className='reference-slot';
        item.append(el('code',`references[${index}]`),el('small','类型 · '+(resolved.title || typeName(slot,root))));
        item.append(el('small',slot.description?'作用 · '+slot.description:'作用 · 资源未声明此位置的用途'));
        if(!slot.description&&resolved.description)item.append(el('small','结构说明 · '+resolved.description));
        summary.append(item);
      });
    }
    parent.append(summary);
  }
  function referenceEditor(parent, node, resource, scope, automatic) {
    const {root,slots}=referenceDeclaration(resource);
    parent.append(el('p','主数据自动传递；简单模式参考：'+automatic+'。资源声明 '+slots.length+' 个参考位置。'));
    const panel=el('details');panel.dataset.detailKey=node.nodeId+':references';panel.open=node.references!=null;
    panel.append(el('summary','高级参考设置'));
    panel.append(choices([['simple','简单模式 · 自动来源'],['advanced','高级模式 · 替换参考列表']],node.references==null?'simple':'advanced',value=>{
      if(value==='simple')delete node.references;
      else node.references=[];
      changed();render();
    }));
    if(node.references!=null){
      if(!slots.length)panel.append(el('p','此资源声明零参考：保存为空列表。'));
      slots.forEach((slot,index)=>{
        const label=el('label',`references[${index}] · ${slot.description || typeName(slot,root)}`);
        label.append(choices(sourceOptions(scope),node.references[index]?sourceValue(node.references[index]):'',value=>{
          node.references[index]=value?JSON.parse(value):{kind:'node',nodeId:''};changed();render();
        }));panel.append(label);
      });
      if(node.references.length>slots.length)panel.append(button('清除多余参考',()=>{node.references.splice(slots.length);changed();render();}));
      const keys=node.references.map(ref=>ref&&sourceValue(ref));
      if(new Set(keys).size!==keys.length)panel.append(el('p','同一来源不能重复绑定，请修改后保存。'));
    }
    parent.append(panel);
  }
  function switchValues(node) {
    const root=resources.find(r=>r.resourceId===node.router?.artifactRef)?.schemas.output||{};
    const out=resolveSchema(root,root),values=out.enum||(out.const!==undefined?[out.const]:[]);
    return out.type==='string'&&values.length&&values.every(value=>typeof value==='string')?values:[];
  }
  function switchOverview(parent,node) {
    const values=switchValues(node),panel=el('section');panel.className='switch-outlets';
    panel.setAttribute('aria-label','枚举分支出口');
    panel.append(el('h5',values.length?'枚举出口 · '+values.length+' 条路径，每次执行一条':'枚举出口 · 待选择路由块'));
    if(!values.length)panel.append(el('p','在配置中选择路由块后，这里会列出所有枚举及其分支。'));
    const list=el('div');list.className='switch-outlet-list';
    for(const value of [...new Set([...values,...node.cases.map(c=>c.value)])]){
      const index=node.cases.findIndex(c=>c.value===value),declared=values.includes(value);
      const label=el('span');label.className='switch-outlet';
      label.append(el('code',JSON.stringify(value)));
      if(!declared||index<0){label.classList.add('is-missing');label.append(el('small',declared?'待创建分支':'不在当前枚举中'));}
      list.append(label);
    }
    panel.append(list);
    const matched=values.length&&node.cases.length===values.length&&values.every(value=>node.cases.filter(c=>c.value===value).length===1);
    if(values.length&&!matched)panel.append(button('按路由枚举同步出口',()=>{
      const removed=node.cases.filter(c=>!values.includes(c.value));
      if(removed.some(c=>c.nodes.length)&&!window.confirm('同步将删除声明外分支及其中节点，继续？'))return;
      for(const c of removed)for(const n of allNodes(c.nodes))delete content.nodeConfigurations[n.nodeId];
      node.cases=values.map(value=>node.cases.find(c=>c.value===value)||{value,nodes:[],output:[]});changed();render();
    }));
    parent.append(panel);
  }
  function controlOutputCandidate(value, routing, root=value, seen=new Set()) {
    // 只排除 Schema 能明确证明不适用的出口；无法解析时留给后端预检。
    if(!value||typeof value!=='object')return true;
    if(value.$ref){
      if(!value.$ref.startsWith('#/$defs/')||seen.has(value.$ref))return true;
      const target=root.$defs?.[value.$ref.slice(8)];
      if(!target)return true;
      return controlOutputCandidate({...target,...Object.fromEntries(Object.entries(value).filter(([key])=>key!=='$ref'))},routing,root,new Set([...seen,value.$ref]));
    }
    if(!routing&&Array.isArray(value.anyOf))return value.anyOf.every(part=>controlOutputCandidate(part,false,root,seen));
    if(!value.type)return routing&&Array.isArray(value.anyOf)?false:true;
    if(value.type!==(routing?'string':'boolean'))return false;
    if(!routing)return true;
    const values=value.enum||(Object.hasOwn(value,'const')?[value.const]:[]);
    return Array.isArray(values)&&values.length>0&&values.every(item=>typeof item==='string');
  }
  function conditionEditor(parent,node,scope,incoming,automatic, routing=false){
    const conditionNode=routing?node.router:node.condition;
    if(conditionNode?.kind!=='block'){
      parent.append(el('p','此条件使用旧引用协议。请删除该控制节点并重新添加 Python 条件块。'));return;
    }
    const condition=el('label',routing?'Python 路由块 · 返回有限字符串枚举':'Python 条件块 · 独立执行并返回严格 bool');
    const blocks=latestResources().filter(r=>r.kind==='block');
    const available=blocks.filter(r=>controlOutputCandidate(r.schemas.output,routing));
    const conditionSelect=choices(available.map(r=>[r.resourceId,r.name+' · v'+r.version]),conditionNode.artifactRef,value=>{
      conditionNode.artifactRef=value;delete content.nodeConfigurations[conditionNode.nodeId];
      if(routing&&!node.cases.length)node.cases=switchValues(node).map(value=>({value,nodes:[],output:[]}));
      changed();render();
    });
    if(conditionNode.artifactRef&&!available.some(r=>r.resourceId===conditionNode.artifactRef)){
      const selected=conditionSelect.selectedOptions[0],resource=resources.find(r=>r.resourceId===conditionNode.artifactRef);
      selected.textContent=(resource?.name||'当前固定引用')+(resource&&!controlOutputCandidate(resource.schemas.output,routing)?'（出口类型不适用，请重新选择）':'（不在最新可选列表中）');selected.disabled=true;
    }
    condition.append(conditionSelect);parent.append(condition);
    parent.append(el('p',(routing?'按有限字符串枚举出口筛选':'按 bool 出口筛选')+'；已隐藏 '+(blocks.length-available.length)+' 个出口不适用的块。输入与参考兼容性仍以保存校验为准。'));
    if(!available.length)parent.append(el('p',routing?'暂无可选路由块，请先加载返回有限字符串 Literal 的通用块。':'暂无可选条件块，请先加载返回严格 bool 的通用块。'));
    parent.append(el('p','主数据：'+incoming+'；条件结果只选择路径。'));
    const resource=resources.find(r=>r.resourceId===conditionNode.artifactRef);
    const explain=adviceButton(resource);if(explain)parent.append(explain);
    const preview=el('div');portPreview(preview,resource?.primaryContract);parent.append(preview);
    referenceEditor(parent,conditionNode,resource,scope,automatic);
    parent.append(el('p',routing?'路由出口：有限字符串枚举，所有枚举值必须有且只有一个分支。':'条件出口：bool（true / false），保存时严格校验。'));
    if(resource?.apiRequired)parent.append(button('配置通用块 API',()=>configure(conditionNode,resource)));
  }
  function sequence(parent, nodes, inherited, incoming='服务完整输入', incomingReference='无（零项）') {
    parent.classList.add('flow-sequence');
    if(!nodes.length){const hint=el('p','点击 ＋ 添加这条路径的第一步');hint.className='empty-sequence';parent.append(hint);}
    nodes.forEach((node,index)=>{
      insertPoint(parent,nodes,index);
      const scope=[...inherited,...nodes.slice(0,index)];
      const resource=node.kind==='service'?component(node):resources.find(r=>r.resourceId===node.artifactRef);
      const card=el('article');card.className='flow-node';card.tabIndex=-1;card.dataset.nodeId=node.nodeId;card.dataset.kind=node.kind;
      if(node.condition?.nodeId||node.router?.nodeId)card.dataset.conditionId=(node.condition||node.router).nodeId;
      const header=el('div');header.className='node-header';
      const icon=el('span',({block:'▦',package:'✦',service:'▣',if:'⑂',repeat:'↻',while:'↻',foreach:'☷',switch:'⑂'})[node.kind]);icon.className='node-icon';
      const title=el('div');title.className='node-title';title.append(el('small',kindNames[node.kind]+' · '+node.nodeId+(resource ? ' · v'+resource.version+(resource.archived ? ' · 已归档' : '') : '')),el('h4',nodeName(node)));
      const actions=el('div');actions.className='node-actions';
      const explain=adviceButton(resource);if(explain)actions.append(explain);
      for(const [text,delta] of [['↑',-1],['↓',1]]) {
        const move=button(text,()=>{const next=index+delta;[nodes[index],nodes[next]]=[nodes[next],nodes[index]];changed();render(node.nodeId);});
        move.disabled=index+delta<0||index+delta>=nodes.length;move.setAttribute('aria-label',(delta<0?'上移':'下移')+' '+nodeName(node));actions.append(move);
      }
      const remove=button('×',()=>{
        for(const child of allNodes([node]))delete content.nodeConfigurations[child.nodeId];
        nodes.splice(index,1);if(!allNodes().some(n=>n.kind==='package'||n.kind==='service'&&component(n)?.budget))delete content.budget;changed();render();
      });remove.setAttribute('aria-label','删除 '+nodeName(node));actions.append(remove);header.append(icon,title,actions);card.append(header);
      const description=el('p',resource ? resource.description || '按输入数据执行处理，将结果提供给后续节点。' : controls.find(r=>r.kind===node.kind)?.description || '资源不可用，请重新加载。');description.className='node-description';card.append(description);
      const summary=el('div');summary.className='node-port-summary';
      const automatic=index ? nodeName(nodes[index-1])+' 本次执行的主数据输入' : incomingReference;
      const previousInput=index ? nodeName(nodes[index-1])+' 的完整输出' : incoming;
      let inputText=previousInput;
      if(node.kind==='if')inputText='条件 → 成立 / 否则';
      if(node.kind==='switch')inputText='枚举路由 → 选择下方一条路径';
      if(node.body)inputText=node.kind==='foreach'?'数组 → 逐项处理 → items 集合':'初始值 → 每轮处理 → 更新携带值';
      summary.append(el('span','输入 · '+inputText),el('span','输出 · '+(outputRef(node)?contractLabel(outputRef(node)):'待选择契约')));
      if(node.kind==='block'||node.kind==='package')referenceSummary(summary,resource);
      card.append(summary);
      const detail=el('details');detail.className='node-details';detail.append(el('summary',node.kind==='service'?'查看固定版本与契约':node.kind==='block'||node.kind==='package'?'查看固定契约与配置参数':'配置条件或循环'));card.append(detail);
      if(node.kind==='block'||node.kind==='package') {
        detail.append(el('h5','输入契约 · 自动接收'+previousInput));
        const inputPreview=el('div');portPreview(inputPreview,resource?.primaryContract);detail.append(inputPreview);
        referenceEditor(detail,node,resource,scope,automatic);
        detail.append(el('p','输入输出类型由'+kindNames[node.kind]+'固定声明。运行时输出不符合契约时，按服务设置重新调用本步骤；下一步不会执行。预算不足或取消时立即停止。'));
        detail.append(el('h5','输出契约 · 执行后可供后续步骤使用'));const outputPreview=el('div');portPreview(outputPreview,resource?.outputContract);detail.append(outputPreview);
        const raw=el('details');raw.className='raw-schema';raw.append(el('summary','查看完整契约 JSON'),el('pre',JSON.stringify(resource?.schemas,null,2)));detail.append(raw);
        if(node.kind==='package'||resource?.apiRequired){
          const configured=!!content.nodeConfigurations[node.nodeId];const status=el('p',configured?'参数已配置 · 兼容性以校验结果为准':'待配置 · '+(node.kind==='package'?'模型连接、参数与预算':'API 连接与请求路径'));status.className='configuration-status';card.append(status);
          const configButton=button('配置'+(node.kind==='package'?'模型与参数':' API 连接'),()=>configure(node,resource));configButton.disabled=!resource;detail.append(configButton);
        }
      } else if(node.kind==='service') {
        detail.append(el('p','固定实例：'+node.instanceId),el('p','内部节点使用已保存配置；子服务升级不会改变本节点。输入为上一层完整数据，不读取外层参考。内部预算按本任务累计，同时受父任务预算约束。'));
        const versionLabel=el('label','固定服务版本');
        versionLabel.append(choices(serviceComponents.filter(r=>r.serviceId===node.serviceId).map(r=>[r.instanceId,'v'+r.version+(r.current?' · 当前':'' )]),node.instanceId,id=>{
          node.instanceId=id;const selected=component(node);if(selected?.budget&&!content.budget)content.budget={...selected.budget};changed();render();
        }));detail.append(versionLabel);
        for(const [label,ref] of [['输入契约',resource?.inputContract],['输出契约',resource?.outputContract]]){detail.append(el('h5',label));const preview=el('div');portPreview(preview,ref);detail.append(preview);}
        detail.append(button('查看固定实例内容',()=>viewHistory(node.serviceId,node.instanceId)));
      } else if(node.kind==='if'||node.kind==='switch') {
        conditionEditor(detail,node,scope,previousInput,automatic,node.kind==='switch');
        if(node.kind==='switch')switchOverview(card,node);
        contractChoice(detail,'契约 · 分支输出契约',node.outputContract,v=>node.outputContract=v);
        const branches=el('div');branches.className='flow-branches';
        const entries=node.kind==='if'?[['thenBranch','成立 · true',node.thenBranch],['elseBranch','否则 · false',node.elseBranch]]:node.cases.map((c,i)=>['cases.'+i,c.value,c]);
        for(const [key,title,branchValue] of entries){
          const branch=el('div');branch.className='flow-branch';branch.dataset.branch=key;
          if(node.kind==='switch'){const heading=el('h5');heading.className='switch-branch-title';heading.append(el('span','路由结果为'),el('code',JSON.stringify(title)));branch.append(heading);}
          else branch.append(el('h5',title));
          const branchNodes=el('div');sequence(branchNodes,branchValue.nodes,scope,previousInput,automatic);branch.append(branchNodes);
          const output=el('details');output.className='branch-output';output.dataset.detailKey=node.nodeId+':'+key;output.append(el('summary','本分支返回什么'));
          bindingSection(output,'分支出口',branchValue.output,node.outputContract,[...scope,...branchValue.nodes]);branch.append(output);branches.append(branch);
        }
        card.append(branches,el('div','⑂ 分支汇合 · 统一输出给下一步'));card.lastChild.className='flow-merge';
      } else if(node.kind==='foreach') {
        const source=el('label','完整数组来源');
        source.append(choices(sourceOptions(scope),sourceValue(node.source),value=>{node.source=value?JSON.parse(value):{kind:'input'};node.arrayPath=[];changed();render();}));detail.append(source);
        const arrays=arrayFields(sourceSchema(node.source));
        const path=el('label','数组字段 · 根数组选 []');
        path.append(choices(arrays.map(([p])=>[JSON.stringify(p),p.length?p.join(' → '):'[] · 根数组']),JSON.stringify(node.arrayPath),value=>{if(value)node.arrayPath=JSON.parse(value);changed();render();}));detail.append(path);
        if(!arrays.length)detail.append(el('p','来源没有确定的数组字段，请先用通用块规范化。'));
        const limit=el('label','最大条数 · 超限时不执行任何元素'),input=el('input');input.type='number';input.min='1';input.step='1';input.value=node.maxItems;
        input.onchange=()=>{node.maxItems=Number(input.value);changed();};limit.append(input);detail.append(limit);
        contractChoice(detail,'每项输出契约',node.itemOutputContract,v=>node.itemOutputContract=v);
        detail.append(el('h5','当前元素输入'));const itemPreview=el('div');portPreview(itemPreview,'item:'+node.nodeId);detail.append(itemPreview);
        detail.append(el('h5','汇总输出 · items 保持输入顺序'));const resultPreview=el('div');portPreview(resultPreview,outputRef(node));detail.append(resultPreview);
        detail.append(el('p','循环体首步接收当前元素，默认零参考；完整上下文请在高级参考中选择。空数组返回 items: []。'));
        const body=el('div');body.className='loop-body';body.dataset.branch='body';
        sequence(body,node.body,[...scope,{kind:'item',nodeId:node.nodeId}],'当前数组元素','无（零项）');card.append(body);
      } else {
        const key=node.kind==='repeat'?'count':'maxIterations';const label=el('label',node.kind==='repeat'?'重复次数 · 0 表示跳过':'最大执行次数 · 防止无限循环');
        const input=el('input');input.type='number';input.min=node.kind==='repeat'?'0':'1';input.step='1';input.value=node[key]??'';input.dataset.count=key;
        input.onchange=()=>{if(input.value==='')delete node[key];else node[key]=Number(input.value);changed();render();};label.append(input);detail.append(label);
        contractChoice(detail,'契约 · 循环传递契约',node.carry.contract,v=>node.carry.contract=v);
        detail.append(el('p','初始值用于第一轮；循环体读取「本轮携带值」，每轮结束用「下轮携带值」更新。循环结束后输出最后的携带值。'));
        bindingSection(detail,'循环初始值',node.carry.initial,node.carry.contract,scope);
        const inner=[...scope,{kind:'carry',nodeId:node.nodeId,contract:node.carry.contract}];
        if(node.kind==='while')conditionEditor(detail,node,inner,'本轮完整携带值','无（零项）');
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
    if(kind==='package'||kind==='service'&&resource.budget) {
      const defaults=resource.budgetDefaults||resource.budget;
      if(!content.budget)content.budget={...defaults};
      else {content.budget.loopLimit+=defaults.loopLimit;content.budget.tokenLimit+=defaults.tokenLimit;}
    }
    let node={kind,nodeId,artifactRef:resource.resourceId};
    if(kind==='service')node={kind,nodeId,serviceId:resource.serviceId,instanceId:resource.instanceId};
    if(kind==='if')node={kind,nodeId,condition:{kind:'block',nodeId:nodeId+'_condition',artifactRef:''},outputContract:'',thenBranch:{nodes:[],output:[]},elseBranch:{nodes:[],output:[]}};
    if(kind==='foreach')node={kind,nodeId,source:{kind:'input'},arrayPath:[],maxItems:100,itemOutputContract:'',body:[]};
    if(kind==='switch')node={kind,nodeId,router:{kind:'block',nodeId:nodeId+'_router',artifactRef:''},outputContract:'',cases:[]};
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
  inputEvents.onInput($('contract-search'),renderContractOptions);
  $('contract-close').onclick=()=>$('contract-dialog').close();
  inputEvents.onInput($('insert-search'),renderInsertOptions);
  $('insert-close').onclick=()=>$('insert-dialog').close();
  $('node-close').onclick = () => $('node-dialog').close();
  async function refreshChoices(){
    const results=await Promise.all([window.agentPlatform.listContractGroups(),window.agentPlatform.listServiceComponents()]);
    if(results.some(result=>!result.ok)){$('service-result').textContent=results.find(result=>!result.ok).error.message;return;}
    contractGroups=results[0].data;serviceComponents=results[1].data;
    renderTabs();renderLibrary($('module-library'),$('module-search').value,resource=>add(resource));
  }
  async function refresh() {
    const result = await window.agentPlatform.listResources();
    if (!result.ok) { $('load-result').textContent = result.error.message; return; }
    resources = result.data; await refreshChoices(); await refreshAdviceModels();
    await refreshDrafts(); await refreshSaved(); render();
  }
  async function refreshDrafts() {
    const result = await window.agentPlatform.listDrafts(); if (!result.ok) return;
    $('draft-select').replaceChildren(new Option('新建草稿',''));
    for (const doc of result.data) $('draft-select').add(new Option(doc.content.name || doc.draftId,doc.draftId));
    $('draft-select').value = draftId;
  }
  let savedServices = [];
  function renderServiceOptions(selected=$('service-select').value){
    const query=$('service-search').value.trim().toLowerCase();
    $('service-select').replaceChildren(new Option('保存为新服务',''));
    for(const service of savedServices.filter(s=>s.serviceId===selected||(s.name+' '+s.serviceId).toLowerCase().includes(query)))$('service-select').add(new Option(service.name+' · v'+service.current.version,service.serviceId));
    $('service-select').value=selected;
  }
  inputEvents.onInput($('service-search'),()=>renderServiceOptions());
  async function refreshSaved(selected = $('service-select').value) {
    const result = await window.agentPlatform.listServices();
    if (!result.ok) { $('service-result').textContent=result.error.message;return; }
    savedServices=result.data;renderServiceOptions(selected);
    await refreshChoices();
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
    function tree(nodes,parent,configurations=history.flow.nodeConfigurations || history.flow.node_configurations || {}){for(const node of nodes){
      const item=el('fieldset');item.append(el('legend',node.nodeId+' · '+node.kind));
      const own={...node};delete own.body;delete own.thenBranch;delete own.elseBranch;delete own.cases;
      item.append(el('pre',JSON.stringify({node:own,configuration:configurations[node.nodeId]},null,2)));
      if(node.kind==='if')for(const key of ['thenBranch','elseBranch']){const branch=el('fieldset');branch.append(el('legend',key),el('pre',JSON.stringify(node[key].output,null,2)));tree(node[key].nodes,branch,configurations);item.append(branch);}
      if(node.cases)for(const c of node.cases){const branch=el('fieldset');branch.append(el('legend',c.value),el('pre',JSON.stringify(c.output,null,2)));tree(c.nodes,branch,configurations);item.append(branch);}
      if(node.body)tree(node.body,item,configurations);
      if(node.kind==='service'&&history.children?.[node.nodeId]){
        const child=history.children[node.nodeId],section=el('details');section.append(el('summary','固定子流程 · '+child.instanceId));
        tree(child.flow.flow,section,child.flow.nodeConfigurations||{});item.append(section);
      }
      parent.append(item);
    }}
    if(history.executable===false)target.append(el('p',history.upgradeMessage));
    else tree(history.flow.flow,target);
    const detail=el('details');detail.append(el('summary','完整快照、契约、参数和预算'),el('pre',JSON.stringify(history,null,2)));target.append(detail);
  }
  $('service-refresh').onclick=()=>refreshSaved();
  $('service-select').onchange=async()=>{
    const id=$('service-select').value;
    if(id){const result=await window.agentPlatform.serviceSchema(id);if(!result.ok){await refreshSaved(id);$('service-result').textContent=result.error.message;return;}
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
      let response = await window.agentPlatform.prepareResource(body);
      if (response.ok) {
        const jobId = response.data.jobId;
        $('load-cancel').hidden = false;
        $('load-cancel').onclick = () => window.agentPlatform.cancelPreparation(jobId);
        const phases = {check:'检查声明与依赖',download:'下载',install:'安装',verify:'验证',ready:'就绪',failed:'失败',cancelled:'已取消'};
        while (response.ok && !['ready','failed','cancelled'].includes(response.data.phase)) {
          const state = response.data;
          loadStatus('loading',(phases[state.phase] || state.phase) + (state.source ? '\n来源：'+state.source : '') +
            (state.downloadedBytes !== undefined ? '\n已下载 '+state.downloadedBytes+' 字节'+(state.totalBytes !== null && state.totalBytes !== undefined ? ' / '+state.totalBytes+' 字节' : '') : ''));
          await new Promise(resolve=>setTimeout(resolve,350));
          response = await window.agentPlatform.preparationStatus(jobId);
        }
        if (response.ok) response = response.data.phase === 'ready' ? {ok:true,data:response.data.resource} : {ok:false,error:response.data.error};
      }
      if (!response.ok) {
        loadStatus('error','加载失败：'+loadError(response.error)+'\n路径：'+body.path);return;
      }
      const listed = await window.agentPlatform.listResources();
      if (!listed.ok) {
        loadStatus('error','已录入 '+response.data.name+'，但列表刷新失败：'+loadError(listed.error));return;
      }
      resources = listed.data;
      await refreshChoices();
      $('module-search').value = '';
      renderLibrary($('module-library'),'',resource=>add(resource));render();
      loadStatus('success','已录入'+kindNames[body.kind]+'：'+response.data.name+'\n路径：'+body.path+'\n'+
        (response.data.archived ? '该版本已归档。包和块仅展示最新版本，旧版不会进入资源或契约选择列表。' : body.kind === 'contract' ? '现在可在输入契约、输出契约中选择。' : '现在可在左侧点击添加到流程；首次导入新版本时，同一 ID 的较低版本已自动归档。'));
    } catch {
      loadStatus('error','未能确认加载结果：桌面与后端通信失败，请重试加载（相同资源不会重复录入）。\n路径：'+body.path);
    } finally {
      $('load-cancel').hidden = true;
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
  renderTabs();renderLibrary($('module-library'),'',resource=>add(resource));
  render();
  return {refresh, validate, refreshAdviceModels};
})();
