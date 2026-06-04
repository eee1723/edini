#!/usr/bin/env python3
"""
Edini Wiki Builder — MD to rich HTML with interactive features.
Usage: python scripts/build.py
"""

import json
import shutil
import sys
from pathlib import Path

try:
    import markdown as md_lib
except ImportError:
    print("Error: 'markdown' package not found. Install: pip install markdown")
    sys.exit(1)

WIKI_DIR = Path(__file__).resolve().parent.parent
PAGES_DIR = WIKI_DIR / "pages"
HTML_DIR = WIKI_DIR / "html"
ASSETS_DIR = HTML_DIR / "assets"
CONFIG_PATH = WIKI_DIR / "wiki.json"
CSS_PATH = WIKI_DIR / "style.css"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prelude(config: dict, page: dict) -> str:
    """Generate <head> through opening <body> tag, including sidebar nav."""
    project = config["project"]
    pages = config["pages"]
    features = config.get("features", {})

    nav_items = []
    for p in pages:
        active = " active" if p["id"] == page["id"] else ""
        icon = p.get("icon", "")
        nav_items.append(
            f'<a class="nav-item{active}" href="{p["id"]}.html">'
            f'<span class="nav-icon">{icon}</span>{p["title"]}</a>'
        )
    nav_html = "\n        ".join(nav_items)

    search_html = ""
    if features.get("search"):
        search_html = """
    <div class="search-box">
      <input type="text" id="wiki-search" placeholder="搜索 Wiki... (Ctrl+K)" autocomplete="off">
      <div class="search-results" id="search-results"></div>
    </div>"""

    dark_mode_toggle = ""
    if features.get("dark_mode"):
        dark_mode_toggle = """
    <button class="dark-toggle" id="dark-toggle" title="切换暗色模式" aria-label="切换暗色模式">
      <span class="dark-icon-light">☀️</span>
      <span class="dark-icon-dark">🌙</span>
    </button>"""

    return f"""<!DOCTYPE html>
<html lang="{project.get('lang', 'zh-CN')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project['name']} Wiki - {page['title']}</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <nav class="sidebar">
    <div class="project-info">
      <div class="project-name">{project['name']}</div>
      <div class="project-desc">{project['description']}</div>
    </div>
    {search_html}
    <div class="nav-label">Wiki Pages</div>
    <div class="nav-list">
        {nav_html}
    </div>
    {dark_mode_toggle}
  </nav>
  <main class="content">
"""


def build_postlude(page: dict, features: dict) -> str:
    toc = ""
    if features.get("toc"):
        toc = '<nav class="wiki-toc"><div class="toc-title">本页目录</div></nav>'

    footer = f"""    <footer class="footer">
      <span>{page['title']}</span>
      <span>由 Edini Wiki 系统生成</span>
    </footer>
  </main>"""

    return f"""{toc}
{footer}"""


def build_scripts(features: dict, page: dict) -> str:
    """Generate all script tags based on enabled features."""
    scripts = ""

    if features.get("dark_mode"):
        scripts += """
  <script>
    (function() {
      const saved = localStorage.getItem('wiki-dark');
      if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
      }
    })();
  </script>"""

    if features.get("search"):
        scripts += '\n  <script src="assets/search.js" defer></script>'

    if features.get("copy_buttons"):
        scripts += """
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      document.querySelectorAll('pre').forEach(function(block) {
        if (block.closest('.code-block')) return;
        var wrapper = document.createElement('div');
        wrapper.className = 'code-block';
        var btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.textContent = '复制';
        btn.onclick = function() {
          var code = block.querySelector('code') || block;
          navigator.clipboard.writeText(code.textContent).then(function() {
            btn.textContent = '已复制!';
            setTimeout(function() { btn.textContent = '复制'; }, 2000);
          }).catch(function() {
            btn.textContent = '失败';
            setTimeout(function() { btn.textContent = '复制'; }, 2000);
          });
        };
        block.parentNode.insertBefore(wrapper, block);
        wrapper.appendChild(btn);
        wrapper.appendChild(block);
      });
    });
  </script>"""

    if features.get("filterable_lists") and page.get("filterable"):
        scripts += """
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      var filters = document.querySelectorAll('.wiki-filter');
      if (!filters.length) return;
      filters.forEach(function(filter) {
        filter.addEventListener('change', applyFilters);
      });
      function applyFilters() {
        var active = {};
        filters.forEach(function(f) {
          var val = f.value;
          if (val) active[f.dataset.key] = val;
        });
        document.querySelectorAll('.filterable-item').forEach(function(item) {
          var show = true;
          for (var key in active) {
            if (item.dataset[key] !== active[key]) { show = false; break; }
          }
          item.style.display = show ? '' : 'none';
        });
      }
    });
  </script>"""

    if features.get("toc"):
        scripts += """
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      var toc = document.querySelector('.wiki-toc');
      if (!toc) return;
      var headings = document.querySelectorAll('.content h2, .content h3');
      headings.forEach(function(h, i) {
        var id = h.textContent.replace(/\\s+/g, '-').replace(/[^\\w\\u4e00-\\u9fff-]/g, '');
        if (!id) id = 'h-' + i;
        h.id = id;
        var a = document.createElement('a');
        a.href = '#' + id;
        a.className = 'toc-item toc-level-' + (h.tagName === 'H2' ? '0' : '1');
        a.textContent = h.textContent;
        toc.appendChild(a);
      });
      var links = toc.querySelectorAll('.toc-item');
      window.addEventListener('scroll', function() {
        var current = '';
        headings.forEach(function(h) {
          if (window.scrollY >= h.offsetTop - 100) current = h.id;
        });
        links.forEach(function(l) {
          l.classList.toggle('active', l.getAttribute('href') === '#' + current);
        });
      });
    });
  </script>"""

    return scripts


def build_search_index(pages: list) -> list:
    """Build search index from all pages."""
    index = []
    for page in pages:
        md_file = PAGES_DIR / f"{page['id']}.md"
        if not md_file.exists():
            continue
        content = md_file.read_text(encoding="utf-8")
        index.append({
            "id": page["id"],
            "title": page["title"],
            "url": f"{page['id']}.html",
            "text": content[:5000]
        })
    return index


def inject_page_features(md_content: str, page: dict, features: dict) -> str:
    """Inject filter controls or other page-specific features."""
    if not features.get("filterable_lists") or not page.get("filterable"):
        return md_content

    page_id = page["id"]

    if page_id == "pitfalls":
        filter_html = """<div class="filter-bar">
  <span class="filter-label">筛选：</span>
  <select class="wiki-filter" data-key="category">
    <option value="">全部分类</option>
    <option value="Python">Python/PySide6</option>
    <option value="Houdini">Houdini API</option>
    <option value="Pi">Pi Agent</option>
    <option value="TypeScript">TypeScript/Node</option>
    <option value="JSON-RPC">JSON-RPC</option>
    <option value="部署">部署/安装</option>
    <option value="开发流程">开发流程</option>
  </select>
  <select class="wiki-filter" data-key="priority">
    <option value="">全部优先级</option>
    <option value="高">高</option>
    <option value="中">中</option>
    <option value="低">低</option>
  </select>
  <select class="wiki-filter" data-key="status">
    <option value="">全部状态</option>
    <option value="已修复">已修复</option>
    <option value="待修复">待修复</option>
    <option value="已验证">已验证</option>
    <option value="信息">信息</option>
  </select>
</div>

"""
        first_h3 = md_content.find("\n### ")
        if first_h3 > 0:
            md_content = md_content[:first_h3] + "\n" + filter_html + "\n" + md_content[first_h3:]

    elif page_id == "progress":
        filter_html = """<div class="filter-bar">
  <span class="filter-label">阶段筛选：</span>
  <select class="wiki-filter" data-key="status">
    <option value="">全部</option>
    <option value="done">已完成</option>
    <option value="wip">进行中</option>
    <option value="pending">计划中</option>
  </select>
</div>

"""
        first_section = md_content.find("\n## ")
        if first_section > 0:
            next_section = md_content.find("\n## ", first_section + 1)
            if next_section > 0:
                md_content = md_content[:next_section] + "\n" + filter_html + "\n" + md_content[next_section:]

    return md_content


def generate_all():
    config = load_config()
    pages = config.get("pages", [])
    features = config.get("features", {})

    HTML_DIR.mkdir(exist_ok=True)
    ASSETS_DIR.mkdir(exist_ok=True)

    generated = 0
    for page in pages:
        md_file = PAGES_DIR / f"{page['id']}.md"
        if not md_file.exists():
            print(f"  ! {page['id']}.md not found, skipping")
            continue

        md_content = md_file.read_text(encoding="utf-8")

        # Inject page-specific features
        md_content = inject_page_features(md_content, page, features)

        # Convert MD to HTML
        html_body = md_lib.markdown(
            md_content,
            extensions=["tables", "fenced_code", "toc", "attr_list", "md_in_html"],
        )

        # Assemble full page
        prelude = build_prelude(config, page)
        postlude = build_postlude(page, features)
        scripts = build_scripts(features, page)
        full_html = prelude + "\n" + html_body + "\n" + postlude + "\n" + scripts + "\n</body>\n</html>"

        output_path = HTML_DIR / f"{page['id']}.html"
        output_path.write_text(full_html, encoding="utf-8")
        print(f"  ok  {page['id']}.html")
        generated += 1

    # Copy CSS
    if CSS_PATH.exists():
        shutil.copy(CSS_PATH, ASSETS_DIR / "style.css")
        print("  ok  assets/style.css")

    # Generate search index
    if features.get("search"):
        search_index = build_search_index(pages)
        index_path = ASSETS_DIR / "search_index.json"
        index_path.write_text(json.dumps(search_index, ensure_ascii=False), encoding="utf-8")
        print("  ok  assets/search_index.json")

    # Copy search.js if it exists
    search_js_path = WIKI_DIR / "scripts" / "search.js"
    if search_js_path.exists():
        shutil.copy(search_js_path, ASSETS_DIR / "search.js")
        print("  ok  assets/search.js")

    print(f"\nDone. {generated} pages generated. Open html/index.html in browser.")


if __name__ == "__main__":
    generate_all()
