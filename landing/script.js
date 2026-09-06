const DEFAULT_LANGUAGE = "ko";
const STORAGE_KEY = "dashpi-language";
const toggle = document.querySelector(".language-toggle");
const dictionaryNode = document.querySelector("#translations");
const CUBE_COLUMNS = 40;
const CUBE_ROWS = 20;
const CUBE_SHADES = " .:-=+*#%@";
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
      const shade = Math.min(CUBE_SHADES.length - 1,
        Math.floor((0.22 + 0.78 * luminance) * (CUBE_SHADES.length - 1)));
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
    cube.textContent = renderClearboxCube(time * 0.00015);
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
