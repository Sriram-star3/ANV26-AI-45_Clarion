// FinOps & Business View Transformer

window.FinOpsEngine = {
  isFinOpsActive: false,

  // Revenue estimation formula based on metric drop percentage
  calculateFinancialRisk: function(dropPct) {
    if (!dropPct) return "₹0 / hr";
    // Base estimation formula: 1% drop ~ ₹15,000/hr risk
    const hourlyRiskInINR = Math.round(dropPct * 15000);
    if (hourlyRiskInINR >= 100000) {
      return `₹${(hourlyRiskInINR / 100000).toFixed(1)}L / hr`;
    }
    return `₹${hourlyRiskInINR.toLocaleString('en-IN')} / hr`;
  },

  // Technical terminology to Business terminology mapper
  labelMap: {
    "Batching DB-Lock Deadlock": "Checkout Bottleneck (DB Contention)",
    "Payment Gateway Outage": "Payment Vendor Interruption",
    "Redis Cache Exhaustion": "Inventory Stockout Risk",
    "DB Lock Contention": "Checkout Bottleneck",
    "payment_502_count": "Failed Checkout Transactions",
    "SUPPRESSED_NOISE": "SUPPRESSED SYMPTOM",
    "ROOT_CAUSE": "PRIMARY BUSINESS IMPACT"
  },

  getBusinessLabel: function(technicalText) {
    return this.labelMap[technicalText] || technicalText;
  },

  toggleView: function(enableFinOps) {
    this.isFinOpsActive = enableFinOps;
    const bodyEl = document.body;
    
    if (enableFinOps) {
      bodyEl.classList.add('finops-mode');
    } else {
      bodyEl.classList.remove('finops-mode');
    }

    // Trigger UI re-render event
    window.dispatchEvent(new CustomEvent('clarion:view-toggled', { 
      detail: { isFinOps: enableFinOps } 
    }));
  }
};