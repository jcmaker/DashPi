const DEFAULT_LANGUAGE = "ko";
const STORAGE_KEY = "dashpi-language";
const toggle = document.querySelector(".language-toggle");
const dictionaryNode = document.querySelector("#translations");

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

let translations;
try {
  translations = JSON.parse(dictionaryNode.textContent);
  toggle.addEventListener("click", () => applyLanguage(document.documentElement.lang === "ko" ? "en" : "ko"));
  applyLanguage(storedLanguage());
} catch {
  toggle.dataset.state = "error";
  toggle.disabled = true;
}
