(function () {
  if (document.body.classList.contains("hub-shell")) return;
  const params = new URLSearchParams(location.search || "");
  const embed = params.get("embed") === "1" || params.get("embed") === "true";
  const themeParam = (params.get("theme") || "").toLowerCase();
  const theme =
    themeParam === "dark" || themeParam === "light"
      ? themeParam
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";

  function pathSection(pathname) {
    const p = (pathname || "/").replace(/\/+$/, "") || "/";
    if (p === "/") return "home";
    const first = p.split("/").filter(Boolean)[0] || "home";
    const map = {
      marketplace: "marketplace",
      history: "history",
      work: "work",
      skills: "skills",
      rules: "rules",
      hooks: "hooks",
      agents: "agents",
      tasks: "tasks",
      tools: "tools",
      catalog: "catalog",
      google: "google",
      admin: "admin",
    };
    return map[first] || first;
  }

  function withEmbed(href) {
    try {
      const u = new URL(href, location.origin);
      if (!u.pathname.startsWith("/")) return href;
      u.searchParams.set("embed", "1");
      u.searchParams.set("theme", theme);
      return u.pathname + "?" + u.searchParams.toString() + u.hash;
    } catch {
      return href;
    }
  }

  function notifyParent() {
    try {
      parent.postMessage(
        { source: "am-hub", type: "nav", section: pathSection(location.pathname), theme },
        "*",
      );
    } catch (_) {}
  }

  function rewriteEmbedLinks(root) {
    (root || document).querySelectorAll('a[href^="/"]').forEach((a) => {
      const href = a.getAttribute("href");
      if (!href || href.startsWith("//")) return;
      a.setAttribute("href", withEmbed(href));
    });
  }

  if (embed) {
    document.body.classList.add("hub-embed");
    document.documentElement.classList.add("hub-embed");
    document.body.classList.add(theme === "dark" ? "hub-dark" : "hub-light");
    document.documentElement.classList.add(theme === "dark" ? "hub-dark" : "hub-light");
    document.documentElement.style.colorScheme = theme;
    rewriteEmbedLinks(document);
    notifyParent();
    document.addEventListener(
      "click",
      (ev) => {
        const a = ev.target && ev.target.closest ? ev.target.closest('a[href^="/"]') : null;
        if (!a) return;
        const href = a.getAttribute("href");
        if (!href) return;
        const next = withEmbed(href);
        if (next !== href) a.setAttribute("href", next);
        try {
          const u = new URL(next, location.origin);
          parent.postMessage(
            { source: "am-hub", type: "nav", section: pathSection(u.pathname), theme },
            "*",
          );
        } catch (_) {}
      },
      true,
    );
    return;
  }

  const path = (location.pathname || "/").replace(/\/+$/, "") || "/";
  const nav = [
    { sec: "Workspace" },
    { href: "/", label: "Home", match: ["/"] },
    { href: "/marketplace/", label: "Marketplace", match: ["/marketplace"] },
    { href: "/history/", label: "Chat history", match: ["/history"] },
    { href: "/work/", label: "Role activity", match: ["/work"] },
    { sec: "Asrax" },
    { href: "/skills/", label: "Skills", match: ["/skills"] },
    { href: "/rules/", label: "Rules", match: ["/rules"] },
    { href: "/hooks/", label: "Hooks", match: ["/hooks"] },
    { href: "/agents/", label: "Agents", match: ["/agents"] },
    { href: "/tasks/", label: "Tasks", match: ["/tasks"] },
    { sec: "Ops" },
    { href: "/tools/", label: "Tools playground", match: ["/tools"] },
    { href: "/catalog/", label: "Tool catalog", match: ["/catalog"] },
    { href: "/google/", label: "Google", match: ["/google"] },
    { href: "/admin/", label: "Integrations", match: ["/admin"] },
    { href: "/docs", label: "API docs", match: ["/docs"], external: true },
  ];

  function active(item) {
    if (!item.match) return false;
    return item.match.some((m) => (m === "/" ? path === "/" : path === m || path.startsWith(m + "/")));
  }

  const aside = document.createElement("aside");
  aside.className = "hub-sidebar";
  aside.innerHTML =
    '<a class="hub-brand" href="/"><div class="hub-avatar">AM</div><div class="hub-brand-text"><strong>AM MCP Hub</strong><span>Enterprise workspace</span></div></a>' +
    '<input class="hub-search" id="hubNavSearch" type="search" placeholder="Search settings" />' +
    '<nav class="hub-nav" id="hubNav"></nav>';

  const navEl = aside.querySelector("#hubNav");
  for (const item of nav) {
    if (item.sec) {
      const s = document.createElement("div");
      s.className = "sec";
      s.textContent = item.sec;
      navEl.appendChild(s);
      continue;
    }
    const a = document.createElement("a");
    a.href = item.href;
    a.textContent = item.label;
    if (item.external) a.target = "_blank";
    if (active(item)) a.classList.add("active");
    a.dataset.label = item.label.toLowerCase();
    navEl.appendChild(a);
  }

  aside.querySelector("#hubNavSearch").addEventListener("input", (e) => {
    const q = String(e.target.value || "").toLowerCase().trim();
    navEl.querySelectorAll("a").forEach((a) => {
      a.style.display = !q || a.dataset.label.includes(q) ? "" : "none";
    });
  });

  const main = document.createElement("div");
  main.className = "hub-main";
  while (document.body.firstChild) main.appendChild(document.body.firstChild);

  document.body.classList.add("hub-shell");
  document.body.classList.add(theme === "dark" ? "hub-dark" : "hub-light");
  document.documentElement.classList.add(theme === "dark" ? "hub-dark" : "hub-light");
  document.documentElement.style.colorScheme = theme;
  document.body.appendChild(aside);
  document.body.appendChild(main);

  const oldTop = main.querySelector(".top, header:not(.hub-page-head)");
  if (oldTop && !main.querySelector(".hub-page") && !oldTop.classList.contains("hub-page-head")) {
    oldTop.classList.add("legacy-top");
    if (oldTop.tagName === "HEADER") oldTop.classList.add("legacy-header");
  }
})();
