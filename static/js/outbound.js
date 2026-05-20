// ============================================
// Outbound survey logic (UZ/RU) — Django backend
// 2026 versiya — yangilangan (96 davlat, employment yo'li, sub-rows 1.1/1.2)
// ============================================
(function () {
  'use strict';

  var CFG = window.SURVEY_CONFIG || {};
  var currentLang = 'uz';
  var currentQIdx = 0;
  // Boshlanish vaqti — submit'da fill_duration_ms hisoblash uchun
  var SURVEY_START_TS = Date.now();
  // GLOBAL — inline oninput="answers.X=Y" lar global scope'da bajarilgani uchun
  window.answers = window.answers || {};
  var answers = window.answers;
  var submitted = false;

  // ============ SESSION STORAGE ============
  var STORAGE_KEY = 'tourism_outbound_state_v1';
  function saveState() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        currentQIdx: currentQIdx,
        currentLang: currentLang,
        answers: answers,
      }));
    } catch (e) {}
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

  function resetAnswers() {
    Object.keys(answers).forEach(function (k) { delete answers[k]; });
  }

  // ==================== DATA ====================
  var COUNTRIES_UZ = [
    'Afgʻoniston', 'Albaniya', 'Jazoir', 'Argentina', 'Armaniston', 'Avstraliya', 'Avstriya', 'Ozarbayjon',
    'Bahrayn', 'Bangladesh', 'Belarus', 'Belgiya', 'Braziliya', 'Bolgariya', 'Kanada', 'Chili', 'Xitoy',
    'Kolumbiya', 'Xorvatiya', 'Kuba', 'Kipr', 'Chexiya', 'Daniya', 'Misr', 'Estoniya', 'Efiopiya',
    'Finlyandiya', 'Fransiya', 'Gruziya', 'Germaniya', 'Gana', 'Gretsiya', 'Vengriya', 'Hindiston', 'Indoneziya',
    'Eron', 'Iroq', 'Irlandiya', 'Isroil', 'Italiya', 'Yaponiya', 'Iordaniya', 'Qozogʻiston', 'Keniya', 'Quvayt',
    'Qirgʻiziston', 'Latviya', 'Livan', 'Litva', 'Malayziya', 'Meksika', 'Moldova', 'Mongoliya',
    'Marokash', 'Niderlandiya', 'Yangi Zelandiya', 'Nigeriya', 'Shimoliy Koreya', 'Norvegiya', 'Ummon', 'Pokiston',
    'Falastin', 'Filippin', 'Polsha', 'Portugaliya', 'Qatar', 'Ruminiya', 'Rossiya', 'Saudiya Arabistoni',
    'Serbiya', 'Singapur', 'Slovakiya', 'Sloveniya', 'Janubiy Afrika', 'Janubiy Koreya', 'Ispaniya', 'Shri-Lanka',
    'Shvetsiya', 'Shveytsariya', 'Suriya', 'Tayvan', 'Tojikiston', 'Tailand', 'Tunis', 'Turkiya',
    'Turkmaniston', 'BAA', 'Ukraina', 'Buyuk Britaniya', 'AQSh', "O'zbekiston",
    'Venesuela', 'Vyetnam', 'Yaman', 'Boshqa'
  ];
  var COUNTRIES_RU = [
    'Афганистан', 'Албания', 'Алжир', 'Аргентина', 'Армения', 'Австралия', 'Австрия', 'Азербайджан',
    'Бахрейн', 'Бангладеш', 'Беларусь', 'Бельгия', 'Бразилия', 'Болгария', 'Канада', 'Чили', 'Китай',
    'Колумбия', 'Хорватия', 'Куба', 'Кипр', 'Чехия', 'Дания', 'Египет', 'Эстония', 'Эфиопия',
    'Финляндия', 'Франция', 'Грузия', 'Германия', 'Гана', 'Греция', 'Венгрия', 'Индия', 'Индонезия',
    'Иран', 'Ирак', 'Ирландия', 'Израиль', 'Италия', 'Япония', 'Иордания', 'Казахстан', 'Кения', 'Кувейт',
    'Кыргызстан', 'Латвия', 'Ливан', 'Литва', 'Малайзия', 'Мексика', 'Молдова', 'Монголия',
    'Марокко', 'Нидерланды', 'Новая Зеландия', 'Нигерия', 'Северная Корея', 'Норвегия', 'Оман', 'Пакистан',
    'Палестина', 'Филиппины', 'Польша', 'Португалия', 'Катар', 'Румыния', 'Россия', 'Саудовская Аравия',
    'Сербия', 'Сингапур', 'Словакия', 'Словения', 'ЮАР', 'Южная Корея', 'Испания', 'Шри-Ланка',
    'Швеция', 'Швейцария', 'Сирия', 'Тайвань', 'Таджикистан', 'Таиланд', 'Тунис', 'Турция',
    'Туркменистан', 'ОАЭ', 'Украина', 'Великобритания', 'США', 'Узбекистан',
    'Венесуэла', 'Вьетнам', 'Йемен', 'Другое'
  ];
  // ENG kalitlar (saqlash uchun)
  var COUNTRIES_KEY = [
    'Afghanistan', 'Albania', 'Algeria', 'Argentina', 'Armenia', 'Australia', 'Austria', 'Azerbaijan',
    'Bahrain', 'Bangladesh', 'Belarus', 'Belgium', 'Brazil', 'Bulgaria', 'Canada', 'Chile', 'China',
    'Colombia', 'Croatia', 'Cuba', 'Cyprus', 'Czech Republic', 'Denmark', 'Egypt', 'Estonia', 'Ethiopia',
    'Finland', 'France', 'Georgia', 'Germany', 'Ghana', 'Greece', 'Hungary', 'India', 'Indonesia',
    'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kuwait',
    'Kyrgyzstan', 'Latvia', 'Lebanon', 'Lithuania', 'Malaysia', 'Mexico', 'Moldova', 'Mongolia',
    'Morocco', 'Netherlands', 'New Zealand', 'Nigeria', 'North Korea', 'Norway', 'Oman', 'Pakistan',
    'Palestine', 'Philippines', 'Poland', 'Portugal', 'Qatar', 'Romania', 'Russia', 'Saudi Arabia',
    'Serbia', 'Singapore', 'Slovakia', 'Slovenia', 'South Africa', 'South Korea', 'Spain', 'Sri Lanka',
    'Sweden', 'Switzerland', 'Syria', 'Taiwan', 'Tajikistan', 'Thailand', 'Tunisia', 'Turkey',
    'Turkmenistan', 'UAE', 'Ukraine', 'United Kingdom', 'United States', 'Uzbekistan',
    'Venezuela', 'Vietnam', 'Yemen', 'Other'
  ];

  var CURRENCIES = ['USD', 'EUR', 'UZS', 'RUB', 'GBP', 'CNY', 'KZT', 'CHF', 'JPY', 'AED', 'Boshqa/Другое'];

  // EXP_ROWS — sub:true bo'lganlar (1.1, 1.2) faqat employment uchun ko'rinadi
  var EXP_ROWS = [
    { n: '1', uz: 'Turar joy: (toʻlov summasi faqat xona uchun)', ru: 'Размещение: (сумма оплаты только за номер/комнату)', pkg: true },
    { n: '1.1', uz: 'Turar joy uchun kommunal toʻlovlar', ru: 'Коммунальные платежи, если они оплачивались отдельно', sub: true, pkg: false },
    { n: '1.2', uz: 'Soliqlar va ishlash uchun ruxsatnoma', ru: 'Налоги и сборы, связанные с разрешением на работу', sub: true, pkg: false },
    { n: '2', uz: 'Ovqat va ichimliklar', ru: 'Питание и напитки', pkg: true },
    { n: '3', uz: 'Xalqaro transport', ru: 'Международный транспорт', pkg: true },
    { n: '4', uz: "Mahalliy transport (faqat O'zbekistondan tashqarida)", ru: 'Местный транспорт (только за пределами Узбекистана)', pkg: true },
    { n: '5', uz: 'Madaniy xizmatlar (muzeylar, tomoshalar, kinoteatrlarga kirish chiptalari)', ru: 'Культурные услуги (входные билеты в музеи, на представления, фильмы)', pkg: true },
    { n: '6', uz: "Sport xizmatlari, ko'ngil ochish va dam olish", ru: 'Спортивные услуги, развлечения и отдых', pkg: true },
    { n: '7', uz: "Ta'lim xarajatlari", ru: 'Расходы на образование', pkg: false },
    { n: '8', uz: "Tibbiy xizmatlar (sanatoriyalar, sog'lomlashtirish maskanlari)", ru: 'Медицинские услуги (санатории, оздоровительные курорты)', pkg: false },
    { n: '9', uz: "Shaxsiy avtotransportni yoqilg'i bilan ta'minlash va texnik xizmat ko'rsatish", ru: 'Заправка топливом и техническое обслуживание собственного автотранспорта', pkg: false },
    { n: '10', uz: "Qimmatbaho buyumlar sotib olish (qimmatbaho metallar va toshlar, zargarlik buyumlari, san'at asarlari)", ru: 'Покупка ценностей (драгоценные металлы и камни, ювелирные изделия, произведения искусства)', pkg: false },
    { n: '11', uz: "Xaridlar: suvenir, kiyim-kechak, boshqa iste'mol tovarlari, aloqa va internet xizmatlari (qimmatbaho buyumlardan tashqari)", ru: 'Покупки: сувениры, одежда, другие потребительские товары, услуги связи и Интернета, за исключением ценностей', pkg: false },
    { n: '12', uz: "O'zbekistonda qayta sotish maqsadida chet elda sotib olingan tovarlarning qiymati (yuqorida qayd etilganlardan tashqari)", ru: 'Стоимость товаров, приобретённых за рубежом для перепродажи в Узбекистане, за исключением вышеуказанных товаров', pkg: false, mand: true },
    { n: '13', uz: 'Boshqa xarajatlar', ru: 'Прочие расходы', pkg: false }
  ];

  // ==================== TRANSLATIONS ====================
  var T = {
    uz: {
      welcome_title: 'HURMATLI SAYOHATCHI,',
      welcome_text: "Turizm sohasini o'rganish va O'zbekistonning turizm yordamchi hisobini tuzish maqsadida o'tkazilayotgan ushbu so'rovnomada ishtirok etishingizni iltimos qilamiz. Mazkur so'rovnomaga kiritilgan barcha savollarga javob berish orqali bizga ko'maklashishingizni so'raymiz.",
      welcome_conf: "Javoblaringiz maxfiyligi O'zbekiston Respublikasining \"Rasmiy statistika to'g'risida\"gi Qonuni bilan kafolatlanadi.",
      start: 'BOSHLASH',
      back: '← Ortga', next: 'Keyingi →', finish: 'Yakunlash ✓',
      submitting: 'Saqlanmoqda…',
      submit_error: "Saqlash muvaffaqiyatsiz. Qayta urinib ko'ring.",
      gps_required: "So'rovnomani yuborish uchun joylashuv ruxsati majburiy. Iltimos, brauzerda GPS ruxsatini bering.",
      gps_unsupported: "Brauzeringiz GPS ni qo'llab-quvvatlamaydi. Zamonaviy brauzerdan foydalaning.",
      gps_acquiring: 'GPS olinmoqda…',
      error: 'Davom etishdan oldin javob tanlang yoki kiriting.',
      error_row12: "12-qator majburiy (Ko'rgazma/qayta sotish maqsadida tovar sotib olish tanlanganligi sababli). Summani kiriting.",
      q_of: 'Savol', of: 'dan', search: 'Davlat qidirish...',
      success_title: 'Rahmat!',
      success_sub: "Javoblaringiz muvaffaqiyatli saqlandi. Ushbu muhim so'rovnomani to'ldirgatingiz uchun minnatdormiz!"
    },
    ru: {
      welcome_title: 'УВАЖАЕМЫЙ ПУТЕШЕСТВЕННИК,',
      welcome_text: 'Просим Вас принять участие в данном обследовании. Оно проводится для изучения туристских поездок и составления вспомогательного счёта туризма Узбекистана. Ваши ответы будут использоваться только в статистических целях.',
      welcome_conf: 'Конфиденциальность Ваших ответов гарантируется Законом Республики Узбекистан «Об официальной статистике».',
      start: 'НАЧАТЬ',
      back: '← Назад', next: 'Далее →', finish: 'Завершить ✓',
      submitting: 'Сохранение…',
      submit_error: 'Не удалось сохранить. Попробуйте ещё раз.',
      gps_required: 'Для отправки анкеты требуется доступ к местоположению. Разрешите GPS в браузере и повторите.',
      gps_unsupported: 'Ваш браузер не поддерживает GPS. Используйте современный браузер.',
      gps_acquiring: 'Получение GPS…',
      error: 'Пожалуйста, выберите или введите ответ перед продолжением.',
      error_row12: 'Строка 12 обязательна (выбрана Выставка/покупка товаров). Введите сумму.',
      q_of: 'Вопрос', of: 'из', search: 'Поиск страны...',
      success_title: 'Спасибо!',
      success_sub: 'Ваши ответы успешно сохранены. Благодарим Вас за заполнение этой важной анкеты!'
    }
  };

  // ==================== SCREENING TEXT (Outbound) ====================
  var SC_TEXT = {
    uz: {
      header: '🔍 Filtr savollari',
      F1: 'F1. Xorijga safaringiz 12 oydan kam davom etdimi?',
      F2: 'F2. Siz quyidagi toifalardan biriga mansubmisiz: diplomat, konsullik xodimi, harbiy xizmatchi, qochqin yoki transport ekipaji aʼzosi?',
      F3: 'F3. Ushbu safaringiz Sizning xizmat vazifalaringizni bajarish bilan bogʼliqmi?',
      yes: 'Ha',
      no: "Yo'q",
      terminate: "Qiziqishingiz uchun rahmat. Afsuski, siz ushbu so'rovnomada qatnasha olmaysiz.",
      continueBtn: "Asosiy so'rovnomaga o'tish →",
      back: 'Bosh sahifaga qaytish',
    },
    ru: {
      header: '🔍 Отборочные вопросы',
      F1: 'A. Длилась ли Ваша поездка за рубеж менее 12 месяцев?',
      F2: 'B. Относитесь ли Вы к одной из следующих категорий: дипломат, консульское должностное лицо, военнослужащий, беженец или член экипажа транспортного средства?',
      F3: 'C. Связана ли данная поездка с выполнением Ваших служебных обязанностей?',
      yes: 'Да',
      no: 'Нет',
      terminate: 'Спасибо за интерес. К сожалению, Вы не можете участвовать в данном опросе.',
      continueBtn: 'Перейти к основной анкете →',
      back: 'Вернуться на главную',
    },
  };

  // ==================== SCREENING STATE ====================
  var scAnswers = { F1: null, F2: null, F3: null };
  var scTerminated = false;
  window.__scAnswers = scAnswers;

  // ==================== BUILD SEQUENCE ====================
  function buildSeq() {
    var seq = ['q1', 'q2'];
    var p = answers.q2;
    if (p === 'business') seq.push('q3');
    // Employment: q4, q10, q11, q12, q13, q14 — q5/q6/q7/q8/q9 olib tashlangan
    if (p === 'employment') {
      seq.push('q4', 'q10', 'q11', 'q12', 'q13', 'q14');
      return seq;
    }
    seq.push('q4');
    // 0 nights: q10, q11, q13, q14 (q12 yo'q, q5-q9 yo'q)
    if (answers.q4_val === 0) {
      seq.push('q10', 'q11', 'q13', 'q14');
      return seq;
    }
    seq.push('q5', 'q6');
    if (answers.q6 === 'yes') seq.push('q7', 'q8', 'q9');
    seq.push('q10', 'q11', 'q13', 'q14');
    return seq;
  }

  // ==================== NAVIGATION ====================
  function goTo(id) {
    document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
    var el = document.getElementById(id);
    if (el) el.classList.add('active');
    window.scrollTo(0, 0);
  }
  function scrollToTop() { window.scrollTo({ top: 0, behavior: 'smooth' }); }

  function setLanguage(lang) {
    currentLang = lang;
    document.querySelectorAll('.lang-tab').forEach(function (b) { b.classList.remove('active'); });
    var tab = document.getElementById('tab-' + lang);
    if (tab) tab.classList.add('active');
    var L = T[lang];
    var el = document.getElementById('welcome-title'); if (el) el.innerText = L.welcome_title;
    el = document.getElementById('welcome-text'); if (el) el.innerText = L.welcome_text;
    el = document.getElementById('welcome-conf'); if (el) el.innerText = L.welcome_conf;
    el = document.getElementById('start-btn'); if (el) el.innerText = L.start;
    // Filter sahifasi tarjimasini ham yangilash
    if (typeof scRender === 'function') {
      try { scRender(); } catch (e) { /* sahifa hali yuklanmagan */ }
    }
  }
  window.setLanguage = setLanguage;

  function startSurvey() {
    // Yangi mantiq: START → filter sahifasi (page-filter)
    resetAnswers();
    submitted = false;
    scReset();
    goTo('page-filter');
    window.scrollTo(0, 0);
  }
  window.startSurvey = startSurvey;

  // ==================== FILTER (SCREENING) LOGIC ====================
  function scReset() {
    scAnswers.F1 = null; scAnswers.F2 = null; scAnswers.F3 = null;
    scTerminated = false;
    scRender();
  }
  window.scReset = scReset;

  function scRender() {
    var tx = SC_TEXT[currentLang] || SC_TEXT.uz;
    var headerEl = document.getElementById('sc-header');
    if (headerEl) headerEl.textContent = tx.header;

    ['F1', 'F2', 'F3'].forEach(function (q) {
      var titleEl = document.getElementById('sc-title-' + q);
      if (titleEl) titleEl.textContent = tx[q];
      var yEl = document.getElementById('sc-' + q + '-yes');
      var nEl = document.getElementById('sc-' + q + '-no');
      if (yEl) { yEl.textContent = tx.yes; yEl.className = 'sc-yn-btn' + (scAnswers[q] === 'yes' ? ' sel-yes' : ''); }
      if (nEl) { nEl.textContent = tx.no;  nEl.className = 'sc-yn-btn' + (scAnswers[q] === 'no'  ? ' sel-no'  : ''); }
    });

    var qF2 = document.getElementById('sc-qF2');
    var qF3 = document.getElementById('sc-qF3');
    if (qF2) qF2.style.display = scAnswers.F1 === 'yes' ? '' : 'none';
    if (qF3) qF3.style.display = (scAnswers.F1 === 'yes' && scAnswers.F2 === 'yes') ? '' : 'none';

    var resultEl = document.getElementById('sc-result');
    if (!resultEl) return;
    resultEl.innerHTML = '';

    if (scTerminated) {
      resultEl.innerHTML = '<div class="sc-result-terminate">' + tx.terminate + '</div>';
      document.querySelectorAll('.sc-yn-btn').forEach(function (b) { b.classList.add('sc-disabled'); });
    } else if (
      (scAnswers.F1 === 'yes' && scAnswers.F2 === 'no') ||
      (scAnswers.F1 === 'yes' && scAnswers.F2 === 'yes' && scAnswers.F3 === 'no')
    ) {
      resultEl.innerHTML =
        '<div class="sc-result-eligible">' +
        '<button class="btn-sc-continue" onclick="startMainSurvey()">' + tx.continueBtn + '</button>' +
        '</div>';
    }

    var backLbl = document.getElementById('sc-back-label');
    if (backLbl) backLbl.textContent = tx.back;
  }
  window.scRender = scRender;

  function scAnswer(q, val) {
    if (scTerminated) return;
    scAnswers[q] = val;
    if (q === 'F1') { scAnswers.F2 = null; scAnswers.F3 = null; }
    if (q === 'F2') { scAnswers.F3 = null; }
    scTerminated = false;
    if (scAnswers.F1 === 'no') scTerminated = true;
    if (scAnswers.F1 === 'yes' && scAnswers.F2 === 'yes' && scAnswers.F3 === 'yes') scTerminated = true;
    scRender();
  }
  window.scAnswer = scAnswer;

  function startMainSurvey() {
    currentQIdx = 0;
    submitted = false;
    SURVEY_START_TS = Date.now();
    goTo('page-survey');
    renderSurvey();
    window.scrollTo(0, 0);
  }
  window.startMainSurvey = startMainSurvey;

  // Device fingerprint to'plash
  function getDeviceInfo() {
    var info = { ua: '', screen: '', platform: '', language: '', timezone: '' };
    try { info.ua = navigator.userAgent || ''; } catch (e) {}
    try { info.platform = navigator.platform || ''; } catch (e) {}
    try { info.language = navigator.language || ''; } catch (e) {}
    try {
      if (window.screen) info.screen = (screen.width || 0) + 'x' + (screen.height || 0);
    } catch (e) {}
    try {
      if (window.Intl && Intl.DateTimeFormat) {
        info.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      }
    } catch (e) {}
    try {
      info.touch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    } catch (e) { info.touch = false; }
    try { info.cores = navigator.hardwareConcurrency || 0; } catch (e) {}
    try { info.memory = navigator.deviceMemory || 0; } catch (e) {}
    return info;
  }
  function getFillDurationMs() {
    return Math.max(0, Date.now() - SURVEY_START_TS);
  }

  function scGoHome() { goTo('page-home'); }
  window.scGoHome = scGoHome;

  // Faqat staff uchun — joriy holatni o'chirib boshiga qaytadi
  function staffReset() {
    if (!CFG.isStaffView) return;
    var msg = currentLang === 'ru'
      ? 'Сбросить текущие ответы и начать новый опрос?'
      : "Hozirgi javoblarni o'chirib, yangi so'rovnomani boshlaymizmi?";
    if (!window.confirm(msg)) return;
    try { clearState(); } catch (e) {}
    resetAnswers();
    if (typeof scReset === 'function') {
      try { scReset(); } catch (e) {}
    }
    currentQIdx = 0;
    submitted = false;
    SURVEY_START_TS = Date.now();
    setLanguage(currentLang === 'ru' ? 'ru' : 'uz');
    goTo('page-home');
    window.scrollTo(0, 0);
  }
  window.staffReset = staffReset;

  function prevQuestion() {
    if (currentQIdx > 0) { currentQIdx--; renderSurvey(); scrollToTop(); }
  }
  window.prevQuestion = prevQuestion;

  function nextQuestion() {
    var seq = buildSeq(), qId = seq[currentQIdx];
    if (!validateQ(qId)) return;
    hideErr();
    if (currentQIdx < seq.length - 1) {
      currentQIdx++;
      renderSurvey();
      scrollToTop();
    } else {
      submitSurvey();
    }
  }
  window.nextQuestion = nextQuestion;

  function showErr(msg) {
    var el = document.getElementById('val-err');
    el.innerText = msg || T[currentLang].error;
    el.classList.add('show');
  }
  function hideErr() { document.getElementById('val-err').classList.remove('show'); }

  // ==================== VALIDATION ====================
  function validateQ(qId) {
    switch (qId) {
      case 'q1': if (!answers.q1) { showErr(); return false; } break;
      case 'q2': if (!answers.q2) { showErr(); return false; } break;
      case 'q3': if (!answers.q3) { showErr(); return false; } break;
      case 'q4':
        if (answers.q4_val === undefined || answers.q4_val === null || answers.q4_val === '') { showErr(); return false; }
        break;
      case 'q5': if (!answers.q5) { showErr(); return false; } break;
      case 'q6': if (!answers.q6) { showErr(); return false; } break;
      case 'q7': if (!answers.q7) { showErr(); return false; } break;
      case 'q8': if (!answers.q8) { showErr(); return false; } break;
      case 'q9':
        if (!answers.q9_amount) { showErr(); return false; }
        if (!answers.q9_currency) { showErr(); return false; }
        break;
      case 'q10':
        if (!answers.q10) { showErr(); return false; }
        if (answers.q10 === 'airplane' && !answers.q10_airline) { showErr(); return false; }
        break;
      case 'q11':
        if (!answers.q11) { showErr(); return false; }
        if (answers.q11 === 'airplane' && !answers.q11_airline) { showErr(); return false; }
        break;
      case 'q12': if (!answers.q12) { showErr(); return false; } break;
      case 'q13':
        if (!answers.q13_amount) { showErr(); return false; }
        if (!answers.q13_currency) { showErr(); return false; }
        break;
      case 'q14':
        if (answers.q3 === 'exhibition') {
          var r12 = answers.q14 && answers.q14['r12'];
          if (!r12 || (!r12.inPkg && !r12.amount)) { showErr(T[currentLang].error_row12); return false; }
        }
        break;
    }
    return true;
  }

  // ==================== RENDER ====================
  function renderSurvey() {
    var seq = buildSeq();
    var total = seq.length;
    var qid = seq[currentQIdx];
    var percent = Math.round(((currentQIdx + 1) / total) * 100);
    var pf = document.getElementById('prog-fill'); if (pf) pf.style.width = percent + '%';
    var pl = document.getElementById('prog-lbl'); if (pl) pl.innerHTML = (currentQIdx + 1) + ' / ' + total;
    var nextBtn = document.getElementById('btn-next');
    nextBtn.innerText = (currentQIdx === total - 1) ? T[currentLang].finish : T[currentLang].next;
    nextBtn.disabled = false;
    var prevBtn = document.getElementById('btn-prev');
    if (prevBtn) {
      prevBtn.innerText = T[currentLang].back;
      prevBtn.style.visibility = currentQIdx === 0 ? 'hidden' : 'visible';
    }
    document.getElementById('survey-body').innerHTML = (renderers[qid] || function () { return '<div>Error</div>'; })();
    document.querySelectorAll('#survey-body input, #survey-body select, #survey-body textarea').forEach(function (el) {
      el.addEventListener('input', saveState);
      el.addEventListener('change', saveState);
    });
    document.getElementById('val-err').classList.remove('show');
    saveState();
  }

  var renderers = {
    q1: rQ1, q2: rQ2, q3: rQ3, q4: rQ4, q5: rQ5, q6: rQ6, q7: rQ7,
    q8: rQ8, q9: rQ9, q10: rQ10, q11: rQ11, q12: rQ12, q13: rQ13, q14: rQ14
  };

  // ==================== HELPERS ====================
  function t(uz, ru) { return currentLang === 'ru' ? ru : uz; }
  function chip(n, total) {
    return '<div class="q-badge">' + T[currentLang].q_of + ' ' + n + ' / ' + total + '</div>';
  }
  function qTitle(uz, ru) { return '<div class="q-title">' + t(uz, ru) + '</div>'; }
  function qSub(uz, ru) { return '<div class="q-sub">' + t(uz, ru) + '</div>'; }
  function cList() { return currentLang === 'ru' ? COUNTRIES_RU : COUNTRIES_UZ; }

  function filterC(listId, val) {
    var v = (val || '').toLowerCase();
    document.querySelectorAll('#' + listId + ' .opt-item').forEach(function (el) {
      el.style.display = el.textContent.toLowerCase().includes(v) ? '' : 'none';
    });
  }
  window.filterC = filterC;

  function currSel(name, selVal) {
    var ph = currentLang === 'ru' ? '— Выберите валюту —' : '— Valyutani tanlang —';
    var opts = '<option value="" disabled' + (!selVal ? ' selected' : '') + ' hidden>' + ph + '</option>';
    opts += CURRENCIES.map(function (c) {
      return '<option value="' + c + '"' + (selVal === c ? ' selected' : '') + '>' + c + '</option>';
    }).join('');
    return '<select class="exp-sel" onchange="answers[\'' + name + '\']=this.value">' + opts + '</select>';
  }

  function pickSingle(qid, val, el) {
    answers[qid] = val;
    var list = el.closest('.opt-list');
    if (list) list.querySelectorAll('.opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  }
  window.pickSingle = pickSingle;

  // ==================== QUESTION RENDERERS ====================

  function rQ1() {
    var seq = buildSeq(), sel = answers.q1 || '', list = cList();
    return chip(1, seq.length) +
      qTitle("Safaringizning asosiy qismi qaysi davlatda bo'ldi?",
             'В какой стране преимущественно прошла Ваша поездка за рубеж?') +
      qSub('Faqat bitta javob belgilansin', 'Только один ответ') +
      '<div class="search-wrap"><span class="search-icon">🔍</span><input type="text" class="search-input" placeholder="' + T[currentLang].search + '" oninput="filterC(\'clist1\',this.value)"></div>' +
      '<div class="country-list" id="clist1">' +
      COUNTRIES_KEY.map(function (k, i) {
        return '<div class="opt-item' + (sel === k ? ' selected' : '') + '" onclick="selC1(this,\'' + k + '\')"><span class="opt-dot"></span>' + list[i] + '</div>';
      }).join('') + '</div>';
  }
  window.selC1 = function (el, k) {
    answers.q1 = k;
    document.querySelectorAll('#clist1 .opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ2() {
    var seq = buildSeq(), v = answers.q2 || '';
    var opts = [
      { val: 'leisure', uz: "Ta'til, dam olish va rekreatsiya", ru: 'Отдых, досуг и рекреация' },
      { val: 'friends', uz: "Do'stlar va qarindoshlarni ziyorat qilish", ru: 'Посещение друзей и родственников' },
      { val: 'business', uz: 'Tadbirkorlik va kasbiy maqsad (uchrashuvlar, konferentsiyalar, treninglar)', ru: 'Деловые и профессиональные цели (встречи, конференции, обучение)' },
      { val: 'education', uz: "Ta'lim olish va treninglar (12 oydan kam bo'lgan qisqa kurslar)", ru: 'Образование и обучение (краткосрочные курсы менее 12 месяцев)' },
      { val: 'health', uz: "Sog'liqni tiklash maqsadida tibbiy davolanish", ru: 'Лечение и получение медицинских услуг' },
      { val: 'religion', uz: 'Diniy maqsad va ziyorat', ru: 'Религиозные цели и паломничество' },
      { val: 'employment', uz: "Ishlash maqsadida / haq to'lanadigan mehnat faoliyati", ru: 'Трудоустройство / оплачиваемая работа за рубежом' },
      { val: 'other', uz: 'Boshqa, iltimos aniq yozing', ru: 'Другое, пожалуйста укажите' }
    ];
    return chip(2, seq.length) +
      qTitle("Xorijga safaringizning asosiy maqsadini ko'rsating?", 'Укажите основную цель Вашей поездки за рубеж?') +
      qSub("Iltimos, xorijga safaringizning asosiy maqsadini ifodalaydigan bitta variantni tanlang.",
           'Пожалуйста, выберите один вариант, который лучше всего описывает цель Вашей поездки.') +
      '<ul class="opt-list">' +
      opts.map(function (o) {
        return '<li class="opt-item' + (v === o.val ? ' selected' : '') + '" onclick="pickQ2(\'' + o.val + '\',this)"><span class="opt-dot"></span>' + t(o.uz, o.ru) + '</li>';
      }).join('') + '</ul>';
  }
  window.pickQ2 = function (val, el) {
    answers.q2 = val;
    // Reset dependent
    if (val !== 'business') delete answers.q3;
    document.querySelectorAll('#survey-body .opt-list .opt-item').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ3() {
    var seq = buildSeq(), v = answers.q3 || '';
    var opts = [
      { val: 'exhibition', uz: "Ko'rgazma / qayta sotish maqsadida tovar sotib olish", ru: 'Выставка / покупка товаров с целью перепродажи' },
      { val: 'corporate', uz: "Korporativ / ishbilarmonlik uchrashuvi, seminar, amaliy mashg'ulot yoki taqdimot", ru: 'Корпоративная/деловая встреча, семинар, тренинг или презентация' },
      { val: 'incentive', uz: "Korxona tomonidan tashkil etilgan rag'batlantiruvchi tur", ru: 'Поощрительная поездка, организованная предприятием/компанией' },
      { val: 'conference', uz: 'Konferentsiya, kongress, forum', ru: 'Конференция, конгресс, форум' }
    ];
    return chip(3, seq.length) +
      qTitle("Xorijga ishbilarmonlik/kasbiy safaringizning asosiy maqsadini belgilang?",
             'Какова основная цель Вашей деловой/профессиональной поездки за рубеж?') +
      qSub('Faqat bitta javob belgilansin', 'Только один ответ') +
      '<ul class="opt-list">' +
      opts.map(function (o) {
        return '<li class="opt-item' + (v === o.val ? ' selected' : '') + '" onclick="pickSingle(\'q3\',\'' + o.val + '\',this)"><span class="opt-dot"></span>' + t(o.uz, o.ru) + '</li>';
      }).join('') + '</ul>';
  }

  function rQ4() {
    var seq = buildSeq(), v = answers.q4_val;
    var note = '';
    if (v === 0) {
      note = '<div style="background:#fffaf0;border:1.5px solid var(--yellow,#f39c12);border-radius:10px;padding:10px 14px;font-size:13px;font-weight:600;color:#b7760a;margin-top:8px;">' +
        t("0 kun: to'g'ridan to'g'ri 10-savolga o'tadi", '0 ночей: переход к Вопросу 10') + '</div>';
    }
    return chip(4, seq.length) +
      qTitle("Xorijda necha kun bo'ldingiz?", 'Сколько ночей Вы провели за рубежом?') +
      qSub("Tunlar sonini kiriting (0 kiriting, agar kecha qolmagan bo'lsangiz).",
           'Введите количество ночей (введите 0, если не ночевали).') +
      '<input type="number" class="survey-input" min="0" value="' + (v !== undefined && v !== '' ? v : '') + '" placeholder="' + t('Tunlar soni...', 'Количество ночей...') + '" oninput="setQ4Val(this.value)">' +
      note;
  }
  window.setQ4Val = function (val) {
    var n = parseInt(val);
    answers.q4_val = isNaN(n) ? 0 : n;
    // Re-render to show/hide note
    if (answers.q4_val === 0 || (val === '' || val === undefined)) renderSurvey();
  };

  function rQ5() {
    var seq = buildSeq(), v = answers.q5 || '';
    var opts = [
      { val: 'hotel', uz: 'Mehmonxona, motel, xosting yoki mehmon uyi (pullik joylar)', ru: 'Гостиница, мотель, хостел или гостевой дом (платное коммерческое размещение)' },
      { val: 'rented', uz: 'Ijaraga olingan kvartira, uy yoki villa (masalan, Airbnb, xususiy ijara)', ru: 'Арендованная квартира, дом или вилла (например, Airbnb, частная аренда)' },
      { val: 'friends', uz: "Do'stlar yoki qarindoshlar uyida qolish (bepul)", ru: 'Проживание у друзей или родственников (бесплатно)' },
      { val: 'own', uz: "O'zingizga tegishli mulk yoki ikkinchi uy (tashrif buyurilgan davlatda)", ru: 'Собственная недвижимость или второй дом (в посещённой стране)' },
      { val: 'sanator', uz: "Sanatoriy, sog'lomlashtirish maskani yoki SPA muassasasi", ru: 'Санаторий, оздоровительный курорт или SPA-объект' },
      { val: 'camping', uz: 'Kemping / avtokemper', ru: 'Кемпинг / дом на колёсах' },
      { val: 'other', uz: 'Boshqa pullik joylashtirish vositalari', ru: 'Другое платное размещение' }
    ];
    return chip(5, seq.length) +
      qTitle("Xorijda bo'lgan davringizda asosan qanday joyda tunab qoldingiz?", 'Каким типом размещения Вы в основном пользовались во время пребывания за рубежом?') +
      qSub("Eng ko'p tunlagan joyni tanlang.", 'Выберите один вариант, где Вы провели наибольшее количество ночей.') +
      '<ul class="opt-list">' +
      opts.map(function (o) {
        return '<li class="opt-item' + (v === o.val ? ' selected' : '') + '" onclick="pickSingle(\'q5\',\'' + o.val + '\',this)"><span class="opt-dot"></span>' + t(o.uz, o.ru) + '</li>';
      }).join('') + '</ul>';
  }

  function rQ6() {
    var seq = buildSeq(), v = answers.q6 || '';
    return chip(6, seq.length) +
      qTitle("Xorijga safar qilish uchun tur paket xarid qildingizmi?", 'Приобретали ли Вы для этой поездки за рубеж пакетный тур?') +
      '<div class="yn-group">' +
      '<button class="yn-btn' + (v === 'yes' ? ' selected' : '') + '" onclick="pickYN(\'yes\',this)">✅ ' + t('Ha', 'Да') + '</button>' +
      '<button class="yn-btn' + (v === 'no' ? ' selected' : '') + '" onclick="pickYN(\'no\',this)">❌ ' + t("Yo'q", 'Нет') + '</button>' +
      '</div>';
  }
  window.pickYN = function (val, el) {
    answers.q6 = val;
    document.querySelectorAll('.yn-btn').forEach(function (b) { b.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ7() {
    var seq = buildSeq(), v = answers.q7 || '';
    return chip(7, seq.length) +
      qTitle("Tur paket jami necha tunni qamrab olgan?", 'Сколько ночей в общей сложности охватывал пакетный тур?') +
      '<input type="number" class="survey-input" min="1" value="' + v + '" placeholder="' + t('Tunlar soni...', 'Количество ночей...') + '" oninput="answers.q7=parseInt(this.value)||0">';
  }

  function rQ8() {
    var seq = buildSeq(), v = answers.q8 || '';
    return chip(8, seq.length) +
      qTitle("Siz bilan birga tur paket necha kishini qamrab olgan?",
             'На сколько человек, включая Вас, был рассчитан пакетный тур?') +
      '<input type="number" class="survey-input" min="1" value="' + v + '" placeholder="' + t('Kishilar soni...', 'Количество человек...') + '" oninput="answers.q8=parseInt(this.value)||0">';
  }

  function rQ9() {
    var seq = buildSeq();
    return chip(9, seq.length) +
      qTitle("Ushbu turpaket uchun qancha to'ladingiz?", 'Сколько Вы заплатили за этот тур?') +
      qSub("To'lov summasini va valyutasini ko'rsating.", 'Укажите сумму и валюту платежа.') +
      '<div class="inline-fields">' +
      '<input type="number" class="survey-input" style="flex:2;margin-bottom:0" min="0" value="' + (answers.q9_amount || '') + '" placeholder="' + t('Summa...', 'Сумма...') + '" oninput="answers.q9_amount=this.value">' +
      currSel('q9_currency', answers.q9_currency) +
      '</div>';
  }

  function rQ10() {
    var seq = buildSeq(), v = answers.q10 || '', al = answers.q10_airline || '';
    var sub = '';
    if (v === 'airplane') {
      sub = '<div class="sub-opts">' +
        '<div class="sub-opt' + (al === 'uzair' ? ' selected' : '') + '" onclick="pickAirline(\'q10\',\'uzair\',this)">✈️ ' + t("Uzbekistan Airways (O'zbek avialiniyasi)", 'Uzbekistan Airways (Узбекская авиакомпания)') + '</div>' +
        '<div class="sub-opt' + (al === 'other' ? ' selected' : '') + '" onclick="pickAirline(\'q10\',\'other\',this)">🌐 ' + t('Boshqa (chet el) aviakompaniyalar', 'Другие (неузбекские) авиакомпании') + '</div>' +
        '</div>';
    }
    return chip(10, seq.length) +
      qTitle("O'zbekistondan CHIQISH uchun qanday asosiy transport turidan foydalandingiz?",
             'Каким основным видом транспорта Вы воспользовались для ВЫЕЗДА из Узбекистана?') +
      qSub('Bitta asosiy variantni tanlang.', 'Пожалуйста, выберите один основной вариант.') +
      '<ul class="opt-list">' +
      '<li class="opt-item' + (v === 'airplane' ? ' selected' : '') + '" onclick="pickQ10(\'airplane\',this)"><span class="opt-dot"></span>✈️ ' + t('Samolyot', 'Самолёт') + '</li>' +
      (v === 'airplane' ? '<li style="padding:0;border:none;background:none;">' + sub + '</li>' : '') +
      '<li class="opt-item' + (v === 'train' ? ' selected' : '') + '" onclick="pickQ10(\'train\',this)"><span class="opt-dot"></span>🚂 ' + t('Poyezd', 'Поезд') + '</li>' +
      '<li class="opt-item' + (v === 'road' ? ' selected' : '') + '" onclick="pickQ10(\'road\',this)"><span class="opt-dot"></span>🚗 ' + t('Avtomobil transporti (avtomobil/avtobus/mototsikl)', 'Автомобильный транспорт (автомобиль/автобус/мотоцикл)') + '</li>' +
      '</ul>';
  }
  window.pickQ10 = function (val, el) {
    answers.q10 = val; answers.q10_airline = '';
    renderSurvey();
  };
  window.pickAirline = function (q, val, el) {
    answers[q + '_airline'] = val;
    el.closest('.sub-opts').querySelectorAll('.sub-opt').forEach(function (e) { e.classList.remove('selected'); });
    el.classList.add('selected');
  };

  function rQ11() {
    var seq = buildSeq(), v = answers.q11 || '', al = answers.q11_airline || '';
    var sub = '';
    if (v === 'airplane') {
      sub = '<div class="sub-opts">' +
        '<div class="sub-opt' + (al === 'uzair' ? ' selected' : '') + '" onclick="pickAirline(\'q11\',\'uzair\',this)">✈️ ' + t("Uzbekistan Airways (O'zbek avialiniyasi)", 'Uzbekistan Airways (Узбекская авиакомпания)') + '</div>' +
        '<div class="sub-opt' + (al === 'other' ? ' selected' : '') + '" onclick="pickAirline(\'q11\',\'other\',this)">🌐 ' + t('Boshqa (chet el) aviakompaniyalar', 'Другие (неузбекские) авиакомпании') + '</div>' +
        '</div>';
    }
    return chip(11, seq.length) +
      qTitle("O'zbekistonga QAYTISH uchun qanday asosiy transport turidan foydalandingiz?",
             'Каким основным видом транспорта Вы воспользовались для ПРИБЫТИЯ в Узбекистан?') +
      qSub('Bitta asosiy variantni tanlang.', 'Пожалуйста, выберите один основной вариант.') +
      '<ul class="opt-list">' +
      '<li class="opt-item' + (v === 'airplane' ? ' selected' : '') + '" onclick="pickQ11(\'airplane\',this)"><span class="opt-dot"></span>✈️ ' + t('Samolyot', 'Самолёт') + '</li>' +
      (v === 'airplane' ? '<li style="padding:0;border:none;background:none;">' + sub + '</li>' : '') +
      '<li class="opt-item' + (v === 'train' ? ' selected' : '') + '" onclick="pickQ11(\'train\',this)"><span class="opt-dot"></span>🚂 ' + t('Poyezd', 'Поезд') + '</li>' +
      '<li class="opt-item' + (v === 'road' ? ' selected' : '') + '" onclick="pickQ11(\'road\',this)"><span class="opt-dot"></span>🚗 ' + t('Avtomobil transporti (avtomobil/avtobus/mototsikl)', 'Автомобильный транспорт (автомобиль/автобус/мотоцикл)') + '</li>' +
      '</ul>';
  }
  window.pickQ11 = function (val, el) {
    answers.q11 = val; answers.q11_airline = '';
    renderSurvey();
  };

  function rQ12() {
    var seq = buildSeq(), v = answers.q12 || '';
    var optsUz = ['15% – 25%', '25% – 35%', '35% – 50%', "50% dan ko'proq"];
    var optsRu = ['15% – 25%', '25% – 35%', '35% – 50%', 'Более 50%'];
    var opts = currentLang === 'ru' ? optsRu : optsUz;
    var keys = ['lt25', '25to50', '50to75', 'gt75'];
    return chip(12, seq.length) +
      qTitle("Chet elda ishlash davrida oylik daromadingizning qancha qismini u yerda ovqat, uy ijarasi va mahalliy transport uchun sarfladim deb o'ylaysiz?",
             'В период работы за рубежом какую долю Вашего месячного дохода, по Вашей оценке, Вы тратите за рубежом на питание, аренду жилья и местный транспорт?') +
      qSub('Bitta variantni tanlang.', 'Пожалуйста, выберите один вариант.') +
      '<ul class="opt-list">' +
      opts.map(function (o, i) {
        return '<li class="opt-item' + (v === keys[i] ? ' selected' : '') + '" onclick="pickSingle(\'q12\',\'' + keys[i] + '\',this)"><span class="opt-dot"></span>' + o + '</li>';
      }).join('') + '</ul>';
  }

  function rQ13() {
    var seq = buildSeq();
    return chip(13, seq.length) +
      qTitle("Xorijga safaringiz davomida, barcha turdagi xarajatlar uchun tahminan qancha mablag' sarfladingiz?",
             'Какую общую сумму, по Вашей оценке, Вы потратили во время этой поездки за рубежом, включая все виды расходов, но исключая стоимость пакетного тура?') +
      qSub("Turpaket qiymatini qo'shmagan holda", 'Укажите сумме без стоимости пакетного тура.') +
      '<div class="inline-fields">' +
      '<input type="number" class="survey-input" style="flex:2;margin-bottom:0" min="0" value="' + (answers.q13_amount || '') + '" placeholder="' + t('Summa...', 'Сумма...') + '" oninput="answers.q13_amount=this.value">' +
      currSel('q13_currency', answers.q13_currency) +
      '</div>' +
      '<label class="field-label" style="margin-top:10px">' + t("Ushbu summa necha kishini qamrab oladi?", 'Количество лиц, охваченных этой суммой') + '</label>' +
      '<input type="number" class="survey-input" min="1" value="' + (answers.q13_persons || '') + '" placeholder="' + t('Kishilar soni...', 'Количество лиц...') + '" oninput="answers.q13_persons=parseInt(this.value)">';
  }

  function rQ14() {
    var seq = buildSeq();
    if (!answers.q14) answers.q14 = {};
    var isEmployment = (answers.q2 === 'employment');
    var showPkg = (answers.q6 === 'yes') && !isEmployment;
    // Q13 dan default valyuta — agar qator uchun yo'q bo'lsa, shu ishlatiladi
    var defaultCurrency = answers.q13_currency || '';
    var gridStyle = showPkg ? '1fr 36px 110px 80px' : '1fr 110px 80px';
    var headCols = showPkg
      ? '<div>' + t('Xarajat turi', 'Тип расхода') + '</div><div style="text-align:center">☑</div><div>' + t('Summa', 'Стоимость') + '</div><div>' + t('Valyuta', 'Валюта') + '</div>'
      : '<div>' + t('Xarajat turi', 'Тип расхода') + '</div><div>' + t('Summa', 'Стоимость') + '</div><div>' + t('Valyuta', 'Валюта') + '</div>';

    var rowsHtml = EXP_ROWS.map(function (row) {
      // Sub-rows (1.1, 1.2) faqat employment uchun
      if (row.sub && !isEmployment) return '';
      var r = answers.q14['r' + row.n] || {};
      var isMand = row.mand && (answers.q3 === 'exhibition');
      var checked = r.inPkg || false;
      var disabled = checked ? 'disabled' : '';
      var label = t(row.uz, row.ru);
      var hasChk = showPkg && row.pkg && !row.sub;
      var chkCell = hasChk
        ? '<div style="text-align:center"><input type="checkbox"' + (checked ? ' checked' : '') + ' onchange="toggleExpPkg(\'' + row.n + '\',this)"></div>'
        : (showPkg ? '<div></div>' : '');
      var rowClass = 'exp-row' + (row.sub ? ' subrow' : '') + (isMand ? ' mandatory-row' : '');
      // Effektiv valyuta: agar qatorda yo'q bo'lsa, Q13'dan
      var effectiveCurrency = r.currency || defaultCurrency;
      var hasExplicit = !!r.currency || !!defaultCurrency;
      return '<div class="' + rowClass + '" style="grid-template-columns:' + gridStyle + '">' +
        '<div><div class="exp-num">' + row.n + '.</div><div class="exp-name">' + label + (isMand ? ' ⭐' : '') + '</div></div>' +
        chkCell +
        '<input class="exp-inp' + (isMand ? ' mand' : '') + '" type="number" min="0" placeholder="' + t('Summa...', 'Сумма...') + '" value="' + (r.amount || '') + '" ' + disabled + ' oninput="setExp(\'' + row.n + '\',\'amount\',this.value)">' +
        '<select class="exp-sel" ' + disabled + ' onchange="setExp(\'' + row.n + '\',\'currency\',this.value)">' +
        '<option value="" disabled' + (!hasExplicit ? ' selected' : '') + ' hidden>—</option>' +
        CURRENCIES.map(function (c) { return '<option value="' + c + '"' + (effectiveCurrency === c ? ' selected' : '') + '>' + c + '</option>'; }).join('') + '</select>' +
        '</div>';
    }).join('');

    return chip(14, seq.length) +
      qTitle("Chet elda bo'lganingizda qanday xarajatlar qilganligingizni va ularning taxminiy qiymatini ko'rsating.",
             'Пожалуйста, укажите виды расходов, которые у Вас были за рубежом, и их примерную стоимость.') +
      (showPkg
        ? qSub("☑ = tur paket qiymatiga kiritilgan (1–6-qatorlar uchun). Belgilansa, summa va valyuta kiritib bo'lmaydi.",
               '☑ = включено в стоимость пакетного тура (строки 1–6). Если отмечено, сумма и валюта недоступны.')
        : '<div style="margin-bottom:14px"></div>') +
      '<div class="exp-wrap"><div class="exp-head" style="grid-template-columns:' + gridStyle + '">' + headCols + '</div>' + rowsHtml + '</div>';
  }
  window.toggleExpPkg = function (n, chk) {
    if (!answers.q14) answers.q14 = {};
    if (!answers.q14['r' + n]) answers.q14['r' + n] = {};
    answers.q14['r' + n].inPkg = chk.checked;
    if (chk.checked) {
      answers.q14['r' + n].amount = '';
      answers.q14['r' + n].currency = '';
    }
    var row = chk.closest('.exp-row');
    if (row) {
      var inp = row.querySelector('.exp-inp'), sel = row.querySelector('.exp-sel');
      if (inp) { inp.disabled = chk.checked; if (chk.checked) inp.value = ''; }
      if (sel) sel.disabled = chk.checked;
    }
  };
  window.setExp = function (n, field, val) {
    if (!answers.q14) answers.q14 = {};
    if (!answers.q14['r' + n]) answers.q14['r' + n] = {};
    answers.q14['r' + n][field] = val;
    // Summa kiritilsa va valyuta tanlanmagan bo'lsa — Q13 dan default valyutani saqlash
    if (field === 'amount' && val && !answers.q14['r' + n].currency && answers.q13_currency) {
      answers.q14['r' + n].currency = answers.q13_currency;
    }
  };

  // ============ GEOLOCATION ============
  function getLocation() {
    return new Promise(function (resolve) {
      if (!('geolocation' in navigator)) {
        resolve({ granted: false });
        return;
      }
      var timeoutId = setTimeout(function () { resolve({ granted: false, reason: 'timeout' }); }, 8000);
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
    nextBtn.innerText = T[currentLang].gps_acquiring;

    // Public (non-staff) submissions: GPS is optional
    if (!CFG.isStaffView) {
      nextBtn.innerText = T[currentLang].submitting;
      fetch(CFG.submitUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': CFG.csrfToken,
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          answers: answers,
          language: currentLang,
          location: null,
          screening: scAnswers,
          device_info: getDeviceInfo(),
          fill_duration_ms: getFillDurationMs(),
        }),
      }).then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      }).then(function (data) {
        if (data && data.ok) {
          clearState();
          document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
          document.getElementById('page-success').classList.add('active');
        } else { throw new Error('Server error'); }
      }).catch(function () {
        submitted = false;
        nextBtn.disabled = false;
        nextBtn.innerText = T[currentLang].finish;
        showErr(T[currentLang].submit_error);
      });
      return;
    }

    if (!('geolocation' in navigator)) {
      submitted = false;
      nextBtn.disabled = false;
      nextBtn.innerText = T[currentLang].finish;
      showErr(T[currentLang].gps_unsupported);
      return;
    }

    getLocation().then(function (location) {
      if (!location.granted) {
        submitted = false;
        nextBtn.disabled = false;
        nextBtn.innerText = T[currentLang].finish;
        showErr(T[currentLang].gps_required);
        return null;
      }
      nextBtn.innerText = T[currentLang].submitting;
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
          screening: scAnswers,
          device_info: getDeviceInfo(),
          fill_duration_ms: getFillDurationMs(),
        }),
      });
    }).then(function (res) {
      if (res === null) return null;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      if (data === null) return;
      if (data && data.ok) {
        clearState();
        document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
        document.getElementById('page-success').classList.add('active');
      } else { throw new Error('Server error'); }
    }).catch(function (err) {
      submitted = false;
      nextBtn.disabled = false;
      nextBtn.innerText = T[currentLang].finish;
      showErr(T[currentLang].submit_error);
    });
  }

  // ============ INIT — sessionStorage restore ============
  function init() {
    var saved = loadState();
    if (saved && saved.answers) {
      Object.keys(saved.answers).forEach(function (k) { answers[k] = saved.answers[k]; });
      currentLang = saved.currentLang || 'uz';
      currentQIdx = saved.currentQIdx || 0;
      setLanguage(currentLang);
      document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
      document.getElementById('page-survey').classList.add('active');
      renderSurvey();
    } else {
      setLanguage('uz');
    }
  }
  init();
})();
