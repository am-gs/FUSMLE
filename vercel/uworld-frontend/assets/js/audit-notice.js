(function () {
  var TARGET_EMAIL = 'nidhitiyyagura@gmail.com';
  var REPORT_URL = '/nidhi-report';
  var TOAST_ID = 'auditNoticeToast';
  var STYLE_ID = 'auditNoticeStyles';

  function getStoredUser() {
    try {
      return JSON.parse(localStorage.getItem('uworldUser') || '{}') || {};
    } catch (e) {
      return {};
    }
  }

  function getUserEmail() {
    var user = getStoredUser();
    return String(user.email || '').trim().toLowerCase();
  }

  function shouldActivate() {
    if (window.location.pathname === REPORT_URL || window.location.pathname === '/nidhi_report.html') {
      return false;
    }
    return getUserEmail() === TARGET_EMAIL;
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = '' +
      '#' + TOAST_ID + '{position:fixed;right:18px;bottom:18px;z-index:99999;width:min(430px,calc(100vw - 24px));background:#0f3a5f;color:#fff;border-radius:14px;box-shadow:0 18px 40px rgba(0,0,0,.26);border:1px solid rgba(255,255,255,.12);overflow:hidden;font-family:"Open Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;opacity:0;transform:translateY(12px) scale(.98);pointer-events:none;transition:opacity .18s ease,transform .18s ease;}' +
      '#' + TOAST_ID + '.audit-show{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}' +
      '#' + TOAST_ID + ' .audit-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;background:linear-gradient(135deg,#1565c0,#0f3a5f);border-bottom:1px solid rgba(255,255,255,.12);}' +
      '#' + TOAST_ID + ' .audit-head strong{font-size:13px;letter-spacing:.02em;}' +
      '#' + TOAST_ID + ' .audit-close{appearance:none;border:none;background:transparent;color:#fff;font-size:18px;line-height:1;cursor:pointer;padding:0 2px;opacity:.85;}' +
      '#' + TOAST_ID + ' .audit-close:hover{opacity:1;}' +
      '#' + TOAST_ID + ' .audit-body{padding:14px;}' +
      '#' + TOAST_ID + ' .audit-body p{margin:0 0 10px 0;font-size:13px;line-height:1.5;color:rgba(255,255,255,.96);}' +
      '#' + TOAST_ID + ' .audit-meta{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px;}' +
      '#' + TOAST_ID + ' .audit-pill{font-size:11px;font-weight:700;padding:5px 8px;border-radius:999px;background:rgba(255,255,255,.12);}' +
      '#' + TOAST_ID + ' .audit-actions{display:flex;gap:10px;flex-wrap:wrap;}' +
      '#' + TOAST_ID + ' .audit-btn{appearance:none;border:none;border-radius:999px;padding:9px 12px;font-size:12px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px;}' +
      '#' + TOAST_ID + ' .audit-btn-primary{background:#fff;color:#0f3a5f;}' +
      '#' + TOAST_ID + ' .audit-btn-secondary{background:rgba(255,255,255,.12);color:#fff;}' +
      '#' + TOAST_ID + ' .audit-foot{padding:0 14px 14px;font-size:11px;color:rgba(255,255,255,.75);line-height:1.4;}' +
      '@media (max-width: 640px){#' + TOAST_ID + '{left:12px;right:12px;bottom:12px;width:auto;}}';
    document.head.appendChild(style);
  }

  function ensureToast() {
    var existing = document.getElementById(TOAST_ID);
    if (existing) return existing;
    ensureStyles();
    var toast = document.createElement('section');
    toast.id = TOAST_ID;
    toast.setAttribute('aria-live', 'polite');
    toast.innerHTML = '' +
      '<div class="audit-head">' +
        '<strong><i class="fas fa-circle-info"></i> Score audit update</strong>' +
        '<button type="button" class="audit-close" aria-label="Dismiss audit notice">×</button>' +
      '</div>' +
      '<div class="audit-body">' +
        '<p>Your <strong>Test 2</strong> was manually re-audited. The automatic scoring path was off, and your corrected result is <strong>52 / 120</strong>.</p>' +
        '<div class="audit-meta">' +
          '<span class="audit-pill">B2 I15: incorrect</span>' +
          '<span class="audit-pill">B2 I16: correct</span>' +
          '<span class="audit-pill">B3 I2: correct</span>' +
        '</div>' +
        '<div class="audit-actions">' +
          '<a class="audit-btn audit-btn-primary" href="' + REPORT_URL + '" target="_blank" rel="noopener">View full audit</a>' +
          '<button type="button" class="audit-btn audit-btn-secondary">Dismiss</button>' +
        '</div>' +
      '</div>' +
      '<div class="audit-foot">This notice appears because we want you to see the corrected audit while you use the app.</div>';
    document.body.appendChild(toast);

    var closeButtons = toast.querySelectorAll('.audit-close, .audit-btn-secondary');
    closeButtons.forEach(function (btn) {
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        hideToast();
      });
    });
    return toast;
  }

  var hideTimer = null;
  function hideToast() {
    var toast = document.getElementById(TOAST_ID);
    if (!toast) return;
    toast.classList.remove('audit-show');
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function showToast() {
    if (!shouldActivate()) return;
    var toast = ensureToast();
    toast.classList.remove('audit-show');
    void toast.offsetWidth;
    toast.classList.add('audit-show');
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(hideToast, 8000);
  }

  function isButtonLike(target) {
    if (!target || !target.closest) return false;
    return !!target.closest('button, input[type="button"], input[type="submit"], input[type="reset"], a.btn, .btn, .fred-icon-btn, .fred-hamburger, [role="button"]');
  }

  document.addEventListener('click', function (event) {
    if (!shouldActivate()) return;
    var target = event.target;
    if (!target) return;
    if (target.closest && target.closest('#' + TOAST_ID)) return;
    if (!isButtonLike(target)) return;
    window.requestAnimationFrame(showToast);
  }, true);
})();
