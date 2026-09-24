const DEFAULT_LANGUAGE = "ko";
const STORAGE_KEY = "dashpi-language";
const toggle = document.querySelector(".language-toggle");
const dictionaryNode = document.querySelector("#translations");
const CUBE_COLUMNS = 40;
const CUBE_ROWS = 20;
const CUBE_SHADES = " .,:;irsXA253hMHGS#9B&@";
const CUBE_ROTATION_PERIOD = 30000;
const cube = document.querySelector("[data-clearbox-cube]");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let previousFrameTime = 0;

function rotateClearboxVector(vector, xAngle, yAngle) {
  const xCos = Math.cos(xAngle);
  const xSin = Math.sin(xAngle);
  const yCos = Math.cos(yAngle);
  const ySin = Math.sin(yAngle);
  const afterX = {
    x: vector.x,
    y: vector.y * xCos - vector.z * xSin,
    z: vector.y * xSin + vector.z * xCos,
  };
  return {
    x: afterX.x * yCos + afterX.z * ySin,
    y: afterX.y,
    z: -afterX.x * ySin + afterX.z * yCos,
  };
}

function unrotateClearboxVector(vector, xAngle, yAngle) {
  const afterY = rotateClearboxVector(vector, 0, -yAngle);
  return rotateClearboxVector(afterY, -xAngle, 0);
}

function intersectClearboxCube(origin, direction) {
  let near = -Infinity;
  let far = Infinity;
  let hitAxis = "x";
  let hitSign = 0;

  for (const axis of ["x", "y", "z"]) {
    if (Math.abs(direction[axis]) < 1e-8) {
      if (Math.abs(origin[axis]) > 1) return null;
      continue;
    }

    let first = (-1 - origin[axis]) / direction[axis];
    let second = (1 - origin[axis]) / direction[axis];
    let sign = -1;
    if (first > second) {
      [first, second] = [second, first];
      sign = 1;
    }
    if (first > near) {
      near = first;
      hitAxis = axis;
      hitSign = sign;
    }
    far = Math.min(far, second);
    if (near > far) return null;
  }

  if (far < Math.max(near, 0)) return null;
  return {
    x: hitAxis === "x" ? hitSign : 0,
    y: hitAxis === "y" ? hitSign : 0,
    z: hitAxis === "z" ? hitSign : 0,
  };
}

function renderClearboxCube(angle) {
  const xAngle = -0.4;
  const yAngle = angle + 0.55;
  const ray = unrotateClearboxVector({ x: 0, y: 0, z: 1 }, xAngle, yAngle);
  const light = { x: -0.38, y: -0.65, z: -0.66 };
  const lines = [];

  for (let row = 0; row < CUBE_ROWS; row += 1) {
    let line = "";
    for (let column = 0; column < CUBE_COLUMNS; column += 1) {
      const origin = unrotateClearboxVector({
        x: (2 * (column + 0.5) / CUBE_COLUMNS - 1) * 2,
        y: (1 - 2 * (row + 0.5) / CUBE_ROWS) * 1.55,
        z: -4,
      }, xAngle, yAngle);
      const normal = intersectClearboxCube(origin, ray);
      if (!normal) {
        line += " ";
        continue;
      }

      const worldNormal = rotateClearboxVector(normal, xAngle, yAngle);
      const luminance = Math.max(0,
        worldNormal.x * light.x + worldNormal.y * light.y + worldNormal.z * light.z);
      const variation = ((column * 17 + row * 11) % 9 - 4) * 0.012;
      const lightLevel = Math.max(0, Math.min(1, 0.18 + 0.72 * luminance
        + 0.1 * (1 - row / CUBE_ROWS) + variation));
      const shade = Math.floor(lightLevel * (CUBE_SHADES.length - 1));
      line += CUBE_SHADES[shade];
    }
    lines.push(line);
  }

  return lines.join("\n");
}

function storedLanguage() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "en" || value === "ko" ? value : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

function saveLanguage(language) {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // The page still works for this session when storage is unavailable.
  }
}

function applyLanguage(language) {
  const locale = language === "en" ? "en" : DEFAULT_LANGUAGE;
  const messages = translations[locale] || translations[DEFAULT_LANGUAGE];
  toggle.dataset.state = "loading";

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = messages[node.dataset.i18n] ?? translations[DEFAULT_LANGUAGE][node.dataset.i18n];
    if (value) node.textContent = value;
  });
  document.querySelectorAll("[data-i18n-attr]").forEach((node) => {
    const [attribute, key] = node.dataset.i18nAttr.split(":", 2);
    const value = messages[key] ?? translations[DEFAULT_LANGUAGE][key];
    if (attribute && value) node.setAttribute(attribute, value);
  });

  document.documentElement.lang = locale;
  document.querySelectorAll("[data-ko-only]").forEach((node) => { node.hidden = locale !== "ko"; });
  toggle.textContent = locale === "ko" ? "EN" : "한국어";
  toggle.setAttribute("aria-pressed", String(locale === "en"));
  saveLanguage(locale);
  requestAnimationFrame(() => { toggle.dataset.state = "success"; });
}

function animateClearboxCube(time) {
  if (time - previousFrameTime >= 120) {
    cube.textContent = renderClearboxCube(time * Math.PI * 2 / CUBE_ROTATION_PERIOD);
    previousFrameTime = time;
  }
  requestAnimationFrame(animateClearboxCube);
}

let translations;
try {
  translations = JSON.parse(dictionaryNode.textContent);
  toggle.addEventListener("click", () => applyLanguage(document.documentElement.lang === "ko" ? "en" : "ko"));
  applyLanguage(storedLanguage());
} catch {
  toggle.dataset.state = "error";
  toggle.disabled = true;
}

if (cube) {
  cube.textContent = renderClearboxCube(0);
  if (!reducedMotion.matches) requestAnimationFrame(animateClearboxCube);
}

// Hero: record → incident → optical handoff → verified, the product's one-line story on a loop.
const handoff = document.querySelector("[data-handoff]");
const handoffCanvas = document.querySelector(".handoff-qr");
const HANDOFF_PHASES = [["record", 4200], ["incident", 1800], ["handoff", 4400], ["verified", 2200]];
const HANDOFF_CYCLE = HANDOFF_PHASES.reduce((total, [, duration]) => total + duration, 0);
const QR_MODULES = 29;

function drawQrFrame(context, seed, ink, paper) {
  let state = (seed * 2654435761) >>> 0 || 1;
  const random = () => {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
  const finders = [[0, 0], [0, QR_MODULES - 7], [QR_MODULES - 7, 0]];
  const inFinder = (row, column) => finders.some(([top, left]) =>
    row >= top - 1 && row <= top + 7 && column >= left - 1 && column <= left + 7);
  context.fillStyle = paper;
  context.fillRect(0, 0, QR_MODULES, QR_MODULES);
  context.fillStyle = ink;
  for (let row = 0; row < QR_MODULES; row += 1) {
    for (let column = 0; column < QR_MODULES; column += 1) {
      if (inFinder(row, column)) continue;
      const timing = (row === 6 || column === 6) && (row + column) % 2 === 0;
      if (timing || random() < 0.5) context.fillRect(column, row, 1, 1);
    }
  }
  for (const [top, left] of finders) {
    context.fillRect(left, top, 7, 7);
    context.fillStyle = paper;
    context.fillRect(left + 1, top + 1, 5, 5);
    context.fillStyle = ink;
    context.fillRect(left + 2, top + 2, 3, 3);
  }
}

function timecode(seconds) {
  const whole = Math.floor(seconds);
  return [whole / 3600, (whole % 3600) / 60, whole % 60]
    .map((part) => String(Math.floor(part)).padStart(2, "0")).join(":");
}

function startHandoff() {
  const context = handoffCanvas.getContext("2d");
  const ink = getComputedStyle(handoff).color;
  const paper = getComputedStyle(document.body).backgroundColor;
  const recordLabel = handoff.querySelector('[data-for="record"]');
  let frame = 0;
  let lastFrameTime = 0;
  drawQrFrame(context, frame, ink, paper);

  if (reducedMotion.matches) {
    handoff.dataset.phase = "verified";
    handoff.style.setProperty("--progress", "1");
    return;
  }

  const start = performance.now();
  function tick(now) {
    let local = (now - start) % HANDOFF_CYCLE;
    let index = 0;
    while (local >= HANDOFF_PHASES[index][1]) local -= HANDOFF_PHASES[index++][1];
    const [phase, duration] = HANDOFF_PHASES[index];
    if (handoff.dataset.phase !== phase) handoff.dataset.phase = phase;
    if (phase === "record") recordLabel.textContent = `REC ${timecode(754 + (now - start) / 1000)}`;
    const progress = phase === "handoff" ? local / duration : phase === "verified" ? 1 : 0;
    handoff.style.setProperty("--progress", progress.toFixed(3));
    if (phase === "handoff" && now - lastFrameTime >= 110) {
      drawQrFrame(context, (frame += 1), ink, paper);
      lastFrameTime = now;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

if (handoff && handoff.dataset && handoffCanvas && handoffCanvas.getContext) startHandoff();
