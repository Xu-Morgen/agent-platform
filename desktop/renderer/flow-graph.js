/* 从同一控制流模型生成代码与 SVG；只读展示，不参与实例编译。 */
const flowGraph = (() => {
  function build(flow, nameOf = node => node.nodeId) {
    const nodes = [], edges = [];
    const add = (label, depth = 0) => {
      const id = 's' + nodes.length;
      nodes.push({id, label, depth});
      return id;
    };
    const edge = (from, to, label = '') => edges.push({from, to, label});
    const describe = node => `${nameOf(node) || node.kind} · ${node.nodeId || '未配置'}`;
    function sequence(items, previous, depth = 0, firstLabel = '') {
      if (!Array.isArray(items)) throw new Error('流程结构不完整，无法生成状态图');
      for (const node of items) {
        const label = describe(node);
        let entry, exit;
        if (node.kind === 'if' || node.kind === 'switch') {
          const condition = node.kind === 'if' ? node.condition : node.router;
          entry = add(`${label}\n${node.kind === 'if' ? '条件' : '路由'}：${condition ? describe(condition) : '未配置'}`, depth);
          const branches = node.kind === 'if'
            ? [['true', node.thenBranch?.nodes], ['false', node.elseBranch?.nodes]]
            : (node.cases || []).map(branch => [branch.value, branch.nodes]);
          const ends = branches.map(([value, items]) => ({value, end: sequence(items || [], entry, depth + 1, String(value))}));
          exit = add(`${node.nodeId} · 分支汇合`, depth);
          for (const {value, end} of ends) edge(end, exit, end === entry ? String(value) : '');
        } else if (['repeat', 'while', 'foreach'].includes(node.kind)) {
          const info = node.kind === 'repeat' ? `固定 ${node.count ?? '?'} 次`
            : node.kind === 'while' ? `条件：${node.condition ? describe(node.condition) : '未配置'}；上限 ${node.maxIterations ?? '?'} 次`
            : `数组：${node.source?.kind || '?'}${node.source?.nodeId ? ':' + node.source.nodeId : ''} / ${(node.arrayPath || []).join('.') || '根数组'}；最多 ${node.maxItems ?? '?'} 项`;
          entry = add(`${label}\n${info}`, depth);
          const end = sequence(node.body || [], entry, depth + 1, node.kind === 'while' ? 'true 且未达上限' : '还有下一项 / 轮');
          edge(end, entry, end === entry
            ? (node.kind === 'while' ? 'true 且未达上限，下一轮' : '还有下一轮')
            : (node.kind === 'foreach' ? '收集输出，下一项' : '下一轮'));
          exit = add(`${node.nodeId} · ${node.kind === 'foreach' ? '有序结果集合' : '循环结束'}`, depth);
          edge(entry, exit, node.kind === 'while' ? 'false' : '已完成（可为 0 次）');
          if (node.kind === 'while' || node.kind === 'foreach') {
            const failure = add(`${node.nodeId} · 报错停止`, depth + 1);
            edge(entry, failure, node.kind === 'while' ? 'true 且已达上限' : '数组项数超限');
          }
        } else if (['package', 'block', 'service'].includes(node.kind)) {
          entry = exit = add(label + (node.kind === 'service' ? `\n固定实例：${node.instanceId || '未配置'}` : `\n${node.kind === 'package' ? '业务包' : '通用块'}`), depth);
        } else {
          throw new Error(`不支持此节点类型：${node.kind}；请使用 flow-6 服务或当前草稿`);
        }
        edge(previous, entry, firstLabel);
        firstLabel = '';
        previous = exit;
      }
      return previous;
    }
    const start = add('开始');
    const end = sequence(flow.flow, start);
    edge(end, add('结束'));
    return {nodes, edges};
  }

  const mermaidText = text => String(text).replace(/[\r\n]+/g, ' / ').replace(/["#&<>:;\[\]{}%\\]/g, char => '#' + char.charCodeAt(0) + ';');
  function code(graph) {
    return ['stateDiagram-v2', '    direction TB', ...graph.nodes.map(node => `    state "${mermaidText(node.label)}" as ${node.id}`),
      ...graph.edges.map(edge => `    ${edge.from} --> ${edge.to}${edge.label ? ' : ' + mermaidText(edge.label) : ''}`)].join('\n') + '\n';
  }

  function svg(graph, title) {
    const ns = 'http://www.w3.org/2000/svg';
    const element = (tag, attrs = {}, text) => {
      const node = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
      if (text !== undefined) node.textContent = text;
      return node;
    };
    // 顺序纵排、嵌套缩进；跨步骤及回边单独走右侧通道，避免穿过节点文字。
    const positions = new Map();
    const nodeWidth = 580, rowHeight = 135;
    const maxDepth = Math.max(0, ...graph.nodes.map(node => node.depth));
    const laneStart = 40 + maxDepth * 40 + nodeWidth;
    const width = laneStart + graph.edges.length * 12 + 250;
    const height = graph.nodes.length * rowHeight + 80;
    const root = element('svg', {xmlns:ns, viewBox:`0 0 ${width} ${height}`, width, height, role:'img', 'aria-label':title});
    root.append(element('title', {}, title), element('rect', {width:'100%', height:'100%', fill:'#ffffff'}));
    const defs = element('defs'), marker = element('marker', {id:'flow-arrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:7, markerHeight:7, orient:'auto-start-reverse'});
    marker.append(element('path', {d:'M 0 0 L 10 5 L 0 10 z', fill:'#52657d'}));defs.append(marker);root.append(defs);
    root.append(element('text', {x:30,y:28,'font-size':18,'font-family':'sans-serif',fill:'#15263c'},title));
    graph.nodes.forEach((node, index) => positions.set(node.id, {x:30 + node.depth * 40, y:50 + index * rowHeight, index}));
    graph.edges.forEach((edge, index) => {
      const from = positions.get(edge.from), to = positions.get(edge.to);
      let d, tx, ty;
      if (to.index === from.index + 1 && from.x === to.x) {
        tx = from.x + nodeWidth / 2; ty = from.y + 106;
        d = `M ${tx} ${from.y + 80} L ${tx} ${to.y}`;
      } else {
        const lane = laneStart + index * 12;
        const sy = from.y + 55, ey = to.y + 25;
        d = `M ${from.x + nodeWidth} ${sy} H ${lane} V ${ey} H ${to.x + nodeWidth}`;
        tx = from.x + nodeWidth + 8; ty = sy - 7;
      }
      root.append(element('path', {d,fill:'none',stroke:'#52657d','stroke-width':1.5,'marker-end':'url(#flow-arrow)'}));
      if (edge.label) root.append(element('text', {x:tx+5,y:ty,'font-size':12,'font-family':'sans-serif',fill:'#334a64'},edge.label));
    });
    for (const node of graph.nodes) {
      const {x,y} = positions.get(node.id);
      root.append(element('rect', {x,y,width:nodeWidth,height:80,rx:10,fill:'#eef4fc',stroke:'#8299b6'}));
      const text = element('text', {x:x+14,y:y+24,'font-size':13,'font-family':'sans-serif',fill:'#15263c'});
      text.append(element('title',{},node.label));
      // 长标识换行，完整文本同时保留在 title 与代码中。
      const lines = node.label.split('\n').flatMap(line => Array.from(line).reduce((chunks, char, index) => {
        if (index % 40 === 0) chunks.push(''); chunks[chunks.length-1] += char; return chunks;
      }, []));
      lines.slice(0,3).forEach((line,index) => text.append(element('tspan',{x:x+14,dy:index?20:0},line + (index===2 && lines.length>3?'…':''))));
      root.append(text);
    }
    return root;
  }

  function download(name, value, type) {
    const url = URL.createObjectURL(new Blob([value], {type}));
    const link = document.createElement('a');link.href=url;link.download=name;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function show(flow, title, nameOf) {
    const graph = build(flow, nameOf), source = code(graph), drawing = svg(graph, title);
    const $ = id => document.getElementById(id);
    $('flow-graph-title').textContent = title;
    $('flow-graph-preview').replaceChildren(drawing);
    $('flow-graph-code').value = source;
    const filename = title.replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').slice(0,100) || 'service-flow';
    $('flow-graph-source-download').onclick=()=>download(filename+'.mmd',source,'text/plain;charset=utf-8');
    $('flow-graph-svg-download').onclick=()=>download(filename+'.svg',new XMLSerializer().serializeToString(drawing),'image/svg+xml;charset=utf-8');
    $('flow-graph-close').onclick=()=>$('flow-graph-dialog').close();
    $('flow-graph-dialog').showModal();
  }
  return {build, code, show};
})();
