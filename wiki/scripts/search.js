// Daito Wiki — Client-side full-text search
(function () {
  var SEARCH_INDEX_URL = 'assets/search_index.json';
  var searchIndex = [];
  var searchInput = null;
  var searchResults = null;

  function init() {
    searchInput = document.getElementById('wiki-search');
    searchResults = document.getElementById('search-results');
    if (!searchInput || !searchResults) return;

    // Load search index
    fetch(SEARCH_INDEX_URL)
      .then(function (r) { return r.json(); })
      .then(function (data) { searchIndex = data; })
      .catch(function () {});

    searchInput.addEventListener('input', handleSearch);
    searchInput.addEventListener('focus', function () {
      if (searchInput.value.trim()) handleSearch();
    });

    // Click outside to close
    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.classList.remove('visible');
      }
    });

    // Keyboard shortcuts: Ctrl+K or /
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && document.activeElement === document.body)) {
        e.preventDefault();
        searchInput.focus();
      }
    });
  }

  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function handleSearch() {
    var query = searchInput.value.trim().toLowerCase();
    if (!query || !searchIndex.length) {
      searchResults.classList.remove('visible');
      searchResults.innerHTML = '';
      return;
    }

    var results = [];
    searchIndex.forEach(function (page) {
      var text = (page.title + ' ' + page.text).toLowerCase();
      var score = 0;

      // Title match bonus
      if (page.title.toLowerCase().indexOf(query) !== -1) score += 10;

      // Content match
      var textIdx = text.indexOf(query);
      if (textIdx !== -1) score += 5;

      // Occurrence count
      var escaped = escapeRegex(query);
      var matches = text.match(new RegExp(escaped, 'g'));
      if (matches) score += Math.min(matches.length, 10);

      if (score > 0) {
        // Extract snippet around first match
        var snippet = '';
        var targetIdx = textIdx > 0 ? textIdx : 0;
        var start = Math.max(0, targetIdx - 40);
        var end = Math.min(text.length, targetIdx + query.length + 80);
        snippet = text.substring(start, end);
        if (start > 0) snippet = '\u2026' + snippet;
        if (end < text.length) snippet = snippet + '\u2026';

        // Highlight matches
        var re = new RegExp('(' + escaped + ')', 'gi');
        snippet = snippet.replace(re, '<mark>$1</mark>');

        results.push({ page: page, score: score, snippet: snippet });
      }
    });

    results.sort(function (a, b) { return b.score - a.score; });
    results = results.slice(0, 10);

    var html = '';
    if (results.length === 0) {
      html = '<div class="search-empty">未找到匹配结果</div>';
    } else {
      results.forEach(function (r) {
        html += '<a class="search-result-item" href="' + r.page.url + '?q=' + encodeURIComponent(query) + '">';
        html += '<div class="search-result-title">' + r.page.title + '</div>';
        html += '<div class="search-result-snippet">' + r.snippet + '</div>';
        html += '</a>';
      });
    }

    searchResults.innerHTML = html;
    searchResults.classList.add('visible');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
