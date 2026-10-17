var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);
var stdin_exports = {};
__export(stdin_exports, {
  en: () => en,
  formatDesktopMessage: () => formatDesktopMessage,
  resolveDesktopLocale: () => resolveDesktopLocale,
  zh: () => zh
});
module.exports = __toCommonJS(stdin_exports);
const en = {
  application: "Application",
  startupFailed: "DeepSeek Harness could not start",
  pluginsMenu: "Desktop Plugins\u2026",
  pluginsMenuPackagedOnly: "Desktop Plugins\u2026 (available in packaged applications)",
  checkUpdatesMenu: "Check for Updates\u2026",
  updateCheckFailedTitle: "Update Check Failed",
  unknownError: "Unknown error",
  updateCheckTitle: "Check for Updates",
  updateCurrent: "You already have the latest version.",
  updateTitle: "DeepSeek Harness Update",
  updateAvailable: "An update is available",
  updateDetail: "DeepSeek Harness {version}\n\nThis release includes its matching dsh version. The application will restart after installation.",
  installAndRestart: "Install and Restart",
  later: "Later",
  updateFailedTitle: "Update Failed",
  pluginManagerTitle: "Desktop Plugins",
  pluginWindowTitle: "DeepSeek Harness \u2014 Desktop Plugins",
  pluginManagerDescription: "Plugins are installed only in the Desktop node_modules and are managed by the bundled pnpm.",
  refresh: "Refresh",
  npmPackage: "npm package",
  install: "Install",
  installed: "Installed",
  noPlugins: "No Desktop plugins are installed.",
  remove: "Remove",
  update: "Update",
  targetVersion: "Enter the target version for {name}",
  removing: "Removing {name}\u2026",
  updating: "Updating {name}\u2026",
  installing: "Installing {spec}\u2026",
  operationComplete: "Done. The Desktop backend has restarted.",
  refreshing: "Refreshing\u2026",
  refreshed: "Plugin list refreshed.",
  loadingPlugins: "Reading Desktop plugins\u2026"
};
const zh = {
  application: "\u5E94\u7528",
  startupFailed: "DeepSeek Harness \u65E0\u6CD5\u542F\u52A8",
  pluginsMenu: "\u684C\u9762\u63D2\u4EF6\u2026",
  pluginsMenuPackagedOnly: "\u684C\u9762\u63D2\u4EF6\u2026\uFF08\u6253\u5305\u5E94\u7528\u4E2D\u53EF\u7528\uFF09",
  checkUpdatesMenu: "\u68C0\u67E5\u66F4\u65B0\u2026",
  updateCheckFailedTitle: "\u66F4\u65B0\u68C0\u67E5\u5931\u8D25",
  unknownError: "\u672A\u77E5\u9519\u8BEF",
  updateCheckTitle: "\u68C0\u67E5\u66F4\u65B0",
  updateCurrent: "\u5F53\u524D\u5DF2\u662F\u6700\u65B0\u7248\u672C\u3002",
  updateTitle: "DeepSeek Harness \u66F4\u65B0",
  updateAvailable: "\u53D1\u73B0\u53EF\u7528\u66F4\u65B0",
  updateDetail: "DeepSeek Harness {version}\n\n\u65B0\u7248\u672C\u7ED1\u5B9A\u5339\u914D\u7684 dsh\uFF0C\u5B89\u88C5\u540E\u5C06\u91CD\u65B0\u542F\u52A8\u3002",
  installAndRestart: "\u5B89\u88C5\u5E76\u91CD\u542F",
  later: "\u7A0D\u540E",
  updateFailedTitle: "\u66F4\u65B0\u5931\u8D25",
  pluginManagerTitle: "\u684C\u9762\u63D2\u4EF6",
  pluginWindowTitle: "DeepSeek Harness \u2014 \u684C\u9762\u63D2\u4EF6",
  pluginManagerDescription: "\u63D2\u4EF6\u53EA\u5B89\u88C5\u5230\u684C\u9762\u7AEF\u81EA\u5DF1\u7684 node_modules\uFF0C\u5E76\u7531\u5185\u7F6E pnpm \u7BA1\u7406\u3002",
  refresh: "\u5237\u65B0",
  npmPackage: "npm \u5305",
  install: "\u5B89\u88C5",
  installed: "\u5DF2\u5B89\u88C5",
  noPlugins: "\u8FD8\u6CA1\u6709\u5B89\u88C5\u684C\u9762\u63D2\u4EF6\u3002",
  remove: "\u79FB\u9664",
  update: "\u66F4\u65B0",
  targetVersion: "\u8F93\u5165 {name} \u7684\u76EE\u6807\u7248\u672C",
  removing: "\u6B63\u5728\u79FB\u9664 {name}\u2026",
  updating: "\u6B63\u5728\u66F4\u65B0 {name}\u2026",
  installing: "\u6B63\u5728\u5B89\u88C5 {spec}\u2026",
  operationComplete: "\u64CD\u4F5C\u5B8C\u6210\uFF0C\u684C\u9762\u540E\u7AEF\u5DF2\u91CD\u65B0\u542F\u52A8\u3002",
  refreshing: "\u6B63\u5728\u5237\u65B0\u2026",
  refreshed: "\u63D2\u4EF6\u5217\u8868\u5DF2\u5237\u65B0\u3002",
  loadingPlugins: "\u6B63\u5728\u8BFB\u53D6\u684C\u9762\u63D2\u4EF6\u2026"
};
function resolveDesktopLocale(locale) {
  return locale.toLowerCase().startsWith("zh") ? { id: "zh-CN", messages: zh } : { id: "en", messages: en };
}
function formatDesktopMessage(message, values) {
  return message.replaceAll(/\{([^{}]+)\}/gu, (placeholder, key) => values[key] ?? placeholder);
}
