(() => {
  "use strict";

  const release = "lifeos-sophia-language-app-shell-v3.1.0-20260812";
  const APP_SESSION_KEY = "lifeos_app_shell_session_v1";
  const source = new URLSearchParams(location.search).get("source") || "";
  const launchedFromAppSource = /^(?:app|twa|pwa|pwa-shortcut)$/i.test(source);
  const standaloneDisplay =
    window.matchMedia?.("(display-mode: standalone)")?.matches === true ||
    window.matchMedia?.("(display-mode: fullscreen)")?.matches === true ||
    window.navigator.standalone === true;
  const trustedAndroidReferrer = /^android-app:\/\/losia\.htc\.com(?:\/|$)/i.test(
    document.referrer || ""
  );

  if (launchedFromAppSource || standaloneDisplay || trustedAndroidReferrer) {
    try {
      sessionStorage.setItem(APP_SESSION_KEY, "1");
    } catch (error) {}
  }

  let rememberedAppSession = false;
  try {
    rememberedAppSession = sessionStorage.getItem(APP_SESSION_KEY) === "1";
  } catch (error) {}

  const isAppMode =
    launchedFromAppSource ||
    standaloneDisplay ||
    trustedAndroidReferrer ||
    rememberedAppSession;
  const appHomeUrl = isAppMode ? "/chat?source=app" : "/";

  window.LifeOSAppShell = Object.freeze({
    isAppMode,
    homeUrl: appHomeUrl,
  });
  document.documentElement.dataset.lifeosAppMode = isAppMode ? "true" : "false";

  if (isAppMode && location.pathname === "/") {
    location.replace(appHomeUrl);
    return;
  }

  const preserveAppNavigation = () => {
    if (!isAppMode) return;
    document.querySelectorAll(".lifeos-home-logo-link-v1,[data-lifeos-app-home]")
      .forEach(link => {
        if (link.tagName === "A") link.href = appHomeUrl;
        link.setAttribute("aria-label", "Return to Sophia Decision Chat");
      });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", preserveAppNavigation, { once: true });
  } else {
    preserveAppNavigation();
  }

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", async () => {
    try {
      const registration = await navigator.serviceWorker.register(
        "/service-worker.js?v=" + encodeURIComponent(release),
        { updateViaCache: "none" }
      );
      await registration.update();
    } catch (error) {
      // Installation support must never prevent the public site from loading.
      console.warn("LifeOS mobile web app registration was unavailable.", error);
    }
  }, { once: true });
})();
