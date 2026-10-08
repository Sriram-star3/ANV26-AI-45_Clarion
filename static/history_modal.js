// Past Incident History Side Drawer

window.HistoryDrawer = {
  isOpen: false,

  toggle: function() {
    this.isOpen = !this.isOpen;
    let drawerEl = document.getElementById('history-drawer');
    if (!drawerEl) {
      drawerEl = this.createDrawer();
    }

    if (this.isOpen) {
      drawerEl.classList.remove('translate-x-full');
      this.fetchHistory();
    } else {
      drawerEl.classList.add('translate-x-full');
    }
  },

  createDrawer: function() {
    const drawer = document.createElement('div');
    drawer.id = 'history-drawer';
    drawer.className = 'fixed top-0 right-0 h-full w-96 bg-gray-900 border-l border-gray-800 shadow-2xl z-40 transition-transform duration-300 transform translate-x-full flex flex-col p-6 text-left';
    
    drawer.innerHTML = `
      <div class="flex justify-between items-center mb-4 border-b border-gray-800 pb-3">
        <h3 class="text-lg font-bold text-white">Past Incident History</h3>
        <button onclick="window.HistoryDrawer.toggle()" class="text-gray-400 hover:text-white font-bold">&times;</button>
      </div>

      <input type="text" id="history-search" placeholder="Search dossier ID or cause..." 
             oninput="window.HistoryDrawer.filter(this.value)"
             class="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-xs text-white mb-4 focus:outline-none focus:border-cyan-500">

      <div id="history-list" class="flex-1 overflow-y-auto space-y-3">
        <div class="text-xs text-gray-500 text-center py-8">Loading history...</div>
      </div>
    `;

    document.body.appendChild(drawer);
    return drawer;
  },

  fetchHistory: async function() {
    const listEl = document.getElementById('history-list');
    try {
      const res = await fetch('/api/v1/history');
      if (!res.ok) throw new Error("History API endpoint offline");
      const data = await res.json();
      
      this.cache = data.history || [];
      this.renderList(this.cache);
    } catch (e) {
      listEl.innerHTML = `<div class="text-xs text-rose-400 text-center py-8">Backend history endpoint not ready.</div>`;
    }
  },

  renderList: function(items) {
    const listEl = document.getElementById('history-list');
    if (!items.length) {
      listEl.innerHTML = `<div class="text-xs text-gray-500 text-center py-8">No incident history recorded yet.</div>`;
      return;
    }

    listEl.innerHTML = items.map(item => `
      <div class="bg-gray-950 border border-gray-800 rounded p-3 hover:border-gray-700 transition">
        <div class="flex justify-between items-start mb-1">
          <span class="font-mono text-xs text-cyan-400 font-bold">${item.dossier_id}</span>
          <span class="text-[10px] text-gray-500">${item.timestamp || 'Recent'}</span>
        </div>
        <div class="text-xs font-semibold text-white mb-1">${item.root_cause}</div>
        <div class="text-[10px] text-emerald-400 font-mono">Confidence: ${(item.confidence * 100).toFixed(1)}%</div>
      </div>
    `).join('');
  },

  filter: function(query) {
    if (!this.cache) return;
    const q = query.toLowerCase();
    const filtered = this.cache.filter(i => 
      i.dossier_id.toLowerCase().includes(q) || 
      i.root_cause.toLowerCase().includes(q)
    );
    this.renderList(filtered);
  }
};