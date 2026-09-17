// Hash 路由兼容 Electron 本地文件，切页保留表单和在途任务。
(() => {
  const routes = {
    '/overview': '平台概览',
    '/environments': '环境配置',
    '/services': '服务配置',
    '/tasks': '任务调用',
  };
  const scrollPositions = new Map();
  let currentRoute;
  function renderRoute() {
    let route = window.location.hash.slice(1);
    if (!Object.hasOwn(routes, route)) {
      route = '/overview';
      window.history.replaceState(null, '', `#${route}`);
    }
    if (currentRoute) scrollPositions.set(currentRoute, window.scrollY);
    for (const page of document.querySelectorAll('[data-page]')) {
      page.hidden = `/${page.dataset.page}` !== route;
    }
    for (const link of document.querySelectorAll('nav a')) {
      if (link.hash === `#${route}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    const title = document.querySelector('#page-title');
    title.textContent = routes[route];
    document.title = `${routes[route]} · Agent Platform`;
    if (currentRoute) title.focus({ preventScroll: true });
    window.scrollTo(0, scrollPositions.get(route) || 0);
    currentRoute = route;
  }
  window.addEventListener('hashchange', renderRoute);
  renderRoute();
})();
