// Interactive Bayesian Confidence Breakdown Modal

window.ConfidenceModal = {
  show: function(hypothesis) {
    if (!hypothesis) return;

    let modalEl = document.getElementById('confidence-modal');
    if (!modalEl) {
      modalEl = document.createElement('div');
      modalEl.id = 'confidence-modal';
      modalEl.className = 'fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden';
      document.body.appendChild(modalEl);
    }

    const prior = hypothesis.prior || 0.20;
    const posterior = hypothesis.confidence || 0.0;
    const evidenceList = hypothesis.evidence || [];

    let evidenceRows = evidenceList.map(e => `
      <tr class="border-b border-gray-800 text-xs">
        <td class="py-2 px-3 font-mono text-cyan-400">${e.id}</td>
        <td class="py-2 px-3 text-gray-300">${e.text}</td>
        <td class="py-2 px-3 text-right font-mono ${e.lr >= 1.0 ? 'text-emerald-400' : 'text-rose-400'}">
          ${e.lr}x
        </td>
      </tr>
    `).join('');

    modalEl.innerHTML = `
      <div class="bg-gray-900 border border-gray-700 rounded-xl max-w-2xl w-full p-6 shadow-2xl relative text-left">
        <button onclick="document.getElementById('confidence-modal').classList.add('hidden')" 
                class="absolute top-4 right-4 text-gray-400 hover:text-white font-bold text-lg">&times;</button>
        
        <h3 class="text-xl font-bold text-white mb-1">Bayesian Multiplication Breakdown</h3>
        <p class="text-xs text-gray-400 mb-4">${hypothesis.name} (${hypothesis.id})</p>

        <div class="grid grid-cols-3 gap-3 mb-6 bg-gray-950 p-4 rounded-lg border border-gray-800 text-center">
          <div>
            <div class="text-xs text-gray-400">Prior Odds</div>
            <div class="text-lg font-mono font-bold text-blue-400">${(prior * 100).toFixed(0)}%</div>
          </div>
          <div class="flex items-center justify-center text-gray-500 font-bold">&rarr;</div>
          <div>
            <div class="text-xs text-gray-400">Posterior Confidence</div>
            <div class="text-lg font-mono font-bold text-emerald-400">${(posterior * 100).toFixed(1)}%</div>
          </div>
        </div>

        <h4 class="text-sm font-semibold text-gray-200 mb-2">Likelihood Ratio (LR) Trail</h4>
        <div class="max-h-60 overflow-y-auto border border-gray-800 rounded-lg">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-gray-800/50 text-xs text-gray-400 uppercase">
                <th class="py-2 px-3">ID</th>
                <th class="py-2 px-3">Evidence Observation</th>
                <th class="py-2 px-3 text-right">LR Multiplier</th>
              </tr>
            </thead>
            <tbody>
              ${evidenceRows || '<tr><td colspan="3" class="p-3 text-center text-xs text-gray-500">No evidence items recorded</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;

    modalEl.classList.remove('hidden');
  }
};