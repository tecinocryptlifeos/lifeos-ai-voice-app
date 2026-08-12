"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../web/lifeos_voice/assets/lifeos_pwa_v1.js"),
  "utf8"
);

function executeShell({
  pathname = "/",
  search = "",
  standalone = false,
  referrer = "",
  hasMatchMedia = true,
} = {}) {
  const redirects = [];
  const store = new Map();
  const link = {
    tagName: "A",
    href: "/",
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
  const navigator = { standalone: false };
  const context = {
    URLSearchParams,
    console,
    navigator,
    location: {
      pathname,
      search,
      replace(value) { redirects.push(value); },
    },
    sessionStorage: {
      getItem(key) { return store.get(key) || null; },
      setItem(key, value) { store.set(key, String(value)); },
    },
    document: {
      referrer,
      readyState: "complete",
      documentElement: { dataset: {} },
      querySelectorAll() { return [link]; },
      addEventListener() {},
    },
  };
  context.window = context;
  context.window.navigator = navigator;
  context.window.addEventListener = () => {};
  if (hasMatchMedia) {
    context.window.matchMedia = () => ({ matches: standalone });
  }

  vm.runInNewContext(source, context, { filename: "lifeos_pwa_v1.js" });
  return { context, link, redirects };
}

const publicRoot = executeShell({ pathname: "/" });
assert.deepEqual(publicRoot.redirects, []);
assert.equal(publicRoot.context.LifeOSAppShell.isAppMode, false);
assert.equal(publicRoot.context.LifeOSAppShell.homeUrl, "/");
assert.equal(publicRoot.link.href, "/");

const pwaRoot = executeShell({ pathname: "/", search: "?source=pwa" });
assert.deepEqual(pwaRoot.redirects, ["/chat?source=app"]);
assert.equal(pwaRoot.context.LifeOSAppShell.isAppMode, true);

const appChat = executeShell({ pathname: "/chat", search: "?source=app" });
assert.deepEqual(appChat.redirects, []);
assert.equal(appChat.context.LifeOSAppShell.homeUrl, "/chat?source=app");
assert.equal(appChat.link.href, "/chat?source=app");

const androidRoot = executeShell({
  pathname: "/",
  referrer: "android-app://losia.htc.com/",
});
assert.deepEqual(androidRoot.redirects, ["/chat?source=app"]);

const legacyBrowser = executeShell({ pathname: "/", hasMatchMedia: false });
assert.deepEqual(legacyBrowser.redirects, []);

console.log("Sophia app-shell routing passed.");
