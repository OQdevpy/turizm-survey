// ============================================
// Inbound survey logic (EN/RU) — Django backend
// 2026 versiya — yangilangan (96 davlat, yangi buildSeq, shopping olib tashlangan)
// ============================================
(function () {
  'use strict';

  var CFG = window.SURVEY_CONFIG || {};
  var currentLang = 'en';
  var currentQIdx = 0;
  // GLOBAL — inline oninput="answers.X=Y" handler'lar global scope'da ishlaydi,
  // shuning uchun window.answers va lokal answers SHU SHU obyektga ishora qilishi kerak.
  window.answers = window.answers || {};
  var answers = window.answers;
  var submitted = false;

  // ============ SESSION STORAGE (avto-saqlash) ============
  // Sahifa yangilansa — savol va javoblar saqlanadi
  // Faqat sahifa yopilganda yo'qoladi (sessionStorage)
  var STORAGE_KEY = 'tourism_inbound_state_v1';

  function saveState() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentQIdx: currentQIdx,
        currentLang: currentLang,
        answers: answers,
        page: 'survey',
      }));
    } catch (e) { /* sessionStorage to'la yoki bloklangan — sukutda */ }
  }
  function loadState() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) { return null; }
  }
  function clearState() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
  }
  // Global tarzda — har inline oninput dan ham chaqirib bo'ladi
  window.__inboundSave = saveState;

  function resetAnswers() {
    Object.keys(answers).forEach(function (k) { delete answers[k]; });
  }

  // ==================== DATA ====================
  var COUNTRIES = [
    'Afghanistan','Albania','Algeria','Argentina','Armenia','Australia','Austria','Azerbaijan',
    'Bahrain','Bangladesh','Belarus','Belgium','Brazil','Bulgaria','Canada','Chile','China',
    'Colombia','Croatia','Cuba','Cyprus','Czech Republic','Denmark','Egypt','Estonia','Ethiopia',
    'Finland','France','Georgia','Germany','Ghana','Greece','Hungary','India','Indonesia',
    'Iran','Iraq','Ireland','Israel','Italy','Japan','Jordan','Kazakhstan','Kenya','Kuwait',
    'Kyrgyzstan','Latvia','Lebanon','Lithuania','Malaysia','Mexico','Moldova','Mongolia',
    'Morocco','Netherlands','New Zealand','Nigeria','North Korea','Norway','Oman','Pakistan',
    'Palestine','Philippines','Poland','Portugal','Qatar','Romania','Russia','Saudi Arabia',
    'Serbia','Singapore','Slovakia','Slovenia','South Africa','South Korea','Spain','Sri Lanka',
    'Sweden','Switzerland','Syria','Taiwan','Tajikistan','Thailand','Tunisia','Turkey',
    'Turkmenistan','UAE','Ukraine','United Kingdom','United States','Uzbekistan',
    'Venezuela','Vietnam','Yemen','Other'
  ];
  var CURRENCIES = ['USD','EUR','UZS','RUB','GBP','CNY','KZT','CHF','JPY','AED','Other'];
  var PLACES_EN = ['Tashkent','Samarkand','Bukhara','Khiva','Shakhrisabz','Termez','Kokand','Fergana','Namangan','Andijan','Nukus','Urgench','Other'];
  var PLACES_RU = ['Ташкент','Самарканд','Бухара','Хива','Шахрисабз','Термез','Коканд','Фергана','Наманган','Андижан','Нукус','Ургенч','Другое'];

  var EXP_ROWS = [
    {n:1, en:'Accommodation (payment only for the room)', ru:'Проживание (оплата только за номер)'},
    {n:2, en:'Food and drinks', ru:'Еда и напитки'},
    {n:3, en:'International transportation', ru:'Международный транспорт'},
    {n:4, en:'Transport (only within Uzbekistan)', ru:'Транспорт (только в пределах Узбекистана)'},
    {n:5, en:'Cultural services (entrance fees to museums, performances, films)', ru:'Культурные услуги (входные билеты, музеи, спектакли)'},
    {n:6, en:'Sport services, entertainment and recreation', ru:'Спортивные услуги, развлечения и отдых'},
    {n:7, en:'Educational expenses', ru:'Расходы на образование'},
    {n:8, en:'Tourism services within Uzbekistan (additional package tours)', ru:'Туристические услуги внутри Узбекистана (доп. турпакеты)'},
    {n:9, en:'Medical services (sanatoriums, health resorts)', ru:'Медицинские услуги (санатории, курорты)'},
    {n:10, en:'Fueling and maintenance of own motor transport', ru:'Топливо и обслуживание личного автотранспорта'},
    {n:11, en:'Purchasing of valuables (precious metals, stones, jewelry, art)', ru:'Покупка ценностей (драгметаллы, камни, ювелирка, искусство)'},
    {n:12, en:'Shops (souvenirs, clothes, other consumer goods)', ru:'Магазины (сувениры, одежда, потребительские товары)'},
    {n:13, en:'The value of goods purchased for resale abroad', ru:'Стоимость товаров, купленных для перепродажи за рубежом', mand:true},
    {n:14, en:'Other expenses', ru:'Прочие расходы'}
  ];

  var RATING_EN = [
    'International transport (Uzbek companies)',
    'Passport control procedures at border crossing points',
    'Hospitality',
    'Value for money',
    'Food',
    'Cleanliness',
    'Transport (within Uzbekistan)',
    'Safety',
    'Cultural and entertainment services',
    'Accommodation',
    'Health and medical services',
    'Communication, Internet and Wi-Fi'
  ];
  var RATING_RU = [
    'Международный транспорт (узбекские компании)',
    'Процедуры паспортного контроля в пунктах пропуска через границу',
    'Гостеприимство',
    'Соотношение цены и качества',
    'Питание',
    'Чистота',
    'Транспорт (в пределах Узбекистана)',
    'Безопасность',
    'Культурные и развлекательные услуги',
    'Размещение',
    'Оздоровительные и медицинские услуги',
    'Связь, интернет и Wi-Fi'
  ];

  // ==================== TRANSLATIONS ====================
  var T = {
    en: {
      welcome_title: "DEAR TRAVELER,",
      welcome_text: 'We kindly ask you to participate in this survey, which is carried out to study tourism development and compile the tourism satellite account of Uzbekistan. We would be grateful if you could answer the questions in this questionnaire.',
      welcome_conf: 'Confidentiality of your responses is guaranteed by the Law of the Republic of Uzbekistan "On Official Statistics".',
      start: "START",
      back: '← Back',
      next: 'Next →',
      finish: 'Finish ✓',
      submitting: 'Saving…',
      submit_error: 'Saving failed. Please try again.',
      gps_required: 'Location permission is required to submit the survey. Please allow GPS access in your browser and try again.',
      gps_unsupported: 'Your browser does not support GPS. Please use a modern browser.',
      gps_acquiring: 'Acquiring GPS location…',
      error: 'Please select or enter an answer before continuing.',
      error_nights: 'The total nights in cities must equal the total nights in Uzbekistan.',
      error_pkg_nights: 'Total package nights must be ≥ nights in Uzbekistan.',
      error_row13: 'Row 13 is mandatory (you selected Exhibition/Buying goods). Please enter an amount.',
      q_of: 'Question', of: 'of', nights: 'nights',
      search: 'Search country...',
      ended_title: 'Survey Completed',
      ended_sub: 'This survey is intended for non-resident visitors to Uzbekistan only. Thank you!',
      success_title: 'Thank You!',
      success_sub: 'Your answers have been successfully recorded. We appreciate your time and participation!'
    },
    ru: {
      welcome_title: "УВАЖАЕМЫЙ ПОСЕТИТЕЛЬ,",
      welcome_text: 'Просим Вас принять участие в данном обследовании, которое проводится для изучения развития туризма и составления вспомогательного счета туризма Узбекистана. Просим Вас оказать содействие, ответив на все вопросы, включенные в настоящую анкету.',
      welcome_conf: 'Конфиденциальность Ваших ответов гарантируется Законом Республики Узбекистан «Об официальной статистике».',
      start: "НАЧАТЬ",
      back: '← Назад',
      next: 'Далее →',
      finish: 'Завершить ✓',
      submitting: 'Сохранение…',
      submit_error: 'Не удалось сохранить. Попробуйте ещё раз.',
      gps_required: 'Для отправки анкеты требуется доступ к местоположению. Разрешите GPS в браузере и повторите.',
      gps_unsupported: 'Ваш браузер не поддерживает GPS. Используйте современный браузер.',
      gps_acquiring: 'Получение GPS-местоположения…',
      error: 'Пожалуйста, выберите или введите ответ перед продолжением.',
      error_nights: 'Сумма ночей по городам должна совпадать с общим числом ночей в Узбекистане.',
      error_pkg_nights: 'Общее число ночей в туре должно быть ≥ ночей в Узбекистане.',
      error_row13: 'Строка 13 обязательна (вы выбрали Выставку/покупку товаров). Введите сумму.',
      q_of: 'Вопрос', of: 'из', nights: 'ночей',
      search: 'Поиск страны...',
      ended_title: 'Опрос завершён',
      ended_sub: 'Данный опрос предназначен только для иностранных посетителей Узбекистана. Спасибо!',
      success_title: 'Спасибо!',
      success_sub: 'Ваши ответы успешно сохранены. Мы очень ценим ваше участие!'
    }
  };

  // ==================== BUILD SEQUENCE ====================
  function buildSeq() {
    var seq = ['q1','q2','q3'];
    var p = answers.q3;
    // Transit: only q16
    if (p === 'transit') { seq.push('q16'); return seq; }
    // Employment: q5, q13, q14, q15, q16, q17 (no q18, q19)
    if (p === 'employment') { seq.push('q5','q13','q14','q15','q16','q17'); return seq; }
    if (p === 'business') seq.push('q4');
    seq.push('q5');
    if (answers.q5_zero) {
      seq.push('q13','q14','q16','q17','q18','q19');
    } else {
      seq.push('q6','q7','q8','q9');
      if (answers.q9 === 'yes') seq.push('q10','q11','q12');
      seq.push('q13','q14','q16','q17','q18','q19');
    }
    return seq;
  }

  // ==================== NAVIGATION ====================
  function goTo(id) {
    document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
    var el = document.getElementById(id);
    if (el) el.classList.add('active');
    window.scrollTo(0, 0);
  }
  // Faqat navigatsiyada (Next/Back) — qayta-render qilganda yo'q
  function scrollToTop() { window.scrollTo({ top: 0, behavior: 'smooth' }); }

  function setLang(lang) {
    currentLang = lang;
    document.querySelectorAll('.lang-tab').forEach(function (t) { t.classList.remove('active'); });
    var tab = document.getElementById('tab-' + lang);
    if (tab) tab.classList.add('active');
    var l = T[lang];
    var el = document.getElementById('wlc-title'); if (el) el.textContent = l.welcome_title;
    el = document.getElementById('wlc-text'); if (el) el.textContent = l.welcome_text;
    el = document.getElementById('wlc-conf'); if (el) el.textContent = l.welcome_conf;
    el = document.getElementById('btn-start'); if (el) el.textContent = l.start;
  }
  window.setLang = setLang;

  function startSurvey() {
    resetAnswers();
    currentQIdx = 0;
    submitted = false;
    renderQ();
    goTo('page-survey');
    window.scrollTo(0, 0);
  }
  window.startSurvey = startSurvey;

  function prevQ() {
    if (currentQIdx > 0) { currentQIdx--; renderQ(); scrollToTop(); }
  }
  window.prevQ = prevQ;

  function nextQ() {
    var seq = buildSeq();
    var qId = seq[currentQIdx];
    if (!validateQ(qId)) return;
    hideErr();
    if (currentQIdx < seq.length - 1) {
      currentQIdx++;
      renderQ();
      scrollToTop();
    } else {
      submitSurvey();
    }
  }
  window.nextQ = nextQ;

  function showErr(msg) {
    var el = document.getElementById('val-err');
    el.textContent = msg || T[currentLang].error;
    el.classList.add('show');
  }
  function hideErr() { document.getElementById('val-err').classList.remove('show'); }

  // ==================== VALIDATION ====================
  function validateQ(qId) {
    switch (qId) {
      case 'q1': if (!answers.q1) { showErr(); return false; } break;
      case 'q2':
        if (!answers.q2) { showErr(); return false; }
        if (answers.q2 === 'other' && !answers.q2_country) { showErr(); return false; }
        break;
      case 'q3': if (!answers.q3) { showErr(); return false; } break;
      case 'q4': if (!answers.q4) { showErr(); return false; } break;
      case 'q5':
        if (!answers.q5_zero && (!answers.q5_nights || answers.q5_nights <= 0)) { showErr(); return false; }
        break;
      case 'q6':
        if (!answers.q6 || Object.keys(answers.q6).length === 0) { showErr(); return false; }
        var total5 = parseInt(answers.q5_nights) || 0;
        var sum6 = 0;
        Object.values(answers.q6).forEach(function (v) { sum6 += parseInt(v.nights) || 0; });
        if (sum6 !== total5) { showErr(T[currentLang].error_nights); return false; }
        break;
      case 'q7': if (answers.q7 === undefined || answers.q7 === null) { showErr(); return false; } break;
      case 'q8': if (!answers.q8 || Object.keys(answers.q8).length === 0) { showErr(); return false; } break;
      case 'q9': if (!answers.q9) { showErr(); return false; } break;
      case 'q10':
        var tot = parseInt(answers.q10_total) || 0, uz = parseInt(answers.q10_uz) || 0;
        if (!tot || !uz) { showErr(); return false; }
        if (tot < uz) { showErr(T[currentLang].error_pkg_nights); return false; }
        break;
      case 'q11': if (!answers.q11) { showErr(); return false; } break;
      case 'q12':
        if (!answers.q12_amount) { showErr(); return false; }
        if (!answers.q12_currency) { showErr(); return false; }
        break;
      case 'q13':
        if (!answers.q13) { showErr(); return false; }
        if (answers.q13 === 'airplane' && !answers.q13_airline) { showErr(); return false; }
        break;
      case 'q14':
        if (!answers.q14) { showErr(); return false; }
        if (answers.q14 === 'airplane' && !answers.q14_airline) { showErr(); return false; }
        break;
      case 'q15': if (!answers.q15) { showErr(); return false; } break;
      case 'q16':
        if (!answers.q16_sum) { showErr(); return false; }
        if (!answers.q16_currency) { showErr(); return false; }
        break;
      case 'q17':
        if (answers.q4 === 'exhibition') {
          var r13 = (answers.q17 && answers.q17['r13']) || {};
          if (!r13.inPackage && !r13.amount) { showErr(T[currentLang].error_row13); return false; }
        }
        break;
    }
    return true;
  }

  // ==================== RENDER ====================
  function renderQ() {
    var seq = buildSeq();
    var qId = seq[currentQIdx];
    var total = seq.length;
    var pct = Math.round(((currentQIdx + 1) / total) * 100);
    var pf = document.getElementById('prog-fill'); if (pf) pf.style.width = pct + '%';
    var pl = document.getElementById('prog-lbl'); if (pl) pl.textContent = (currentQIdx + 1) + ' / ' + total;
    var prevBtn = document.getElementById('btn-prev');
    if (prevBtn) prevBtn.style.visibility = currentQIdx === 0 ? 'hidden' : 'visible';
    var nextBtn = document.getElementById('btn-next');
    nextBtn.textContent = (currentQIdx === total - 1) ? T[currentLang].finish : T[currentLang].next;
    nextBtn.disabled = false;
    if (prevBtn) prevBtn.textContent = T[currentLang].back;
    hideErr();
    var renderers = {
      q1: rQ1, q2: rQ2, q3: rQ3, q4: rQ4, q5: rQ5, q6: rQ6, q7: rQ7,
      q8: rQ8, q9: rQ9, q10: rQ10, q11: rQ11, q12: rQ12, q13: rQ13,
      q14: rQ14, q15: rQ15, q16: rQ16, q17: rQ17, q18: rQ18, q19: rQ19
    };
    document.getElementById('survey-body').innerHTML = (renderers[qId] || function () { return ''; })();
    // Hamma input/select/textarea uchun avto-saqlash
    document.querySelectorAll('#survey-body input, #survey-body select, #survey-body textarea').forEach(function (el) {
      el.addEventListener('input', saveState);
      el.addEventListener('change', saveState);
    });
    saveState();
  }

  // ==================== HELPERS ====================
  function t(en, ru) { return currentLang === 'ru' ? ru : en; }
  function chip(n, total) {
    return '<div class="q-badge">' + T[currentLang].q_of + ' ' + n + ' / ' + total + '</div>';
  }
  function qTitle(en, ru) { return '<div class="q-title">' + t(en, ru) + '</div>'; }
  function qSub(en, ru) { return '<div class="q-sub">' + t(en, ru) + '</div>'; }

  function filterC(listId, val) {
    var v = val.toLowerCase();
    document.querySelectorAll('#' + listId + ' .opt-item').forEach(function (el) {
      el.style.display = el.textContent.toLowerCase().includes(v) ? '' : 'none';
    });
  }
  window.filterC = filterC;

  function pickSingle(qId, val, el) {
    answers[qId] = val;
    var list = el.closest('.opt-list') || el.closest('.checkbox-group') || el.closest('.sub-opts');
    if (list) list.querySelectorAll('.opt-item, .sub-opt').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  }
  window.pickSingle = pickSingle;

  function toggleCheckbox(qid, val, el) {
    if (!answers[qid]) answers[qid] = {};
    if (answers[qid][val]) delete answers[qid][val];
    else answers[qid][val] = true;
    el.classList.toggle('selected');
  }
  window.toggleCheckbox = toggleCheckbox;

  function currSel(name, selVal) {
    var ph = currentLang === 'ru' ? '— Выберите валюту —' : '— Select currency —';
    var opts = '<option value="" disabled' + (!selVal ? ' selected' : '') + ' hidden>' + ph + '</option>';
    opts += CURRENCIES.map(function (c) {
      return '<option value="' + c + '"' + (selVal === c ? ' selected' : '') + '>' + c + '</option>';
    }).join('');
    return '<select class="exp-sel" onchange="answers[\'' + name + '\']=this.value">' + opts + '</select>';
  }

  // ==================== QUESTION RENDERERS ====================

  function rQ1() {
    var seq = buildSeq();
    var sel = answers.q1 || '';
    return chip(1, seq.length) +
      qTitle('In which country have you usually lived during the past 12 months?',
             'В какой стране Вы обычно проживали в течение последних 12 месяцев?') +
      qSub('Single answer only', 'Только один ответ') +
      '<div class="search-wrap"><span class="search-icon">🔍</span><input type="text" class="search-input" id="csr1" placeholder="' + T[currentLang].search + '" oninput="filterC(\'clist1\',this.value)"></div>' +
      '<div class="country-list" id="clist1">' +
      COUNTRIES.map(function (c) {
        return '<div class="opt-item' + (sel === c ? ' selected' : '') + '" onclick="selC1(this,\'' + c + '\')"><span class="opt-dot"></span>' + c + '</div>';
      }).join('') + '</div>';
  }
  window.selC1 = function (el, c) {
    answers.q1 = c;
    document.querySelectorAll('#clist1 .opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
    if (c === 'Uzbekistan') setTimeout(function () { goTo('page-ended'); }, 400);
  };

  function rQ2() {
    var seq = buildSeq();
    var v = answers.q2 || '', sel2 = answers.q2_country || '';
    var sub = '';
    if (v === 'other') {
      sub = '<div style="margin-top:14px">' +
        qSub('Which country\'s passport did you use to enter Uzbekistan?',
             'Паспорт какой страны Вы использовали для въезда в Узбекистан?') +
        '<div class="search-wrap"><span class="search-icon">🔍</span><input type="text" class="search-input" id="csr2" placeholder="' + T[currentLang].search + '" oninput="filterC(\'clist2\',this.value)"></div>' +
        '<div class="country-list" id="clist2">' +
        COUNTRIES.map(function (c) {
          return '<div class="opt-item' + (sel2 === c ? ' selected' : '') + '" onclick="selC2(this,\'' + c + '\')"><span class="opt-dot"></span>' + c + '</div>';
        }).join('') + '</div></div>';
    }
    return chip(2, seq.length) +
      qTitle('Which country\'s passport did you use to enter Uzbekistan?',
             'Паспорт какой страны Вы использовали для въезда в Узбекистан?') +
      qSub('Single answer only', 'Только один ответ') +
      '<ul class="opt-list">' +
      '<li class="opt-item' + (v === 'same' ? ' selected' : '') + '" onclick="pickQ2(\'same\',this)"><span class="opt-dot"></span>' + t('Same as country of usual residence', 'Та же, что и страна обычного проживания') + '</li>' +
      '<li class="opt-item' + (v === 'other' ? ' selected' : '') + '" onclick="pickQ2(\'other\',this)"><span class="opt-dot"></span>' + t('Other, please specify', 'Другое, пожалуйста укажите') + '</li>' +
      '</ul>' + sub;
  }
  window.pickQ2 = function (val, el) {
    answers.q2 = val; answers.q2_country = '';
    renderQ();
  };
  window.selC2 = function (el, c) {
    answers.q2_country = c;
    document.querySelectorAll('#clist2 .opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
    if (c === 'Uzbekistan') setTimeout(function () { goTo('page-ended'); }, 400);
  };

  function rQ3() {
    var seq = buildSeq();
    var v = answers.q3 || '', isAfg = (answers.q1 === 'Afghanistan');
    var opts = [
      { val: 'leisure', en: 'Holiday, leisure, and recreation', ru: 'Отпуск, досуг и отдых' },
      { val: 'friends', en: 'Visiting friends and relatives', ru: 'Посещение друзей и родственников' },
      { val: 'business', en: 'Business and professional (meetings, conferences, training)', ru: 'Деловая и профессиональная цель (встречи, конференции, обучение)' },
      { val: 'education', en: 'Education and training (short courses less than 12 months)', ru: 'Образование и обучение (краткосрочные курсы менее 12 месяцев)' },
      { val: 'health', en: 'Health and medical treatment', ru: 'Оздоровление и медицинское лечение' },
      { val: 'religion', en: 'Religion and pilgrimage', ru: 'Религия и паломничество' },
      { val: 'employment', en: 'Employment / paid work in Uzbekistan', ru: 'Трудовая деятельность / оплачиваемая работа в Узбекистане' },
      { val: 'transit', en: 'Transit (passing through to another country without a substantial stop)', ru: 'Транзит (следование в другую страну без существенной остановки)' },
      { val: 'other', en: 'Other', ru: 'Другое' }
    ];
    if (isAfg) opts.push({ val: 'termiz', en: 'To go to the Termiz trade center', ru: 'Посетить торговый центр в Термезе' });
    return chip(3, seq.length) +
      qTitle('What is the main purpose of your visit to Uzbekistan?', 'Какова основная цель Вашего визита в Узбекистан?') +
      qSub('Select only one option that best describes why you came to Uzbekistan this time.',
           'Пожалуйста, выберите один вариант, который лучше всего описывает причину Вашего приезда в Узбекистан в этот раз.') +
      '<ul class="opt-list">' +
      opts.map(function (o) {
        return '<li class="opt-item' + (v === o.val ? ' selected' : '') + '" onclick="pickQ3(\'' + o.val + '\',this)"><span class="opt-dot"></span>' + t(o.en, o.ru) + '</li>';
      }).join('') + '</ul>';
  }
  window.pickQ3 = function (val, el) {
    answers.q3 = val;
    document.querySelectorAll('#survey-body .opt-list .opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ4() {
    var seq = buildSeq();
    var v = answers.q4 || '';
    var opts = [
      { val: 'exhibition', en: 'Exhibition / buying goods with the aim of resale', ru: 'Участие в выставке / покупка товаров с целью перепродажи' },
      { val: 'corporate', en: 'Corporate / business meeting, seminar, workshop, or presentation', ru: 'Корпоративная / деловая встреча, семинар, практический тренинг или презентация' },
      { val: 'incentive', en: 'Incentive tour organized by a business', ru: 'Поощрительная поездка, организованная компанией' },
      { val: 'conference', en: 'Conference, Congress, Forum', ru: 'Конференция, конгресс, форум' }
    ];
    return chip(4, seq.length) +
      qTitle('What was the main purpose of your business/professional visit to Uzbekistan?',
             'Какова основная цель Вашего делового/профессионального визита в Узбекистан?') +
      qSub('Single answer only', 'Только один ответ') +
      '<ul class="opt-list">' +
      opts.map(function (o) {
        return '<li class="opt-item' + (v === o.val ? ' selected' : '') + '" onclick="pickSingle(\'q4\',\'' + o.val + '\',this)"><span class="opt-dot"></span>' + t(o.en, o.ru) + '</li>';
      }).join('') + '</ul>';
  }

  function rQ5() {
    var seq = buildSeq();
    var zero = answers.q5_zero === true, nights = answers.q5_nights || '';
    return chip(5, seq.length) +
      qTitle('How many nights did you spend in Uzbekistan?', 'Сколько ночей Вы провели в Узбекистане?') +
      qSub('Enter the number of nights you spent in Uzbekistan.', 'Введите количество ночей, проведённых в Узбекистане.') +
      '<input type="number" class="survey-input" id="q5n" value="' + nights + '" min="1" placeholder="' + t('Number of nights...', 'Количество ночей...') + '" ' + (zero ? 'disabled' : '') + ' oninput="answers.q5_nights=parseInt(this.value)">' +
      '<div style="margin-top:10px"><label class="opt-item' + (zero ? ' checked' : '') + '" style="cursor:pointer" onclick="toggleZero()"><span class="opt-sq"></span>' +
      t('0 nights (arrived and left on the same day) → goes to question 13', '0 ночей (прибыл и убыл в тот же день) → переход к вопросу 13') +
      '</label></div>';
  }
  window.toggleZero = function () {
    answers.q5_zero = !answers.q5_zero;
    if (answers.q5_zero) answers.q5_nights = 0;
    renderQ();
  };

  function rQ6() {
    var seq = buildSeq();
    var ck = answers.q6 || {};
    var places = currentLang === 'ru' ? PLACES_RU : PLACES_EN;
    var placeKeys = PLACES_EN;
    return chip(6, seq.length) +
      qTitle('Which cities or regions did you visit during this trip, and how many nights did you spend in each?',
             'Какие города и регионы Вы посетили во время этой поездки и сколько ночей провели в каждом из них?') +
      qSub('Several answers are permissible. Total nights must equal nights in Question 5.',
           'Допускается несколько ответов. Сумма ночей должна совпадать с ответом на вопрос 5.') +
      '<div class="places-grid">' +
      placeKeys.map(function (pk, i) {
        var ch = !!ck[pk];
        var nights = (ck[pk] && ck[pk].nights) || '';
        return '<div class="place-row' + (ch ? ' checked' : '') + '" onclick="togglePlace(\'' + pk + '\')">' +
          '<div class="place-sq"></div>' +
          '<div class="place-name">' + places[i] + '</div>' +
          '<div class="place-nights"><input type="number" min="0" value="' + nights + '" placeholder="0" onclick="event.stopPropagation()" oninput="setPN(\'' + pk + '\',this.value)"><span>' + T[currentLang].nights + '</span></div>' +
          '</div>';
      }).join('') + '</div>';
  }
  window.togglePlace = function (p) {
    if (!answers.q6) answers.q6 = {};
    if (answers.q6[p]) delete answers.q6[p];
    else answers.q6[p] = { nights: '' };
    renderQ();
  };
  window.setPN = function (p, v) {
    if (!answers.q6) answers.q6 = {};
    if (!answers.q6[p]) answers.q6[p] = {};
    answers.q6[p].nights = parseInt(v) || 0;
  };

  function rQ7() {
    var seq = buildSeq();
    var v = answers.q7;
    var optsEn = ['Hotel, motel, hostel, or guesthouse (paid commercial lodging)', 'Rented apartment, house, or villa (e.g., Airbnb, private rental)', 'Staying with friends or relatives (free of charge)', 'Own property or second home (owned by you or your immediate family in Uzbekistan)', 'Sanatorium, health resort, or spa facility', 'Camping / recreational vehicle', 'Other paid accommodation'];
    var optsRu = ['Гостиница, мотель, хостел или гостевой дом (платное коммерческое размещение)', 'Арендованная квартира, дом или вилла (например, Airbnb, частная аренда)', 'Проживание у друзей или родственников (бесплатно)', 'Собственная недвижимость или второй дом (принадлежащие Вам или Вашим ближайшим родственникам в Узбекистане)', 'Санаторий, оздоровительный курорт или SPA-объект', 'Кемпинг / автодом', 'Другое платное размещение'];
    var opts = currentLang === 'ru' ? optsRu : optsEn;
    return chip(7, seq.length) +
      qTitle('What type of accommodation did you primarily use during your time in Uzbekistan?',
             'Каким видом размещения Вы преимущественно пользовались во время пребывания в Узбекистане?') +
      qSub('Choose the one where you stayed the most nights.', 'Выберите тот вариант, в котором Вы провели наибольшее количество ночей.') +
      '<ul class="opt-list">' +
      opts.map(function (o, i) {
        return '<li class="opt-item' + (v === i ? ' selected' : '') + '" onclick="pickSingle(\'q7\',' + i + ',this)"><span class="opt-dot"></span>' + o + '</li>';
      }).join('') + '</ul>';
  }

  function rQ8() {
    var seq = buildSeq();
    var sel = answers.q8 || {};
    var opts = [
      { id: 'restaurants', en: 'Restaurants or cafes', ru: 'Рестораны или кафе' },
      { id: 'street', en: 'Street food providers', ru: 'Точки уличного питания' },
      { id: 'fastfood', en: 'Fast food restaurants', ru: 'Заведения быстрого питания (fast food)' },
      { id: 'national', en: 'National cuisine (Chayxana)', ru: 'Заведения национальной кухни (чайхана)' },
      { id: 'friends_home', en: "Friend's or relative's home", ru: 'Дом у друзей или родственников' },
      { id: 'rented', en: 'At rented accommodation / self-catering', ru: 'В арендованном жилье (самостоятельное приготовление пищи)' },
      { id: 'other', en: 'Other, please specify', ru: 'Другое, пожалуйста укажите' }
    ];
    return chip(8, seq.length) +
      qTitle('Where did you purchase food and drinks?', 'Скажите, пожалуйста, в каких типах заведений или мест Вы покупали еду и напитки?') +
      qSub('Several answers are permissible.', 'Допускается несколько ответов.') +
      '<div class="checkbox-group">' +
      opts.map(function (o) {
        return '<div class="checkbox-item' + (sel[o.id] ? ' selected' : '') + '" onclick="toggleCheckbox(\'q8\',\'' + o.id + '\',this)"><span class="checkbox-sq"></span>' + t(o.en, o.ru) + '</div>';
      }).join('') + '</div>';
  }

  function rQ9() {
    var seq = buildSeq();
    var v = answers.q9 || '';
    return chip(9, seq.length) +
      qTitle('Did you travel to Uzbekistan on a package tour?', 'Скажите, пожалуйста, Вы приехали в Узбекистан в рамках пакетного тура?') +
      '<div class="yn-group">' +
      '<button class="yn-btn' + (v === 'yes' ? ' selected' : '') + '" onclick="pickYN(\'yes\',this)">✅ ' + t('Yes', 'Да') + '</button>' +
      '<button class="yn-btn' + (v === 'no' ? ' selected' : '') + '" onclick="pickYN(\'no\',this)">❌ ' + t('No', 'Нет') + '</button>' +
      '</div>';
  }
  window.pickYN = function (val, el) {
    answers.q9 = val;
    document.querySelectorAll('.yn-btn').forEach(function (b) { b.classList.remove('selected'); });
    el.classList.add('selected');
    renderQ();
  };

  function rQ10() {
    var seq = buildSeq();
    return chip(10, seq.length) +
      qTitle('How many nights did the package tour cover in total, and how many of those nights were spent in Uzbekistan?',
             'Сколько ночей в целом включал пакетный тур и сколько из этих ночей было проведено в Узбекистане?') +
      '<label class="field-label">' + t('Total nights in the package tour', 'Всего ночей в пакетном туре') + '</label>' +
      '<input type="number" class="survey-input" min="1" value="' + (answers.q10_total || '') + '" placeholder="' + t('Nights...', 'Ночей...') + '" oninput="answers.q10_total=parseInt(this.value)">' +
      '<label class="field-label">' + t('Nights spent in Uzbekistan', 'Ночей в Узбекистане') + '</label>' +
      '<input type="number" class="survey-input" min="0" value="' + (answers.q10_uz || '') + '" placeholder="' + t('Nights...', 'Ночей...') + '" oninput="answers.q10_uz=parseInt(this.value)">';
  }

  function rQ11() {
    var seq = buildSeq();
    return chip(11, seq.length) +
      qTitle('Including yourself, how many people were covered by the package tour?',
             'Сколько человек, включая Вас, охватывал пакетный тур?') +
      '<input type="number" class="survey-input" min="1" value="' + (answers.q11 || '') + '" placeholder="' + t('Number of persons...', 'Количество человек...') + '" oninput="answers.q11=parseInt(this.value)">';
  }

  function rQ12() {
    var seq = buildSeq();
    return chip(12, seq.length) +
      qTitle('How much did you pay for this package tour?', 'Сколько Вы заплатили за данный пакетный тур?') +
      qSub('Please specify amount and currency of payment.', 'Пожалуйста, укажите сумму и валюту платежа.') +
      '<div class="inline-fields">' +
      '<input type="number" class="survey-input" style="flex:2;margin-bottom:0" min="0" value="' + (answers.q12_amount || '') + '" placeholder="' + t('Amount...', 'Сумма...') + '" oninput="answers.q12_amount=this.value">' +
      currSel('q12_currency', answers.q12_currency) +
      '</div>';
  }

  function rQ13() {
    var seq = buildSeq();
    var v = answers.q13 || '', al = answers.q13_airline || '';
    var sub = '';
    if (v === 'airplane') {
      sub = '<div class="sub-opts">' +
        '<div class="sub-opt' + (al === 'uzair' ? ' selected' : '') + '" onclick="pickAirline13(\'uzair\',this)">✈️ ' + t('Uzbekistan Airways (Uzbek airline)', 'Узбекистан Хаво Йуллари (узбекская авиакомпания)') + '</div>' +
        '<div class="sub-opt' + (al === 'other' ? ' selected' : '') + '" onclick="pickAirline13(\'other\',this)">🌐 ' + t('Other (non-Uzbek) airlines', 'Другие (иностранные) авиакомпании') + '</div>' +
        '</div>';
    }
    return chip(13, seq.length) +
      qTitle('What main mode of transportation did you use to ARRIVE in Uzbekistan?',
             'Каким видом транспорта Вы ПРИБЫЛИ в Узбекистан?') +
      qSub('Please select one main option.', 'Пожалуйста, выберите один основной вариант.') +
      '<ul class="opt-list">' +
      '<li class="opt-item' + (v === 'airplane' ? ' selected' : '') + '" onclick="pickQ13(\'airplane\',this)"><span class="opt-dot"></span>✈️ ' + t('Airplane', 'Воздушный транспорт (самолёт)') + '</li>' +
      (v === 'airplane' ? '<li style="padding:0;border:none;background:none;">' + sub + '</li>' : '') +
      '<li class="opt-item' + (v === 'train' ? ' selected' : '') + '" onclick="pickQ13(\'train\',this)"><span class="opt-dot"></span>🚂 ' + t('Train', 'Железнодорожный транспорт (поезд)') + '</li>' +
      '<li class="opt-item' + (v === 'road' ? ' selected' : '') + '" onclick="pickQ13(\'road\',this)"><span class="opt-dot"></span>🚗 ' + t('Road transport: car, bus, or motorcycle', 'Автомобильный транспорт (автомобиль, автобус, мотоцикл)') + '</li>' +
      '</ul>';
  }
  window.pickQ13 = function (val, el) {
    answers.q13 = val; answers.q13_airline = '';
    renderQ();
  };
  window.pickAirline13 = function (val, el) {
    answers.q13_airline = val;
    document.querySelectorAll('#survey-body .sub-opts .sub-opt').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ14() {
    var seq = buildSeq();
    var v = answers.q14 || '', al = answers.q14_airline || '';
    var sub = '';
    if (v === 'airplane') {
      sub = '<div class="sub-opts">' +
        '<div class="sub-opt' + (al === 'uzair' ? ' selected' : '') + '" onclick="pickAirline14(\'uzair\',this)">✈️ ' + t('Uzbekistan Airways (Uzbek airline)', 'Узбекистан Хаво Йуллари (узбекская авиакомпания)') + '</div>' +
        '<div class="sub-opt' + (al === 'other' ? ' selected' : '') + '" onclick="pickAirline14(\'other\',this)">🌐 ' + t('Other (non-Uzbek) airlines', 'Другие (иностранные) авиакомпании') + '</div>' +
        '</div>';
    }
    return chip(14, seq.length) +
      qTitle('What main mode of transportation did you use to LEAVE Uzbekistan?',
             'Каким видом транспорта Вы ВЫЛЕТАЕТЕ из Узбекистана?') +
      qSub('Please select one main option.', 'Пожалуйста, выберите один основной вариант.') +
      '<ul class="opt-list">' +
      '<li class="opt-item' + (v === 'airplane' ? ' selected' : '') + '" onclick="pickQ14(\'airplane\',this)"><span class="opt-dot"></span>✈️ ' + t('Airplane', 'Воздушный транспорт (самолёт)') + '</li>' +
      (v === 'airplane' ? '<li style="padding:0;border:none;background:none;">' + sub + '</li>' : '') +
      '<li class="opt-item' + (v === 'train' ? ' selected' : '') + '" onclick="pickQ14(\'train\',this)"><span class="opt-dot"></span>🚂 ' + t('Train', 'Железнодорожный транспорт (поезд)') + '</li>' +
      '<li class="opt-item' + (v === 'road' ? ' selected' : '') + '" onclick="pickQ14(\'road\',this)"><span class="opt-dot"></span>🚗 ' + t('Road transport: car, bus, or motorcycle', 'Автомобильный транспорт (автомобиль, автобус, мотоцикл)') + '</li>' +
      '</ul>';
  }
  window.pickQ14 = function (val, el) {
    answers.q14 = val; answers.q14_airline = '';
    renderQ();
  };
  window.pickAirline14 = function (val, el) {
    answers.q14_airline = val;
    document.querySelectorAll('#survey-body .sub-opts .sub-opt').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ15() {
    var seq = buildSeq();
    var v = answers.q15 || '';
    var optsEn = ['Less than 25%', '25% – 50%', '50% – 75%', 'More than 75%'];
    var optsRu = ['Менее 25%', '25% – 50%', '50% – 75%', 'Более 75%'];
    var opts = currentLang === 'ru' ? optsRu : optsEn;
    return chip(15, seq.length) +
      qTitle('During your period of employment in Uzbekistan, how much of your monthly income do you estimate you spend here on food, rent, and local transportation?',
             'В период работы в Узбекистане какую долю Вашего месячного дохода, по Вашей оценке, Вы тратите здесь на питание, аренду жилья и местный транспорт?') +
      qSub('Please select one option.', 'Пожалуйста, выберите один вариант.') +
      '<ul class="opt-list">' +
      opts.map(function (o, i) {
        return '<li class="opt-item' + (v === optsEn[i] ? ' selected' : '') + '" onclick="pickSingle(\'q15\',\'' + optsEn[i] + '\',this)"><span class="opt-dot"></span>' + o + '</li>';
      }).join('') + '</ul>';
  }

  function rQ16() {
    var seq = buildSeq();
    return chip(16, seq.length) +
      qTitle('What total amount did you spend during your visit to Uzbekistan, including all types of expenses but excluding the cost of the package tour?',
             'Какую общую сумму денежных средств, по Вашей оценке, Вы потратили во время визита в Узбекистан, включая все виды расходов, но без учёта стоимости пакетного тура?') +
      qSub('If all expenses are included in the package tour, please indicate that.',
           'Если все расходы включены в стоимость пакетного тура, пожалуйста, укажите это.') +
      '<div class="inline-fields">' +
      '<input type="number" class="survey-input" style="flex:2;margin-bottom:0" min="0" value="' + (answers.q16_sum || '') + '" placeholder="' + t('Amount...', 'Сумма...') + '" oninput="answers.q16_sum=this.value">' +
      currSel('q16_currency', answers.q16_currency) +
      '</div>' +
      '<label class="field-label" style="margin-top:10px">' + t('Number of persons (group size)', 'Количество человек (размер группы)') + '</label>' +
      '<input type="number" class="survey-input" min="1" value="' + (answers.q16_persons || '') + '" placeholder="' + t('Persons...', 'Человек...') + '" oninput="answers.q16_persons=parseInt(this.value)">';
  }

  function rQ17() {
    var seq = buildSeq();
    if (!answers.q17) answers.q17 = {};
    var showPkg = answers.q9 === 'yes';
    var isEmployment = answers.q3 === 'employment';
    var gridStyle = showPkg ? '1fr 36px 110px 80px' : '1fr 110px 80px';
    var headCols = showPkg
      ? '<div>' + t('Expense type', 'Тип расхода') + '</div><div style="text-align:center">☑</div><div>' + t('Amount', 'Сумма') + '</div><div>' + t('Currency', 'Валюта') + '</div>'
      : '<div>' + t('Expense type', 'Тип расхода') + '</div><div>' + t('Amount', 'Сумма') + '</div><div>' + t('Currency', 'Валюта') + '</div>';

    var rowsHtml = EXP_ROWS.map(function (row) {
      var r = answers.q17['r' + row.n] || {};
      var isMand = row.mand && answers.q4 === 'exhibition';
      var checked = r.inPackage || false;
      var disabled = checked ? 'disabled' : '';
      var label = t(row.en, row.ru);
      if (isEmployment && row.n === 14) {
        label += ' <span style="color:var(--red);font-size:11px">(' + t('utility bills for accommodation; taxes and work permit', 'коммунальные услуги; налоги и разрешение на работу') + ')</span>';
      }
      var hasChk = (row.n <= 6) && showPkg;
      var chkCell = hasChk
        ? '<div style="text-align:center"><input type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="toggleExpPkg(\'' + row.n + '\',this)"></div>'
        : (showPkg ? '<div></div>' : '');
      return '<div class="exp-row' + (isMand ? ' mandatory-row' : '') + '" style="grid-template-columns:' + gridStyle + '">' +
        '<div><div class="exp-num">' + row.n + '.</div><div class="exp-name">' + label + (isMand ? ' ⭐' : '') + '</div></div>' +
        chkCell +
        '<input class="exp-inp' + (isMand ? ' mand' : '') + '" type="number" min="0" placeholder="' + t('Amount...', 'Сумма...') + '" value="' + (r.amount || '') + '" ' + disabled + ' oninput="setExp(\'' + row.n + '\',\'amount\',this.value)">' +
        '<select class="exp-sel" ' + disabled + ' onchange="setExp(\'' + row.n + '\',\'currency\',this.value)">' +
        '<option value="" disabled' + (!r.currency ? ' selected' : '') + ' hidden>—</option>' +
        CURRENCIES.map(function (c) { return '<option value="' + c + '"' + (r.currency === c ? ' selected' : '') + '>' + c + '</option>'; }).join('') + '</select>' +
        '</div>';
    }).join('');

    return chip(17, seq.length) +
      qTitle('Please indicate which types of expenses you had in Uzbekistan and their approximate cost.',
             'Пожалуйста, укажите, какие виды расходов у Вас были в Узбекистане и их примерную стоимость.') +
      (showPkg ? qSub('☑ = included in the cost of the package tour (rows 1–6 only). If checked, amount and currency are disabled.',
                      '☑ = включено в стоимость пакетного тура (строки 1–6). Если отмечено, сумма и валюта блокируются.') : '') +
      '<div class="exp-wrap"><div class="exp-head" style="grid-template-columns:' + gridStyle + '">' + headCols + '</div>' + rowsHtml + '</div>';
  }
  window.toggleExpPkg = function (n, chk) {
    if (!answers.q17) answers.q17 = {};
    if (!answers.q17['r' + n]) answers.q17['r' + n] = {};
    answers.q17['r' + n].inPackage = chk.checked;
    if (chk.checked) {
      answers.q17['r' + n].amount = '';
      answers.q17['r' + n].currency = '';
    }
    var row = chk.closest('.exp-row');
    if (row) {
      var inp = row.querySelector('.exp-inp');
      var sel = row.querySelector('.exp-sel');
      if (inp) { inp.disabled = chk.checked; if (chk.checked) inp.value = ''; }
      if (sel) { sel.disabled = chk.checked; }
    }
  };
  window.setExp = function (n, field, val) {
    if (!answers.q17) answers.q17 = {};
    if (!answers.q17['r' + n]) answers.q17['r' + n] = {};
    answers.q17['r' + n][field] = val;
  };

  function rQ18() {
    var seq = buildSeq();
    if (!answers.q18) answers.q18 = {};
    var ratingLabels = currentLang === 'ru' ? RATING_RU : RATING_EN;
    var rows = ratingLabels.map(function (item, i) {
      var v = answers.q18['r' + i];
      var btns = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(function (n) {
        return '<button class="rating-btn' + (v === n ? ' picked' : '') + '" onclick="setRating(' + i + ',' + n + ')">' + n + '</button>';
      }).join('');
      return '<div class="rating-row"><div class="rating-label">' + (i + 1) + '. ' + item + '</div><div class="rating-nums">' + btns + '<button class="rating-na' + (v === 'na' ? ' picked' : '') + '" onclick="setRating(' + i + ',\'na\')">N/A</button></div></div>';
    }).join('');
    return chip(18, seq.length) +
      qTitle('Please rate your satisfaction with the services you received during your visit.',
             'Пожалуйста, оцените Вашу удовлетворённость услугами во время визита.') +
      qSub('Scale 1 to 10, where 1 is the lowest score and 10 is the highest. Please do not rate services you did not use (select N/A).',
           'Шкала от 1 до 10, где 1 — самая низкая оценка, а 10 — самая высокая. Пожалуйста, не оценивайте услуги, которыми Вы не пользовались (выберите N/A).') +
      '<div class="rating-section">' + rows + '</div>';
  }
  window.setRating = function (i, val) {
    if (!answers.q18) answers.q18 = {};
    answers.q18['r' + i] = val;
    // Faqat shu qator buttonlarini yangilash — sahifani tepaga ko'tarmaslik uchun
    var rows = document.querySelectorAll('#survey-body .rating-row');
    var row = rows[i];
    if (row) {
      row.querySelectorAll('.rating-btn, .rating-na').forEach(function (b) { b.classList.remove('picked'); });
      if (val === 'na') {
        var na = row.querySelector('.rating-na');
        if (na) na.classList.add('picked');
      } else {
        var btns = row.querySelectorAll('.rating-btn');
        if (btns[val - 1]) btns[val - 1].classList.add('picked');
      }
    }
    saveState();
  };

  function rQ19() {
    var seq = buildSeq();
    return chip(19, seq.length) +
      qTitle('Please share your opinion on any problems or improvements for travelers in Uzbekistan.',
             'Пожалуйста, напишите Ваше мнение о любых проблемах или о том, что можно улучшить для путешественников в Узбекистане.') +
      qSub('We would appreciate any comments or suggestions you can offer! (Optional)',
           'Мы будем признательны за любые комментарии или предложения! (Необязательно)') +
      '<textarea class="comment-textarea" rows="5" placeholder="' + t('Write here...', 'Напишите здесь...') + '" oninput="answers.q19=this.value">' + (answers.q19 || '') + '</textarea>';
  }

  // ============ GEOLOCATION ============
  function getLocation() {
    return new Promise(function (resolve) {
      if (!('geolocation' in navigator)) {
        resolve({ granted: false });
        return;
      }
      var timeoutId = setTimeout(function () {
        resolve({ granted: false, reason: 'timeout' });
      }, 8000);
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          clearTimeout(timeoutId);
          resolve({
            granted: true,
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
          });
        },
        function (err) {
          clearTimeout(timeoutId);
          resolve({ granted: false, reason: err.code === 1 ? 'denied' : 'error' });
        },
        { enableHighAccuracy: true, timeout: 7000, maximumAge: 0 }
      );
    });
  }

  // ==================== SUBMIT ====================
  function submitSurvey() {
    if (submitted) return;
    submitted = true;
    var nextBtn = document.getElementById('btn-next');
    nextBtn.disabled = true;
    nextBtn.textContent = T[currentLang].gps_acquiring;

    if (!('geolocation' in navigator)) {
      submitted = false;
      nextBtn.disabled = false;
      nextBtn.textContent = T[currentLang].finish;
      showErr(T[currentLang].gps_unsupported);
      return;
    }

    // GPS majburiy — ruxsat berilmasa, yubormaymiz
    getLocation().then(function (location) {
      if (!location.granted) {
        submitted = false;
        nextBtn.disabled = false;
        nextBtn.textContent = T[currentLang].finish;
        showErr(T[currentLang].gps_required);
        return null;
      }
      nextBtn.textContent = T[currentLang].submitting;
      return fetch(CFG.submitUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CFG.csrfToken,
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          answers: answers,
          language: currentLang,
          location: location,
        }),
      });
    }).then(function (res) {
      if (res === null) return null;  // GPS denied — already handled
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      if (data === null) return;  // GPS denied
      if (data && data.ok) {
        clearState();
        goTo('page-success');
      } else {
        throw new Error('Server error');
      }
    }).catch(function (err) {
      submitted = false;
      nextBtn.disabled = false;
      nextBtn.textContent = T[currentLang].finish;
      showErr(T[currentLang].submit_error);
    });
  }

  // ============ INIT — restore sessionStorage ============
  function init() {
    var saved = loadState();
    if (saved && saved.answers) {
      // Avvalgi answers ni ko'chirish (window.answers reference saqlanadi)
      Object.keys(saved.answers).forEach(function (k) { answers[k] = saved.answers[k]; });
      currentLang = saved.currentLang || 'en';
      currentQIdx = saved.currentQIdx || 0;
      // Til tablarini yangilash
      setLang(currentLang);
      // To'g'ridan-to'g'ri survey sahifasiga o'tish
      renderQ();
      goTo('page-survey');
    } else {
      setLang('en');
    }
  }
  init();
})();
