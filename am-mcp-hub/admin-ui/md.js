/* Shared lightweight Markdown renderer for hub admin UI. */
(function (global) {
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  }

  function inlineMd(text) {
    let s = esc(text);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(?<![\w*])\*([^*]+)\*(?![\w*])/g, '<em>$1</em>');
    return s;
  }

  function mdToHtml(src) {
    const text = String(src ?? '').replace(/\r\n/g, '\n');
    const lines = text.split('\n');
    const out = [];
    let i = 0;
    let inCode = false;
    let codeBuf = [];
    let listType = null;

    function closeList() {
      if (listType) {
        out.push(listType === 'ol' ? '</ol>' : '</ul>');
        listType = null;
      }
    }

    while (i < lines.length) {
      const line = lines[i];
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        if (inCode) {
          out.push('<pre><code>' + esc(codeBuf.join('\n')) + '</code></pre>');
          codeBuf = [];
          inCode = false;
        } else {
          closeList();
          inCode = true;
          codeBuf = [];
        }
        i++;
        continue;
      }
      if (inCode) {
        codeBuf.push(line);
        i++;
        continue;
      }
      if (/^\s*---\s*$/.test(line)) {
        closeList();
        out.push('<hr/>');
        i++;
        continue;
      }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        closeList();
        const lvl = heading[1].length;
        out.push('<h' + lvl + '>' + inlineMd(heading[2]) + '</h' + lvl + '>');
        i++;
        continue;
      }
      const ul = line.match(/^\s*[-*]\s+(.+)$/);
      if (ul) {
        if (listType !== 'ul') {
          closeList();
          out.push('<ul>');
          listType = 'ul';
        }
        out.push('<li>' + inlineMd(ul[1]) + '</li>');
        i++;
        continue;
      }
      const ol = line.match(/^\s*(\d+)\.\s+(.+)$/);
      if (ol) {
        if (listType !== 'ol') {
          closeList();
          out.push('<ol>');
          listType = 'ol';
        }
        out.push('<li>' + inlineMd(ol[2]) + '</li>');
        i++;
        continue;
      }
      if (/^>\s?/.test(line)) {
        closeList();
        out.push('<blockquote><p>' + inlineMd(line.replace(/^>\s?/, '')) + '</p></blockquote>');
        i++;
        continue;
      }
      if (!line.trim()) {
        closeList();
        i++;
        continue;
      }
      closeList();
      out.push('<p>' + inlineMd(line) + '</p>');
      i++;
    }
    if (inCode) out.push('<pre><code>' + esc(codeBuf.join('\n')) + '</code></pre>');
    closeList();
    return out.join('') || '<pre><code>' + esc(src || '') + '</code></pre>';
  }

  function codeHtml(src) {
    return '<pre><code>' + esc(src || '') + '</code></pre>';
  }

  global.HubMd = { esc, inlineMd, mdToHtml, codeHtml };
})(typeof window !== 'undefined' ? window : globalThis);
