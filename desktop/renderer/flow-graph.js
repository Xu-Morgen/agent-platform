/* 同一只读模型生成 Mermaid 与 SVG；布局按流程作用域分列，不参与编译。 */
const flowGraph = (() => {
  function schemaSummary(schema = {}) {
    const resolve = value => value?.$ref?.startsWith('#/')
      ? value.$ref.slice(2).split('/').reduce((root, key) => root?.[key.replace(/~1/g,'/').replace(/~0/g,'~')], schema) || value : value || {};
    function type(value, depth = 0) {
      value = resolve(value);
      if (value.const !== undefined) return JSON.stringify(value.const);
      if (value.enum) return value.enum.map(item=>JSON.stringify(item)).join(' | ');
      const union = value.anyOf || value.oneOf;
      if (union) return union.map(item=>type(item,depth+1)).join(' | ');
      if (value.type === 'array') return `Array<${depth < 2 ? type(value.items,depth+1) : '…'}>`;
      if (value.properties) return value.title || 'object';
      return value.type || value.title || '未提供结构';
    }
    const root = resolve(schema), fields = Object.entries(root.properties || {});
    return [root.title || type(root), ...fields.map(([key,value]) =>
      `  ${key}${root.required?.includes(key) ? '' : '?'}: ${type(value)}`)].join('\n');
  }

  function build(flow, nameOf = node=>node.nodeId, details = {}) {
    const nodes = [], edges = [];
    const resource = node => (details.resources || []).find(item=>item.resourceId===node?.artifactRef);
    const service = node => (details.services || []).find(item=>item.instanceId===node.instanceId && item.serviceId===node.serviceId);
    const contract = ref => details.contractSchema?.(ref) || {};
    const summary = (schema, ref) => Object.keys(schema || {}).length ? schemaSummary(schema) : (ref || '未配置');
    const source = value => !value ? '未配置' : value.kind==='input' ? '服务输入' : value.kind==='constant' ? '固定值' : `${value.kind}:${value.nodeId || '?'}`;
    const bindings = values => (values || []).map(value=>source(value.source)).join('，') || '未配置';
    const describe = node => `${nameOf(node) || node.kind} · ${node.nodeId || '未配置'}`;
    const io = node => {
      const r = resource(node), s = node.kind==='service' ? service(node) : undefined;
      const output = node.outputContract || node.carry?.contract || node.itemOutputContract;
      const lines = [];
      if(r || s) {
        lines.push('输入：' + summary(r?.schemas?.primary || s?.schemas?.input,r?.primaryContract || s?.inputContract));
        lines.push('输出：' + summary(r?.schemas?.output || s?.schemas?.output,r?.outputContract || s?.outputContract));
      } else if(output) lines.push((node.kind==='foreach'?'每项输出：':'输出：') + summary(contract(output),output));
      else if(['block','package','service'].includes(node.kind)) lines.push('输入 / 输出：固定资源信息不可用');
      if(node.kind==='foreach')lines.push('集合输出：{ items: Array<每项输出> }');
      if(r)lines.push('参考：' + (node.references===undefined || node.references===null ? '简单模式（上一节点当次 primary）' : node.references.map(source).join('，') || '无'));
      return lines.join('\n');
    };
    function decision(node) {
      if(!node)return '条件块未配置';
      const r=resource(node);
      return [describe(node),io(node),'Python 入口（原文）：',r?.entrySource || '源码不可用；图中按声明的返回值展示分支'].filter(Boolean).join('\n');
    }
    const add = (label,col,row,kind='step') => {
      const id='s'+nodes.length;nodes.push({id,label,col,row,kind});return id;
    };
    const edge = (from,to,back=false,lane=0) => edges.push({from,to,back,lane});
    const branches = node => node.kind==='if'
      ? [{value:'true',nodes:node.thenBranch?.nodes || [],output:node.thenBranch?.output},{value:'false',nodes:node.elseBranch?.nodes || [],output:node.elseBranch?.output}]
      : node.cases || [];
    const widthOf = items => Math.max(1,...items.map(node=>{
      if(['if','switch'].includes(node.kind))return Math.max(1,branches(node).reduce((sum,branch)=>sum+widthOf(branch.nodes || []),0));
      if(['while','repeat','foreach'].includes(node.kind))return widthOf(node.body || [])+(['while','foreach'].includes(node.kind)?3:2);
      return 1;
    }));
    function sequence(items, previous, row, left, width) {
      if(!Array.isArray(items))throw new Error('流程结构不完整，无法生成状态图');
      const center=left+(width-1)/2;
      for(const node of items) {
        let entry,exit;
        if(['if','switch'].includes(node.kind)) {
          const condition=node.kind==='if'?node.condition:node.router;
          entry=add([describe(node),decision(condition)].join('\n'),center,row++,'decision');
          const ends=[];let branchLeft=left,maxRow=row;
          for(const branch of branches(node)) {
            const branchWidth=widthOf(branch.nodes || []), col=branchLeft+(branchWidth-1)/2;
            const gate=add(`${condition?.nodeId || '条件块'} 返回 = ${JSON.stringify(node.kind==='if' ? branch.value==='true' : branch.value)}`,col,row,'condition');
            edge(entry,gate);
            const result=sequence(branch.nodes || [],gate,row+1,branchLeft,branchWidth);
            const out=add('分支返回：'+bindings(branch.output),col,result.row,'join');edge(result.end,out);
            ends.push(out);maxRow=Math.max(maxRow,result.row+1);branchLeft+=branchWidth;
          }
          row=maxRow;exit=add(describe(node)+' · 汇合\n'+io(node),center,row++,'join');ends.forEach(end=>edge(end,exit));
        } else if(['repeat','while','foreach'].includes(node.kind)) {
          const isWhile=node.kind==='while',isEach=node.kind==='foreach';
          const info=isWhile ? decision(node.condition)+`\n最大迭代次数：${node.maxIterations ?? '?'}`
            : isEach ? `输入数组：${source(node.source)} / ${(node.arrayPath || []).join('.') || '根数组'}\n最大项数：${node.maxItems ?? '?'}`
            : `固定次数：${node.count ?? '?'}`;
          entry=add(describe(node)+'\n'+info+'\n'+io(node)+(node.carry?'\n初始值：'+bindings(node.carry.initial)+'\n每轮更新：'+bindings(node.carry.update):''),center,row++,'decision');
          const bodyWidth=widthOf(node.body || []),bodyLeft=left+1,bodyCol=bodyLeft+(bodyWidth-1)/2;
          const enter=add(isWhile?'返回 true，且迭代次数 < 上限':isEach?'数组未超限，且还有下一项':'已执行次数 < 固定次数',bodyCol,row,'condition');edge(entry,enter);
          const doneCol=left+bodyWidth+1;
          const done=add(isWhile?'返回 false':isEach?'数组未超限，且全部处理完成（含空数组）':'已执行次数 = 固定次数（含 0 次）',doneCol,row,'condition');edge(entry,done);
          if(isWhile || isEach) {
            const fail=add(isWhile?'返回 true，且迭代次数 ≥ 上限\n报错停止':'数组长度 > 最大项数\n首项执行前报错停止',left+bodyWidth+2,row,'error');edge(entry,fail);
          }
          const body=sequence(node.body || [],enter,row+1,bodyLeft,bodyWidth);
          const again=add(isEach?'收集本项输出，继续下一项':'更新循环携带值，继续下一轮',bodyCol,body.row,'condition');edge(body.end,again);edge(again,entry,true,left);
          row=body.row+1;exit=add(describe(node)+' · '+(isEach?'有序结果集合':'循环结束')+'\n'+io(node),center,row++,'join');edge(done,exit);
        } else if(['block','package','service'].includes(node.kind)) {
          entry=exit=add(describe(node)+'\n'+(node.kind==='service'?'固定实例：'+node.instanceId:node.kind==='package'?'业务包':'通用块')+'\n'+io(node),center,row++);
        } else throw new Error('不支持此节点类型：'+node.kind);
        edge(previous,entry);previous=exit;
      }
      return {end:previous,row};
    }
    if(!Array.isArray(flow.flow))throw new Error('流程结构不完整');
    const width=widthOf(flow.flow),center=(width-1)/2;
    const start=add('服务输入\n'+summary(details.input || contract(flow.inputContract),flow.inputContract),center,0,'terminal');
    const result=sequence(flow.flow,start,1,0,width);
    const end=add('服务输出\n'+summary(details.output || contract(flow.outputContract),flow.outputContract),center,result.row,'terminal');edge(result.end,end);
    return {nodes,edges,width};
  }

  const mermaidText = text => String(text).replace(/[\r\n]+/g,' / ').replace(/["#&<>:;\[\]{}%\\]/g,char=>'#'+char.charCodeAt(0)+';');
  function code(graph) {
    return ['stateDiagram-v2','    direction TB',...graph.nodes.map(node=>`    state "${mermaidText(node.label)}" as ${node.id}`),...graph.edges.map(edge=>`    ${edge.from} --> ${edge.to}`)].join('\n')+'\n';
  }

  function svg(graph,title) {
    const ns='http://www.w3.org/2000/svg';
    const el=(tag,attrs={},text)=>{const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;return node;};
    const measure=document.createElement('canvas').getContext('2d');measure.font='14px sans-serif';
    const nodeWidth=440,gap=90,padding=18,lineHeight=22;
    function wrap(text) {
      return text.split('\n').flatMap(line=>{
        const result=[];let part='';
        for(const char of line){if(part && measure.measureText(part+char).width>nodeWidth-2*padding){result.push(part);part='';}part+=char;}
        result.push(part);return result;
      });
    }
    const rows=[],positions=new Map();
    for(const node of graph.nodes){const lines=wrap(node.label),height=lines.length*lineHeight+2*padding;positions.set(node.id,{x:35+node.col*(nodeWidth+gap),height,lines});rows[node.row]=Math.max(rows[node.row]||0,height);}
    let y=80;const rowY=rows.map(height=>{const start=y;y+=height+90;return start;});
    for(const node of graph.nodes)positions.get(node.id).y=rowY[node.row];
    const width=Math.max(700,graph.width*(nodeWidth+gap)+70,measure.measureText(title).width+80),height=y+20;
    const root=el('svg',{xmlns:ns,viewBox:`0 0 ${width} ${height}`,width,height,role:'img','aria-label':title});
    root.append(el('title',{},title),el('rect',{width:'100%',height:'100%',fill:'#fff'}));
    const defs=el('defs'),marker=el('marker',{id:'flow-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'});
    marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#52657d'}));defs.append(marker);root.append(defs);
    root.append(el('text',{x:35,y:35,'font-size':18,'font-family':'sans-serif',fill:'#15263c'},title));
    for(const edge of graph.edges) {
      const from=positions.get(edge.from),to=positions.get(edge.to),sx=from.x+nodeWidth/2,sy=from.y+from.height,tx=to.x+nodeWidth/2,ty=to.y;
      let d;
      if(edge.back){const lane=35+edge.lane*(nodeWidth+gap);d=`M ${sx} ${sy} V ${sy+30} H ${lane} V ${to.y+24} H ${to.x}`;}
      else {const fromNode=graph.nodes.find(node=>node.id===edge.from),toNode=graph.nodes.find(node=>node.id===edge.to);
        // 分流在起点行下方折线，汇流在终点行上方折线；留在各分支自己的列内。
        const bend=toNode.row>fromNode.row+1 ? ty-35 : rowY[fromNode.row]+rows[fromNode.row]+40;
        d=`M ${sx} ${sy} V ${bend} H ${tx} V ${ty}`;}
      root.append(el('path',{d,fill:'none',stroke:edge.back?'#93672b':'#52657d','stroke-width':1.5,'marker-end':'url(#flow-arrow)','data-edge':`${edge.from}:${edge.to}`}));
    }
    const colors={decision:['#fff6e5','#b99040'],condition:['#fffdf2','#c9b878'],error:['#fff0f0','#c57979'],terminal:['#eaf7f0','#6c9b80'],join:['#f4f5f8','#a4adba'],step:['#eef4fc','#8299b6']};
    for(const node of graph.nodes) {
      const p=positions.get(node.id),[fill,stroke]=colors[node.kind];
      const group=el('g',{'data-node':node.id});group.append(el('rect',{x:p.x,y:p.y,width:nodeWidth,height:p.height,rx:node.kind==='condition'?18:10,fill,stroke}));
      const text=el('text',{'font-size':14,'font-family':'sans-serif',fill:'#15263c','xml:space':'preserve'});text.append(el('title',{},node.label));
      p.lines.forEach((line,index)=>text.append(el('tspan',{x:p.x+padding,y:p.y+padding+16+index*lineHeight},line)));
      group.append(text);root.append(group);
    }
    return root;
  }

  function download(name, value, type) {
    const url = URL.createObjectURL(new Blob([value], {type}));
    const link = document.createElement('a');link.href=url;link.download=name;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function show(flow, title, nameOf, details) {
    const graph = build(flow, nameOf, details), source = code(graph), drawing = svg(graph, title);
    const $ = id => document.getElementById(id);
    $('flow-graph-title').textContent = title;
    $('flow-graph-preview').replaceChildren(drawing);
    $('flow-graph-code').value = source;
    const filename = title.replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').slice(0,100) || 'service-flow';
    $('flow-graph-source-download').onclick=()=>download(filename+'.mmd',source,'text/plain;charset=utf-8');
    $('flow-graph-close').onclick=()=>$('flow-graph-dialog').close();
    $('flow-graph-dialog').showModal();
    const preview=$('flow-graph-preview'),zoom=$('flow-graph-zoom');
    const originalWidth=drawing.viewBox.baseVal.width,originalHeight=drawing.viewBox.baseVal.height;
    const resize=()=>{
      const scale=zoom.value==='fit'?Math.min(1,(preview.clientWidth-20)/originalWidth):Number(zoom.value);
      drawing.setAttribute('width',originalWidth*scale);drawing.setAttribute('height',originalHeight*scale);
      preview.scrollLeft=Math.max(0,originalWidth*scale/2-preview.clientWidth/2);
    };
    zoom.value='0.75';zoom.onchange=resize;resize();preview.scrollTop=0;
    $('flow-graph-svg-download').onclick=()=>{
      const exported=drawing.cloneNode(true);exported.setAttribute('width',originalWidth);exported.setAttribute('height',originalHeight);
      download(filename+'.svg',new XMLSerializer().serializeToString(exported),'image/svg+xml;charset=utf-8');
    };
  }
  return {build, code, show};
})();
