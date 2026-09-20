/* 名称按任务实际实例解析，不能使用服务当前版本，否则历史节点会被错认。 */
const taskNodeNames = (() => {
  const instances = new Map();
  const controls = {if:'条件分支', while:'条件循环', repeat:'固定循环'};

  async function load(run, bridge) {
    const key = JSON.stringify([run.serviceId, run.instanceId]);
    if (!instances.has(key)) {
      const request = (async () => {
        const [history, catalog] = await Promise.all([
          bridge.getServiceVersion(run.serviceId, run.instanceId), bridge.listResources(),
        ]);
        if (!history.ok || !catalog.ok) throw new Error('任务节点名称读取失败');
        const resources = new Map(catalog.data.map(resource => [resource.resourceId, resource.name]));
        const names = new Map();
        function visit(nodes) {
          for (const node of nodes || []) {
            const id = node.nodeId || node.node_id;
            const name = resources.get(node.artifactRef || node.artifact_ref) || controls[node.kind];
            if (id && name) names.set(id, name);
            if (node.condition?.kind === 'block') visit([node.condition]);
            visit((node.thenBranch || node.then_branch)?.nodes);
            visit((node.elseBranch || node.else_branch)?.nodes);
            visit(node.body);
          }
        }
        visit(history.data.flow.flow);
        return names;
      })();
      instances.set(key, request);
    }
    try {
      return await instances.get(key);
    } catch {
      // 保留原节点标识；失败不缓存，后续查询可以重新获取历史名称。
      instances.delete(key);
      return new Map();
    }
  }

  function node(id, names) {
    return names.has(id) ? `${names.get(id)}（${id}）` : id;
  }

  function step(record, names) {
    if (record.stepId === 'nodes.output') return '服务返回';
    const id = record.packageBindingId || record.stepId.replace(/^(nodes|packages|model)\./, '');
    return node(id, names);
  }

  function path(value, names) {
    return value.replace(/^[A-Za-z][A-Za-z0-9_-]*/, id => node(id, names));
  }

  return {load, node, step, path};
})();
