/* ============================================================
   FitGenie AI — Frontend Logic (Vanilla JS)
   NOTE: This is a pure frontend. All "AI" generation and
   calculations below are LOCAL MOCK IMPLEMENTATIONS that mirror
   the shape of the real FastAPI + OpenAI backend responses
   documented in the architecture blueprint. Replace the
   functions inside `FitGenieAPI` with real `fetch()` calls to
   the backend (e.g. /api/metrics/calculate, /api/workout/generate
   with streaming, /api/chat/stream) when wiring up the server.
   ============================================================ */

(() => {
  'use strict';

  /* ---------------------------------------------------------
     0. STATE (in-memory only — no localStorage per platform rules)
     --------------------------------------------------------- */
  const state = {
    theme: 'light',
    profile: null,       // last submitted assessment data
    metrics: null,       // computed BMI/BMR/TDEE/calories/water
    plan: null,          // generated workout + meal plan
    chatHistory: [],      // [{role:'user'|'assistant', content:''}]
  };

  /* ---------------------------------------------------------
     1. DOM SHORTCUTS
     --------------------------------------------------------- */
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  const views = {
    landing: $('#view-landing'),
    assessment: $('#view-assessment'),
    loading: $('#view-loading'),
    dashboard: $('#view-dashboard'),
  };

  /* ---------------------------------------------------------
     2. VIEW ROUTER
     --------------------------------------------------------- */
  function showView(name) {
    Object.entries(views).forEach(([key, el]) => {
      if (!el) return;
      const active = key === name;
      el.hidden = !active;
      el.setAttribute('aria-hidden', String(!active));
    });

    // The landing-page section links (Features, How It Works, Benefits, FAQ)
    // only make sense on the landing page itself — hide them on every other
    // view, and restore them when the user navigates back to "landing".
    // The logo/brand button is separate and is left untouched.
    const onLanding = name === 'landing';
    const navLinksEl = $('.nav-links');
    const navToggleEl = $('.nav-toggle');
    if (navLinksEl) navLinksEl.classList.toggle('hidden', !onLanding);
    if (navToggleEl) navToggleEl.classList.toggle('hidden', !onLanding);

    window.scrollTo({ top: 0, behavior: 'smooth' });
    // Move focus to the new view heading for a11y
    const heading = views[name] && views[name].querySelector('h1, h2');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus({ preventScroll: true });
    }
    closeMobileNav();
  }
  window.FitGenieNav = { showView };

  /* ---------------------------------------------------------
     3. THEME TOGGLE (Light / Dark) — session only, no storage APIs
     --------------------------------------------------------- */
  const themeToggleBtns = $$('.theme-toggle');
  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    themeToggleBtns.forEach(btn => {
      const icon = btn.querySelector('i');
      if (icon) icon.className = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
      btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    });
  }
  themeToggleBtns.forEach(btn => {
    btn.addEventListener('click', () => applyTheme(state.theme === 'dark' ? 'light' : 'dark'));
  });
  // Respect OS preference on first load
  applyTheme(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

  /* ---------------------------------------------------------
     4. MOBILE NAV
     --------------------------------------------------------- */
  const navToggle = $('.nav-toggle');
  const navLinks = $('.nav-links');
  function closeMobileNav() {
    if (navLinks) navLinks.classList.remove('mobile-open');
    if (navToggle) navToggle.setAttribute('aria-expanded', 'false');
  }
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', () => {
      const open = navLinks.classList.toggle('mobile-open');
      navToggle.setAttribute('aria-expanded', String(open));
    });
  }
  $$('.nav-links a').forEach(a => a.addEventListener('click', closeMobileNav));

  /* ---------------------------------------------------------
     5. FAQ ACCORDION
     --------------------------------------------------------- */
  $$('.faq-item').forEach(item => {
    const btn = $('.faq-q', item);
    btn.addEventListener('click', () => {
      const isOpen = item.getAttribute('data-open') === 'true';
      // close others for a tidy single-open accordion
      $$('.faq-item').forEach(i => { i.setAttribute('data-open', 'false'); $('.faq-q', i).setAttribute('aria-expanded', 'false'); });
      item.setAttribute('data-open', String(!isOpen));
      btn.setAttribute('aria-expanded', String(!isOpen));
    });
  });

  /* ---------------------------------------------------------
     6. NAVIGATION CTA BUTTONS (landing -> assessment, etc.)
     --------------------------------------------------------- */
  $$('[data-nav]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      showView(el.getAttribute('data-nav'));
    });
  });

  /* ---------------------------------------------------------
     7. VITALITY RING (hero signature element) — animate on load
     --------------------------------------------------------- */
  (function animateHeroRing() {
    const circle = $('#heroRingProgress');
    if (!circle) return;
    const radius = circle.r.baseVal.value;
    const circumference = 2 * Math.PI * radius;
    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    circle.style.strokeDashoffset = circumference;
    const targetPct = 0.82; // sample "goal progress" for hero visual only
    requestAnimationFrame(() => {
      circle.style.strokeDashoffset = String(circumference * (1 - targetPct));
    });
  })();

  /* ===========================================================
     8. ASSESSMENT FORM — VALIDATION
     =========================================================== */
  const form = $('#assessmentForm');
  const equipmentGroup = $('#equipmentGroup');
  const locationSelect = $('#workoutLocation');
  const medicalNone = $('#medicalNone');
  const medicalConditions = $('#medicalConditions');
  const daysRange = $('#workoutDays');
  const daysValueOut = $('#workoutDaysValue');

  if (daysRange && daysValueOut) {
    daysRange.addEventListener('input', () => { daysValueOut.textContent = daysRange.value; });
  }

  // Toggle equipment visibility based on location (contextual UX)
  if (locationSelect && equipmentGroup) {
    locationSelect.addEventListener('change', () => {
      equipmentGroup.hidden = locationSelect.value === '';
    });
  }

  // "No medical conditions" checkbox disables textarea
  if (medicalNone && medicalConditions) {
    medicalNone.addEventListener('change', () => {
      medicalConditions.disabled = medicalNone.checked;
      if (medicalNone.checked) medicalConditions.value = '';
    });
  }

  const validators = {
    fullName: v => v.trim().length >= 2 || 'Please enter your full name (at least 2 characters).',
    age: v => (v !== '' && Number(v) >= 13 && Number(v) <= 90) || 'Age must be between 13 and 90.',
    gender: v => v !== '' || 'Please select your gender.',
    heightCm: v => (v !== '' && Number(v) >= 100 && Number(v) <= 250) || 'Height must be between 100–250 cm.',
    weightKg: v => (v !== '' && Number(v) >= 30 && Number(v) <= 300) || 'Weight must be between 30–300 kg.',
    fitnessGoal: v => v !== '' || 'Please select a fitness goal.',
    fitnessLevel: v => v !== '' || 'Please select your fitness level.',
    workoutLocation: v => v !== '' || 'Please select a workout location.',
    workoutDuration: v => v !== '' || 'Please select a preferred duration.',
    dietPreference: v => v !== '' || 'Please select a diet preference.',
  };

  function fieldWrap(el) { return el.closest('.form-field'); }
  function showFieldError(el, message) {
    const wrap = fieldWrap(el);
    if (!wrap) return;
    const err = $('.field-error', wrap);
    if (err) { err.textContent = message; err.classList.add('show'); }
    el.setAttribute('aria-invalid', 'true');
  }
  function clearFieldError(el) {
    const wrap = fieldWrap(el);
    if (!wrap) return;
    const err = $('.field-error', wrap);
    if (err) { err.classList.remove('show'); err.textContent = ''; }
    el.removeAttribute('aria-invalid');
  }

  function validateForm(data) {
    let firstInvalid = null;
    let valid = true;
    Object.entries(validators).forEach(([name, fn]) => {
      const el = form.elements[name];
      if (!el) return;
      const result = fn(data[name] ?? '');
      if (result !== true) {
        valid = false;
        showFieldError(el, result);
        if (!firstInvalid) firstInvalid = el;
      } else {
        clearFieldError(el);
      }
    });
    return { valid, firstInvalid };
  }

  const formErrorBanner = $('#formErrorBanner');
  function showFormBanner(message) {
    if (!formErrorBanner) return;
    $('#formErrorText', formErrorBanner).textContent = message;
    formErrorBanner.hidden = false;
    formErrorBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function hideFormBanner() { if (formErrorBanner) formErrorBanner.hidden = true; }
  $('#dismissFormError')?.addEventListener('click', hideFormBanner);

  // live-clear errors as user types/selects
  if (form) {
    form.addEventListener('input', (e) => {
      if (validators[e.target.name]) clearFieldError(e.target);
    });
    form.addEventListener('change', (e) => {
      if (validators[e.target.name]) clearFieldError(e.target);
    });
  }

  function collectFormData() {
    const fd = new FormData(form);
    const equipment = fd.getAll('equipment');
    return {
      fullName: (fd.get('fullName') || '').toString(),
      age: fd.get('age'),
      gender: fd.get('gender'),
      heightCm: fd.get('heightCm'),
      weightKg: fd.get('weightKg'),
      fitnessGoal: fd.get('fitnessGoal'),
      fitnessLevel: fd.get('fitnessLevel'),
      workoutLocation: fd.get('workoutLocation'),
      equipment,
      workoutDuration: fd.get('workoutDuration'),
      workoutDays: fd.get('workoutDays'),
      dietPreference: fd.get('dietPreference'),
      allergies: (fd.get('allergies') || '').toString(),
      medicalNone: fd.get('medicalNone') === 'on',
      medicalConditions: (fd.get('medicalConditions') || '').toString(),
    };
  }

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      hideFormBanner();
      const data = collectFormData();
      const { valid, firstInvalid } = validateForm(data);
      if (!valid) {
        showFormBanner('Please fix the highlighted fields before continuing. All required fields must be completed accurately for FitGenie to generate a safe, personalized plan.');
        firstInvalid && firstInvalid.focus();
        return;
      }
      state.profile = data;
      runGenerationSequence(data);
    });
  }

  /* ===========================================================
     9. BACKEND INTEGRATION (FastAPI + Gemini, via SSE)
     =========================================================== */
  // Base URL of your FastAPI backend (uvicorn). Update this if your
  // backend runs on a different host/port.
  const API_BASE_URL = 'http://localhost:8000';

  const MOTIVATIONS = [
    'Discipline is choosing between what you want now and what you want most.',
    'Small consistent steps beat occasional giant leaps. Show up today.',
    'Your body can stand almost anything. It\u2019s your mind you have to convince.',
    'Progress, not perfection — every rep counts.',
    'The only bad workout is the one that didn\u2019t happen.',
    'Fuel your body like you actually love it, because you do.',
  ];

  /**
   * Consume a Server-Sent Events (SSE) POST response from the backend.
   * FastAPI's StreamingResponse sends frames shaped like:
   *   event: <name>\ndata: <json>\n\n
   * `handlers` maps event names to callback functions receiving the
   * parsed JSON payload (or raw string if parsing fails).
   */
  async function consumeSSE(url, payload, handlers) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
      let detail = `Server responded with ${response.status}`;
      try {
        const errJson = await response.json();
        detail = errJson?.error?.message || detail;
      } catch (_) { /* response wasn't JSON — keep default detail */ }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let frameEnd;
      while ((frameEnd = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        if (!frame.trim()) continue;

        const eventMatch = frame.match(/^event:\s*(.+)$/m);
        const dataMatch = frame.match(/^data:\s*(.+)$/m);
        const eventName = eventMatch ? eventMatch[1].trim() : 'message';
        const dataRaw = dataMatch ? dataMatch[1] : '';

        let parsed = dataRaw;
        try { parsed = JSON.parse(dataRaw); } catch (_) { /* keep raw string */ }

        if (typeof handlers[eventName] === 'function') handlers[eventName](parsed);
      }
    }
  }

  /** Map the frontend's camelCase assessment data to the backend's snake_case UserProfile schema. */
  function mapProfileToBackend(data) {
    return {
      full_name: data.fullName,
      age: Number(data.age),
      gender: data.gender,
      height_cm: Number(data.heightCm),
      weight_kg: Number(data.weightKg),
      fitness_goal: data.fitnessGoal,
      fitness_level: data.fitnessLevel,
      workout_location: data.workoutLocation,
      equipment: (data.equipment && data.equipment.length) ? data.equipment : ['none'],
      workout_duration: Number(data.workoutDuration),
      workout_days: Number(data.workoutDays),
      diet_preference: data.dietPreference,
      allergies: data.allergies ? data.allergies : null,
      medical_conditions: data.medicalNone ? null : (data.medicalConditions || null),
    };
  }

  /**
   * Call POST /api/generate-plan and resolve once the stream completes with
   * the deterministic metrics payload plus the full AI-generated plan text.
   */
  function requestPlanFromBackend(data) {
    return new Promise((resolve, reject) => {
      let metrics = null;
      let planText = '';
      let settledByEvent = false;

      consumeSSE(`${API_BASE_URL}/api/generate-plan`, { user: mapProfileToBackend(data) }, {
        metrics: (payload) => { metrics = payload; },
        plan_chunk: (payload) => { planText += (payload && payload.text) || ''; },
        error: (payload) => {
          settledByEvent = true;
          reject(new Error((payload && payload.message) || 'AI plan generation failed.'));
        },
        done: () => {
          settledByEvent = true;
          resolve({ metrics, planText });
        },
      }).catch((err) => {
        if (!settledByEvent) reject(err);
      });
    });
  }

  /** Extract a top-level "## Section Title" block (up to the next "## ") from AI markdown. */
  function extractSection(markdown, title) {
    const re = new RegExp(`##\\s*${title}[\\s\\S]*?(?=\\n##\\s|$)`, 'i');
    const match = markdown.match(re);
    return match ? match[0].trim() : '';
  }

  /**
   * Parse the AI-generated markdown (see prompt_builder.py's output_format)
   * into structured data the dashboard cards can render:
   *   { workoutDays: [{title, exercises: [...]}], meals: [{title, content}], safetyNote }
   */
  function parsePlanMarkdown(fullText) {
    const workoutRaw = extractSection(fullText, 'Workout Plan');
    const mealRaw = extractSection(fullText, 'Meal Plan');
    const safetyRaw = extractSection(fullText, 'Safety Note');

    const parseBlocks = (raw) => raw
      .split(/\n(?=###\s)/)
      .filter((b) => /^###\s/.test(b.trim()))
      .map((block) => {
        const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
        const title = lines[0].replace(/^###\s*/, '');
        const bodyLines = lines.slice(1);
        return { title, bodyLines };
      });

    const workoutDays = parseBlocks(workoutRaw).map(({ title, bodyLines }) => ({
      title,
      exercises: bodyLines.filter((l) => l.startsWith('-')).map((l) => l.replace(/^-\s*/, '')),
    }));

    const meals = parseBlocks(mealRaw).map(({ title, bodyLines }) => ({
      title,
      content: bodyLines.join(' ').replace(/^-\s*/, ''),
    }));

    const safetyNote = safetyRaw.replace(/^##\s*Safety Note\s*/i, '').trim();

    return { workoutDays, meals, safetyNote, rawWorkout: workoutRaw, rawMeal: `${mealRaw}\n\n${safetyRaw}`.trim() };
  }

  /* ===========================================================
     10. PREMIUM LOADING SEQUENCE
     =========================================================== */
  const LOADING_MESSAGES = [
    'Analyzing your fitness profile...',
    'Calculating BMI...',
    'Understanding your goals...',
    'Creating your workout...',
    'Preparing meal plan...',
    'Generating AI recommendations...',
    'Almost Ready...',
  ];
  const loadingMsgEl = $('#loadingMessage');
  const loadingBarFill = $('#loadingBarFill');
  const loadingStepsEl = $('#loadingSteps');


  function buildLoadingChips() {
    if (!loadingStepsEl) return;
      loadingStepsEl.innerHTML = LOADING_MESSAGES.map((m, i) =>
      `<span data-step="${i}">${m.replace('...', '')}</span>`).join('');
  
  }

  function runGenerationSequence(data) {
    buildLoadingChips();
    showView('loading');
    if (loadingBarFill) loadingBarFill.style.width = '0%';

    // Cycle the loading messages/progress bar independently of the network
    // request so the premium loading experience keeps moving even if the
    // AI takes a little while to respond. It simply stops advancing past
    // the last message until the real request resolves.
    let step = 0;
    const totalSteps = LOADING_MESSAGES.length;
    const cycle = setInterval(() => {
      if (loadingMsgEl) loadingMsgEl.textContent = LOADING_MESSAGES[Math.min(step, totalSteps - 1)];
      if (loadingBarFill) {
        loadingBarFill.style.width = `${Math.round((Math.min(step + 1, totalSteps) / totalSteps) * 100)}%`;
      }
      const chip = loadingStepsEl && loadingStepsEl.querySelector(`[data-step="${Math.min(step, totalSteps - 1)}"]`);
      if (chip) chip.classList.add('done');
      if (step < totalSteps) step++;
    }, 750);

    requestPlanFromBackend(data)
      .then(({ metrics, planText }) => {
        clearInterval(cycle);
        if (!metrics) throw new Error('The server did not return your metrics. Please try again.');
        const parsedPlan = parsePlanMarkdown(planText);
        state.metrics = metrics;
        state.plan = parsedPlan;
        populateDashboard(data, metrics, parsedPlan);
        showView('dashboard');
        showToast('Your personalized plan is ready!', 'fa-solid fa-circle-check');
      })
      .catch((err) => {
        clearInterval(cycle);
        renderGenerationError(err && err.message ? err.message : null);
      });
  }

  function renderGenerationError(detail) {
    showView('assessment');
    const base = 'Something went wrong while generating your plan.';
    const hint = detail
      ? ` ${detail}`
      : ' Please make sure the FitGenie backend is running and reachable, then try again.';
    showFormBanner(`${base}${hint} Your answers have been kept.`);
  }

  /* ===========================================================
     11. DASHBOARD POPULATION
     =========================================================== */
  function populateDashboard(data, metrics, plan) {
    $('#dashUserName').textContent = data.fullName.split(' ')[0] || 'there';

    // BMI card
    const bmi = metrics.bmi_info.bmi;
    $('#bmiValue').textContent = bmi;
    const tagEl = $('#bmiTag');
    tagEl.textContent = metrics.bmi_info.category;
    tagEl.style.background = 'var(--brand-soft)';
    tagEl.style.color = 'var(--brand-strong)';
    const marker = $('#bmiMarker');
    const pct = Math.min(100, Math.max(0, ((bmi - 15) / (35 - 15)) * 100));
    marker.style.left = `calc(${pct}% - 1px)`;

    // Calories card
    $('#calorieValue').textContent = metrics.calorie_recommendation.toLocaleString();
    $('#macroProtein').textContent = `${metrics.macros.protein} g`;
    $('#macroCarbs').textContent = `${metrics.macros.carbs} g`;
    $('#macroFat').textContent = `${metrics.macros.fat} g`;
    $('#tdeeValue').textContent = metrics.tdee.toLocaleString();

    // Water card
    const liters = (metrics.water_intake_ml / 1000).toFixed(1);
    $('#waterValue').textContent = `${liters} L`;
    const glassFill = $('#glassFill');
    requestAnimationFrame(() => { glassFill.style.height = '78%'; });

    // Workout preview (first 3 days)
    const workoutPreview = $('#workoutPreview');
    workoutPreview.innerHTML = plan.workoutDays.slice(0, 3).map(d => `
      <div class="plan-row">
        <div><strong>${escapeHtmlPlain(d.title)}</strong><br><span>${d.exercises.length} exercise${d.exercises.length === 1 ? '' : 's'}</span></div>
        <span class="tag">${data.workoutDuration} min</span>
      </div>`).join('') || '<p class="hint">No workout plan was returned. Try generating again.</p>';

    // Meal preview
    const mealPreview = $('#mealPreview');
    mealPreview.innerHTML = plan.meals.map(m => `
      <div class="plan-row">
        <div><strong>${escapeHtmlPlain(m.title)}</strong><br><span>${escapeHtmlPlain(m.content)}</span></div>
      </div>`).join('') || '<p class="hint">No meal plan was returned. Try generating again.</p>';

    // Motivation — seed with the backend's motivation line for this plan
    $('#motivationText').textContent = `"${metrics.motivation}"`;

    // Store full plan for modal
    state.fullWorkoutHtml = plan.workoutDays.map(d => `
      <h4>${escapeHtmlPlain(d.title)}</h4>
      <ul>${d.exercises.map(e => `<li>${escapeHtmlPlain(e)}</li>`).join('')}</ul>
    `).join('') || '<p>No workout plan was returned.</p>';
    state.fullMealHtml = `
      <ul>${plan.meals.map(m => `<li><strong>${escapeHtmlPlain(m.title)}:</strong> ${escapeHtmlPlain(m.content)}</li>`).join('')}</ul>
      ${plan.safetyNote ? `<h4>Safety Note</h4><p>${escapeHtmlPlain(plan.safetyNote)}</p>` : ''}
    ` || '<p>No meal plan was returned.</p>';

    // Chat: seed system context (not shown), reset visible history
    state.chatHistory = [];
    $('#chatMessages').innerHTML = '';
    appendChatMessage('assistant', `Hi ${data.fullName.split(' ')[0] || ''}! I'm your FitGenie AI assistant. I can see your profile — goal: **${labelize(data.fitnessGoal)}**, target: **${metrics.calorie_recommendation} kcal/day**. Ask me anything about your plan!`);
  }

  function escapeHtmlPlain(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function setRandomMotivation() {
    const quote = MOTIVATIONS[Math.floor(Math.random() * MOTIVATIONS.length)];
    $('#motivationText').textContent = `"${quote}"`;
  }
  $('#refreshMotivation')?.addEventListener('click', setRandomMotivation);

  function labelize(v) {
    if (!v) return '';
    return v.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  /* ---------------------------------------------------------
     13. DASHBOARD ACTIONS
     --------------------------------------------------------- */
  $('#btnGenerateNew')?.addEventListener('click', () => {
    showView('assessment');
  });

  $('#btnDownloadPlan')?.addEventListener('click', () => {
    showToast('Download requires backend PDF export — coming soon.', 'fa-solid fa-circle-info');
  });

  $('#btnAskAI')?.addEventListener('click', () => {
    $('#chatCard')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    $('#chatInput')?.focus();
  });

  // Modal handling
  const modalOverlay = $('#planModal');
  function openModal(title, bodyHtml) {
    $('#modalTitle').textContent = title;
    $('#modalBody').innerHTML = bodyHtml;
    modalOverlay.hidden = false;
    $('.modal-close', modalOverlay).focus();
    document.addEventListener('keydown', escCloseModal);
  }
  function closeModal() {
    modalOverlay.hidden = true;
    document.removeEventListener('keydown', escCloseModal);
  }
  function escCloseModal(e) { if (e.key === 'Escape') closeModal(); }
  $('#viewFullWorkout')?.addEventListener('click', () => openModal('Your Full Workout Plan', state.fullWorkoutHtml || ''));
  $('#viewFullMeal')?.addEventListener('click', () => openModal('Your Full Meal Plan', state.fullMealHtml || ''));
  $$('[data-close-modal]').forEach(el => el.addEventListener('click', closeModal));
  modalOverlay?.addEventListener('click', (e) => { if (e.target === modalOverlay) closeModal(); });

  /* ---------------------------------------------------------
     14. TOAST
     --------------------------------------------------------- */
  let toastTimer = null;
  function showToast(message, iconClass = 'fa-solid fa-circle-check') {
    const toast = $('#toast');
    if (!toast) return;
    $('#toastText', toast).textContent = message;
    $('#toastIcon', toast).className = iconClass;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
  }

  /* ===========================================================
     15. AI CHAT ASSISTANT (embedded) — streaming simulation
     =========================================================== */
  const chatMessages = $('#chatMessages');
  const chatForm = $('#chatForm');
  const chatInput = $('#chatInput');
  const chatSendBtn = $('#chatSendBtn');

  // Very small markdown-ish renderer: **bold**, bullet lines starting with "- "
  function renderMarkdownLite(text) {
    const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let safe = escapeHtml(text);
    // bold
    safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // bullet lists
    const lines = safe.split('\n');
    let html = '';
    let inList = false;
    lines.forEach(line => {
      if (/^\s*-\s+/.test(line)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${line.replace(/^\s*-\s+/, '')}</li>`;
      } else {
        if (inList) { html += '</ul>'; inList = false; }
        if (line.trim() !== '') html += `<p>${line}</p>`;
      }
    });
    if (inList) html += '</ul>';
    return html || `<p></p>`;
  }

  function appendChatMessage(role, text) {
    const wrap = document.createElement('div');
    wrap.className = `msg ${role === 'user' ? 'user' : 'assistant'}`;
    wrap.innerHTML = `
      <div class="msg-avatar">${role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-sparkles"></i>'}</div>
      <div class="msg-bubble">${renderMarkdownLite(text)}</div>
    `;
    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    state.chatHistory.push({ role, content: text });
    return wrap;
  }

  function appendTypingIndicator() {
    const wrap = document.createElement('div');
    wrap.className = 'msg assistant';
    wrap.id = 'typingIndicator';
    wrap.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-sparkles"></i></div>
      <div class="msg-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>
    `;
    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return wrap;
  }

  /**
   * Stream a live reply from POST /api/chat, appending tokens to a bubble
   * as they arrive (real backend streaming, not a simulated typing effect).
   */
  function streamAssistantReplyFromBackend(userText, typingIndicatorEl) {
    const bubbleWrap = document.createElement('div');
    bubbleWrap.className = 'msg assistant';
    bubbleWrap.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-sparkles"></i></div>
      <div class="msg-bubble"><span class="stream-target"></span><span class="cursor-blink"></span></div>
    `;

    let accumulated = '';
    let bubbleInserted = false;
    const insertBubble = () => {
      if (bubbleInserted) return;
      if (typingIndicatorEl && typingIndicatorEl.parentNode) typingIndicatorEl.remove();
      chatMessages.appendChild(bubbleWrap);
      bubbleInserted = true;
    };

    const target = () => $('.stream-target', bubbleWrap);
    const cursor = () => $('.cursor-blink', bubbleWrap);

    const payload = {
      user: mapProfileToBackend(state.profile || {}),
      workout_plan: (state.plan && state.plan.rawWorkout) || null,
      meal_plan: (state.plan && state.plan.rawMeal) || null,
      message: userText,
      // Exclude the just-appended current turn (already sent as `message`
      // above) so the backend doesn't see it duplicated in history.
      history: state.chatHistory.slice(0, -1).slice(-10),
    };

    consumeSSE(`${API_BASE_URL}/api/chat`, payload, {
      message_chunk: (chunk) => {
        insertBubble();
        accumulated += (chunk && chunk.text) || '';
        const t = target();
        if (t) t.innerHTML = renderMarkdownLite(accumulated).replace(/^<p>|<\/p>$/g, '');
        chatMessages.scrollTop = chatMessages.scrollHeight;
      },
      error: (payload) => {
        insertBubble();
        const c = cursor();
        if (c) c.remove();
        const bubble = $('.msg-bubble', bubbleWrap);
        if (bubble) {
          bubble.style.borderColor = 'var(--danger-500)';
          bubble.innerHTML = `<p><strong>Connection hiccup.</strong> ${escapeHtmlPlain((payload && payload.message) || "I couldn't reach the AI service just now.")} Please try again.</p>`;
        }
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
      },
      done: () => {
        if (!bubbleInserted) {
          // No content ever arrived — surface a gentle fallback message.
          insertBubble();
          accumulated = "I didn't get a response that time — please try asking again.";
        }
        const c = cursor();
        if (c) c.remove();
        const bubble = $('.msg-bubble', bubbleWrap);
        if (bubble) bubble.innerHTML = renderMarkdownLite(accumulated);
        state.chatHistory.push({ role: 'assistant', content: accumulated });
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
      },
    }).catch((err) => {
      insertBubble();
      const c = cursor();
      if (c) c.remove();
      const bubble = $('.msg-bubble', bubbleWrap);
      if (bubble) {
        bubble.style.borderColor = 'var(--danger-500)';
        bubble.innerHTML = `<p><strong>Connection hiccup.</strong> ${escapeHtmlPlain(err.message || 'Could not reach the FitGenie backend.')} Please make sure the backend is running and try again.</p>`;
      }
      chatSendBtn.disabled = false;
      chatInput.disabled = false;
    });
  }

  function handleSendMessage(text) {
    if (!text.trim()) return;
    if (!state.profile || !state.metrics) {
      appendChatMessage('assistant', 'Please complete your fitness assessment first so I can give you personalized guidance!');
      return;
    }
    appendChatMessage('user', text.trim());
    chatInput.value = '';
    chatSendBtn.disabled = true;
    chatInput.disabled = true;

    const typing = appendTypingIndicator();
    streamAssistantReplyFromBackend(text.trim(), typing);
  }

  if (chatForm) {
    chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      handleSendMessage(chatInput.value);
    });
  }
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage(chatInput.value);
      }
    });
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(120, chatInput.scrollHeight) + 'px';
    });
  }
  $$('.chip').forEach(chip => {
    chip.addEventListener('click', () => handleSendMessage(chip.textContent));
  });

  /* ---------------------------------------------------------
     16. Footer year
     --------------------------------------------------------- */
  const yearEl = $('#currentYear');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

})();
