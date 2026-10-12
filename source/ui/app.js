/* BoatGen interface logic */
(function () {
  "use strict";

  const I18N = {
    ru: {
      w_title: "Генератор лодок для Brick Rigs",
      w_lead: "BoatGen собирает готовую постройку — катер или лодку — со всеми механизмами и сохраняет её папкой, которую можно сразу открыть в игре.",
      w_s1: "Выберите тип, размер, детализацию и цвет", w_s2: "Посмотрите лодку в 3D и при желании сгенерируйте другой вариант",
      w_s3: "Заберите папку с постройкой и положите её в папку транспорта игры", w_lang: "Язык интерфейса", w_start: "Начать",
      m_title: "Параметры лодки", m_sub: "Выберите четыре параметра и нажмите «Создать».", m_type: "Тип лодки", m_size: "Размер",
      m_detail: "Детализация", m_color: "Цвет",
      k_motor: "Моторная лодка", k_motor_d: "Открытая, с пультом управления и подвесным мотором",
      k_cutter: "Простой катер", k_cutter_d: "Катер с рубкой, дверью и стабилизаторами",
      k_military: "Военный катер", k_military_d: "Патрульный катер с управляемой пушкой и дверями",
      sz_S: "Малый", sz_M: "Средний", sz_L: "Большой", d_low: "Низкая", d_med: "Средняя", d_high: "Высокая", bricks_short: "бр.",
      c_dark: "Тёмный", c_greyblue: "Серо-синий", c_light: "Светлый", ok_create: "Создать",
      p_warn: "Если что-то сгенерировалось или работает неправильно и вы не можете исправить это сами — просто сгенерируйте лодку заново.",
      p_hint: "Тяните мышью — вращать · колесо — масштаб · двойной клик — сброс", p_loading: "Собираю лодку…",
      p_controls: "Управление в игре", b_back: "Назад", b_reroll: "Другой вариант", b_ok: "ОК, сохранить",
      d_title: "Готово!", d_sub: "Постройка сохранена в папку:", t_h: "Куда положить папку",
      t_1: "Скопируйте папку с лодкой целиком в папку транспорта Brick Rigs:",
      t_2: "Быстро открыть: Win + R → введите %LOCALAPPDATA%\\BrickRigs → SavedRemastered → Vehicles. Или в игре нажмите «Открыть папку» у любой своей постройки.",
      t_3: "После этого лодка появится в списке построек (иногда нужно перезапустить игру).",
      b_open: "Открыть папку", b_copy: "Скопировать в Brick Rigs", b_home: "В главное меню",
      st_len: "Длина", st_beam: "Ширина", st_bricks: "Кирпичей", st_mass: "Масса ≈", st_sections: "Секций пайки", st_draft: "Осадка",
      m_unit: "м", t_unit: "т", cm_unit: "см",
      sum: "{kind} · {size} · {detail} детализация · {color}",
      copied: "Скопировано в папку игры", copy_fail: "Не удалось скопировать: ", no_game: "Папка игры не найдена — перенесите папку вручную (см. «⋯»)",
      support: "Можете поддержать меня подарками в Steam", sound: "Звук", fullscreen: "Во весь экран (F11)",
      st_engines: "Моторов", st_stab: "Стабилизаторы",
      gen_fail: "Ошибка генерации: ", save_fail: "Не удалось сохранить: ", no_webgl: "3D-превью недоступно на этом компьютере, но лодка сгенерирована.",
    },
    en: {
      w_title: "Boat generator for Brick Rigs",
      w_lead: "BoatGen builds a ready-to-drive creation — a boat or a patrol craft — with all its mechanisms, and saves it as a folder you can open in the game right away.",
      w_s1: "Pick the type, size, detail level and colour", w_s2: "Inspect the boat in 3D and roll another variant if you like",
      w_s3: "Take the vehicle folder and drop it into the game's vehicles folder", w_lang: "Interface language", w_start: "Start",
      m_title: "Boat settings", m_sub: "Choose the four options and press “Create”.", m_type: "Boat type", m_size: "Size",
      m_detail: "Detail", m_color: "Colour",
      k_motor: "Motor boat", k_motor_d: "Open boat with a centre console and an outboard",
      k_cutter: "Cabin cruiser", k_cutter_d: "Cabin boat with a door and stabilisers",
      k_military: "Patrol boat", k_military_d: "Armed patrol boat with an aimable gun and doors",
      sz_S: "Small", sz_M: "Medium", sz_L: "Large", d_low: "Low", d_med: "Medium", d_high: "High", bricks_short: "bricks",
      c_dark: "Dark", c_greyblue: "Grey-blue", c_light: "Light", ok_create: "Create",
      p_warn: "If something was generated or works wrong and you can't fix it yourself — just generate the boat again.",
      p_hint: "Drag to rotate · wheel to zoom · double-click to reset", p_loading: "Building the boat…",
      p_controls: "In-game controls", b_back: "Back", b_reroll: "Another variant", b_ok: "OK, save",
      d_title: "Done!", d_sub: "The creation was saved to:", t_h: "Where to put the folder",
      t_1: "Copy the whole boat folder into the Brick Rigs vehicles folder:",
      t_2: "Quick way: Win + R → type %LOCALAPPDATA%\\BrickRigs → SavedRemastered → Vehicles. Or press “Open folder” on any of your creations in the game.",
      t_3: "The boat then shows up in your creations list (sometimes the game needs a restart).",
      b_open: "Open folder", b_copy: "Copy to Brick Rigs", b_home: "Main menu",
      st_len: "Length", st_beam: "Beam", st_bricks: "Bricks", st_mass: "Mass ≈", st_sections: "Weld sections", st_draft: "Draft",
      m_unit: "m", t_unit: "t", cm_unit: "cm",
      sum: "{kind} · {size} · {detail} detail · {color}",
      copied: "Copied to the game folder", copy_fail: "Copy failed: ", no_game: "Game folder not found — move the folder manually (see “⋯”)",
      support: "You can support me with gifts on Steam", sound: "Sound", fullscreen: "Full screen (F11)",
      st_engines: "Engines", st_stab: "Stabilisers",
      gen_fail: "Generation error: ", save_fail: "Could not save: ", no_webgl: "3D preview is not available on this PC, but the boat was generated.",
    },
  };
  const DIMS = {
    motor: { S: [4.2, 1.7], M: [5.0, 2.05], L: [6.0, 2.4] },
    cutter: { S: [6.5, 2.4], M: [8.0, 2.75], L: [9.5, 3.15] },
    military: { S: [9.0, 3.0], M: [11.0, 3.4], L: [13.0, 3.9] },
  };

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const state = { lang: "ru", kind: "military", size: "M", detail: "med", color: "dark", screen: "welcome", busy: false, result: null, saved: null, game_found: false, game_dir: "" };

  // ------------------------------------------------------------------ backend bridge
  const BROWSER = new URLSearchParams(location.search).has("browser");
  function api(name, ...args) {
    if (!BROWSER && window.pywebview && window.pywebview.api && window.pywebview.api[name]) return window.pywebview.api[name](...args);
    if (!BROWSER) return Promise.resolve(null);
    return fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(args) }).then((r) => r.json());
  }
  function ready() {
    return new Promise((res) => {
      if (BROWSER || (window.pywebview && window.pywebview.api)) return res();
      window.addEventListener("pywebviewready", () => res());
    });
  }

  // ------------------------------------------------------------------ sounds (synthesised, quiet)
  const sfx = (function () {
    let ctx = null, muted = false;
    try { muted = localStorage.getItem("bg_muted") === "1"; } catch (e) {}
    function ac() {
      if (!ctx) { try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return null; } }
      if (ctx.state === "suspended") ctx.resume();
      return ctx;
    }
    function tone(freq, dur, type, vol, when, slide) {
      const c = ac(); if (!c || muted) return;
      const t = c.currentTime + (when || 0);
      const o = c.createOscillator(), g = c.createGain();
      o.type = type || "sine"; o.frequency.setValueAtTime(freq, t);
      if (slide) o.frequency.exponentialRampToValueAtTime(slide, t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(vol || 0.05, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + dur + 0.02);
    }
    function noise(dur, vol, from, to) {
      const c = ac(); if (!c || muted) return;
      const n = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
      const src = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
      src.buffer = buf; f.type = "bandpass"; f.Q.value = 0.8;
      f.frequency.setValueAtTime(from, c.currentTime); f.frequency.exponentialRampToValueAtTime(to, c.currentTime + dur);
      g.gain.value = vol; src.connect(f); f.connect(g); g.connect(c.destination); src.start();
    }
    return {
      click() { tone(620, 0.06, "triangle", 0.035); },
      select() { tone(520, 0.07, "sine", 0.04); tone(780, 0.09, "sine", 0.03, 0.035); },
      whoosh() { noise(0.28, 0.035, 500, 2400); },
      done() { [523, 659, 784].forEach((f, i) => tone(f, 0.22, "sine", 0.045, i * 0.09)); },
      error() { tone(260, 0.16, "triangle", 0.05, 0, 180); },
      get muted() { return muted; },
      toggle() { muted = !muted; try { localStorage.setItem("bg_muted", muted ? "1" : "0"); } catch (e) {} return muted; },
    };
  })();

  // ------------------------------------------------------------------ i18n
  const t = (k) => (I18N[state.lang] || I18N.ru)[k] || k;
  function applyLang() {
    document.documentElement.lang = state.lang;
    $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
    $$("#langSeg button").forEach((b) => b.classList.toggle("sel", b.dataset.lang === state.lang));
    $("#langMini").textContent = state.lang.toUpperCase();
    $("#soundBtn").title = t("sound"); $("#fsBtn").title = t("fullscreen");
    updateDims(); updateSummary();
    if (state.result) renderInfo(state.result);
  }
  function setLang(l) {
    state.lang = l; applyLang(); api("set_lang", l);
  }

  // ------------------------------------------------------------------ screens
  const ORDER = ["welcome", "menu", "preview", "done"];
  function go(name) {
    const cur = $("#s-" + state.screen), nxt = $("#s-" + name);
    if (cur && cur !== nxt) {
      cur.classList.add("leave"); cur.classList.remove("active");
      setTimeout(() => cur.classList.remove("leave"), 600);
    }
    nxt.classList.add("active");
    if (state.screen !== name) sfx.whoosh();
    state.screen = name;
    const idx = ORDER.indexOf(name);
    $$("#steps i").forEach((el, i) => { el.className = i === idx ? "on" : i < idx ? "past" : ""; });
  }

  // ------------------------------------------------------------------ menu
  function pick(groupSel, key) {
    $$(groupSel + " [data-v]").forEach((b) => {
      b.addEventListener("click", () => {
        state[key] = b.dataset.v; syncSel(); updateDims(); updateSummary(); sfx.select();
      });
    });
  }
  function syncSel() {
    for (const [sel, key] of [["#kindCards", "kind"], ["#sizeSeg", "size"], ["#detailSeg", "detail"], ["#colorCards", "color"]])
      $$(sel + " [data-v]").forEach((b) => b.classList.toggle("sel", b.dataset.v === state[key]));
  }
  function updateDims() {
    $$("#sizeSeg button").forEach((b) => {
      const d = DIMS[state.kind][b.dataset.v];
      b.querySelector(".dim").textContent = "≈ " + d[0].toFixed(1) + " × " + d[1].toFixed(1) + " " + t("m_unit");
    });
  }
  function updateSummary() {
    const s = t("sum").replace("{kind}", "<b>" + t("k_" + state.kind) + "</b>").replace("{size}", t("sz_" + state.size))
      .replace("{detail}", t("d_" + state.detail).toLowerCase()).replace("{color}", t("c_" + state.color).toLowerCase());
    $("#summary").innerHTML = s;
  }

  // ------------------------------------------------------------------ preview
  let viewer = null;
  function ensureViewer() {
    if (viewer) return viewer;
    try { viewer = new window.BoatViewer($("#gl")); if (!viewer.gl) throw new Error("no webgl"); }
    catch (e) { viewer = { gl: null, setScene() {}, capture() { return null; }, reset() {} }; toast(t("no_webgl"), true); }
    return viewer;
  }
  function stat(label, value, full) {
    return '<div class="stat' + (full ? " full" : "") + '"><small>' + label + "</small><b>" + value + "</b></div>";
  }
  function renderInfo(r) {
    const i = r.info;
    $("#boatName").textContent = r.name;
    $("#stats").innerHTML = stat(t("st_len"), i.length.toFixed(2) + " " + t("m_unit")) + stat(t("st_beam"), i.beam.toFixed(2) + " " + t("m_unit")) +
      stat(t("st_bricks"), i.bricks) + stat(t("st_mass"), i.mass + " " + t("t_unit")) + stat(t("st_sections"), i.sections) + stat(t("st_draft"), Math.round(i.draft) + " " + t("cm_unit")) +
      (i.engines ? stat(t("st_engines"), i.engines) : "") + (i.stab ? stat(t("st_stab"), i.stab) : "");
    $$("#stats .stat").forEach((el, k) => { el.style.animationDelay = k * 0.04 + "s"; });
    $("#controls").innerHTML = (r.controls || []).map((c) => "<li>" + c + "</li>").join("");
  }
  async function generate() {
    if (state.busy) return;
    state.busy = true;
    $("#loader").classList.add("on");
    setButtons(false);
    const t0 = performance.now();
    try {
      const r = await api("generate", { kind: state.kind, size: state.size, detail: state.detail, color: state.color, lang: state.lang });
      const wait = 450 - (performance.now() - t0);
      if (wait > 0) await new Promise((res) => setTimeout(res, wait));
      if (!r || !r.ok) throw new Error(r ? r.error : "no answer");
      state.result = r;
      const v = ensureViewer();
      v.setScene(r.scene, r.info.draft);
      if (v.reset) v.reset();
      renderInfo(r);
    } catch (e) {
      toast(t("gen_fail") + e.message, true); sfx.error();
    } finally {
      state.busy = false;
      $("#loader").classList.remove("on");
      setButtons(true);
    }
  }
  function setButtons(on) {
    for (const id of ["#okPreview", "#rerollBtn", "#backBtn"]) $(id).disabled = !on;
  }

  async function save() {
    if (state.busy || !state.result) return;
    state.busy = true; setButtons(false);
    try {
      let png = null;
      try { png = ensureViewer().capture(256); } catch (e) { png = null; }
      const r = await api("save", png);
      if (!r || !r.ok) throw new Error(r ? r.error : "no answer");
      state.saved = r;
      state.game_found = r.game_found;
      $("#savedPath").textContent = r.path;
      $("#gameDir").textContent = r.game_dir || "%LOCALAPPDATA%\\BrickRigs\\SavedRemastered\\Vehicles";
      $("#copyBtn").style.display = r.game_found ? "" : "none";
      $("#copyBtn").disabled = false;
      go("done"); setTimeout(sfx.done, 250);
    } catch (e) {
      toast(t("save_fail") + e.message, true); sfx.error();
    } finally {
      state.busy = false; setButtons(true);
    }
  }

  // ------------------------------------------------------------------ toast
  let toastTimer = null;
  function toast(msg, err) {
    const el = $("#toast");
    el.textContent = msg; el.classList.toggle("err", !!err); el.classList.add("on");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("on"), 3600);
  }

  // ------------------------------------------------------------------ wiring
  function init() {
    // tick marks on cards
    $$(".card").forEach((c) => c.insertAdjacentHTML("beforeend", '<span class="tick"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>'));
    $$("#langSeg button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
    $("#langMini").addEventListener("click", () => setLang(state.lang === "ru" ? "en" : "ru"));
    $("#startBtn").addEventListener("click", () => go("menu"));
    pick("#kindCards", "kind"); pick("#sizeSeg", "size"); pick("#detailSeg", "detail"); pick("#colorCards", "color");
    $("#okMenu").addEventListener("click", () => { go("preview"); ensureViewer(); setTimeout(generate, 120); });
    $("#backBtn").addEventListener("click", () => go("menu"));
    $("#rerollBtn").addEventListener("click", generate);
    $("#okPreview").addEventListener("click", save);
    $("#homeBtn").addEventListener("click", () => go("menu"));
    $("#openBtn").addEventListener("click", () => api("open_folder", state.saved ? state.saved.path : null));
    $("#copyBtn").addEventListener("click", async () => {
      const r = await api("copy_to_game");
      if (r && r.ok) { toast(t("copied") + ": " + r.path); $("#copyBtn").disabled = true; }
      else toast(r && r.error === "game folder not found" ? t("no_game") : t("copy_fail") + (r ? r.error : ""), true);
    });
    // buttons click softly
    document.addEventListener("click", (e) => { if (e.target.closest(".btn, .icon-btn, .lang-mini, #langSeg button")) sfx.click(); });
    $("#soundBtn").classList.toggle("muted", sfx.muted);
    $("#soundBtn").addEventListener("click", () => { $("#soundBtn").classList.toggle("muted", sfx.toggle()); });
    // full screen: F11 / button / Esc
    async function fullscreen(force) {
      const r = await api("toggle_fullscreen").catch(() => null);
      if (r === true) return;
      try {                                               // browser fallback
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (force !== false) await document.documentElement.requestFullscreen();
      } catch (e) {}
    }
    $("#fsBtn").addEventListener("click", () => fullscreen());
    // Steam link: open in the system browser
    $$(".support").forEach((a) => a.addEventListener("click", async (e) => {
      e.preventDefault();
      sfx.click();
      const ok = await api("open_url", a.href).catch(() => false);
      if (!ok) window.open(a.href, "_blank", "noopener");
    }));
    document.addEventListener("keydown", (e) => {
      if (e.key === "F11") { e.preventDefault(); fullscreen(); return; }
      if (e.key === "Escape") { api("exit_fullscreen").catch(() => null); return; }
      if (e.key !== "Enter" || state.busy) return;
      if (state.screen === "welcome") $("#startBtn").click();
      else if (state.screen === "menu") $("#okMenu").click();
    });
    syncSel(); applyLang(); go("welcome");
    ready().then(() => api("get_state")).then((s) => {
      if (!s) return;
      state.lang = s.lang || "ru";
      if (s.last) for (const k of ["kind", "size", "detail", "color"]) if (s.last[k]) state[k] = s.last[k];
      state.game_found = s.game_found; state.game_dir = s.game_dir;
      $("#gameDir").textContent = s.game_dir;
      syncSel(); applyLang();
    }).catch(() => {});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.__boatgen = { state, go, generate, save };
})();
