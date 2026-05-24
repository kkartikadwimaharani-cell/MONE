// Ghost ID Scanner - Auto-scan on page load
(function() {
  'use strict';

  var loadingEl = document.getElementById('ghostScannerLoading');
  var loadingText = document.getElementById('ghostLoadingText');
  var resultsEl = document.getElementById('ghostScannerResults');

  var messages = [
    'Scanning identity...',
    'Checking VPN tunnel...',
    'Analyzing fingerprint...'
  ];

  function showMessages(index) {
    if (index >= messages.length) {
      fetchGhostScan();
      return;
    }
    loadingText.innerHTML = messages[index] + '<span class="ghost-blink-dots">...</span>';
    setTimeout(function() {
      showMessages(index + 1);
    }, 800);
  }

  function fetchGhostScan() {
    fetch('/api/ghost-scan')
      .then(function(res) { return res.json(); })
      .then(function(data) {
        document.getElementById('ghostIp').textContent = data.ip || '-';
        document.getElementById('ghostCountry').textContent = data.country || '-';
        document.getElementById('ghostBrowser').textContent = data.browser || '-';
        document.getElementById('ghostLanguage').textContent = data.language || '-';
        document.getElementById('ghostVpn').textContent = data.vpn_status || '-';
        document.getElementById('ghostRisk').textContent = data.risk_level || '-';
        document.getElementById('ghostMode').textContent = data.scan_mode || '-';

        // Highlight risk level
        var riskEl = document.getElementById('ghostRisk');
        if (data.risk_level === 'HIGH') {
          riskEl.classList.add('ghost-risk-high');
        } else if (data.risk_level === 'LOW') {
          riskEl.classList.add('ghost-risk-low');
        }

        loadingEl.style.display = 'none';
        resultsEl.style.display = 'block';
      })
      .catch(function() {
        loadingText.innerHTML = 'Scan Failed<span class="ghost-blink-dots">...</span>';
        loadingText.style.color = '#ff4444';
      });
  }

  document.addEventListener('DOMContentLoaded', function() {
    showMessages(0);
  });
})();
