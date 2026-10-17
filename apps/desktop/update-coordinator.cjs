"use strict";
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

// apps/desktop/src/update-coordinator.ts
var update_coordinator_exports = {};
__export(update_coordinator_exports, {
  DesktopUpdateCoordinator: () => DesktopUpdateCoordinator
});
module.exports = __toCommonJS(update_coordinator_exports);
var import_node_fs = require("node:fs");
var import_node_path = require("node:path");
var import_electron = require("electron");

// win7:injected-updater
var injected_updater_default = { autoUpdater: void 0 };

// apps/desktop/src/update-coordinator.ts
var { autoUpdater } = injected_updater_default;
var DesktopUpdateCoordinator = class {
  /**
   * @param publish - state sink for every desktop window.
   * @param beforeRestart - stop application-owned processes before replacement.
   * @param updater - Electron artifact updater; replaceable for tests.
   * @param enabled - whether this packaged process carries updater configuration.
   */
  constructor(publish, beforeRestart = async () => {
  }, updater = autoUpdater, enabled = () => import_electron.app.isPackaged && (0, import_node_fs.existsSync)((0, import_node_path.join)(process.resourcesPath, "app-update.yml"))) {
    this.publish = publish;
    this.beforeRestart = beforeRestart;
    this.updater = updater;
    this.enabled = enabled;
    this.updater.autoDownload = false;
    this.updater.autoInstallOnAppQuit = false;
  }
  availableVersion;
  checkOperation;
  installOperation;
  /** Check the configured Desktop release stream and retain an available version. */
  async check() {
    if (this.installOperation !== void 0) return this.installOperation;
    if (this.checkOperation !== void 0) return this.checkOperation;
    this.checkOperation = this.doCheck().finally(() => {
      this.checkOperation = void 0;
    });
    return this.checkOperation;
  }
  /** Wait for an in-flight check, then download and install its retained release. */
  async install() {
    if (this.installOperation !== void 0) return this.installOperation;
    this.installOperation = (async () => {
      await this.checkOperation;
      return this.doInstall();
    })().finally(() => {
      this.installOperation = void 0;
    });
    return this.installOperation;
  }
  async doCheck() {
    this.publish({ phase: "checking" });
    try {
      if (!this.enabled()) {
        this.availableVersion = void 0;
        return this.publish({ phase: "idle" });
      }
      const result = await this.updater.checkForUpdates();
      const version = result?.isUpdateAvailable === true ? result.updateInfo.version : void 0;
      this.availableVersion = version;
      return version === void 0 ? this.publish({ phase: "idle" }) : this.publish({ phase: "available", version });
    } catch (error) {
      this.availableVersion = void 0;
      return this.publish({
        phase: "error",
        message: error instanceof Error ? error.message : String(error)
      });
    }
  }
  async doInstall() {
    const version = this.availableVersion;
    if (version === void 0) {
      throw new Error("desktop update: no verified update is available");
    }
    this.publish({ phase: "installing", version });
    try {
      await this.updater.downloadUpdate();
      this.availableVersion = void 0;
      const ready = this.publish({ phase: "ready", version });
      await this.beforeRestart();
      this.updater.quitAndInstall(false, true);
      return ready;
    } catch (error) {
      return this.publish({
        phase: "error",
        version,
        message: error instanceof Error ? error.message : String(error)
      });
    }
  }
};
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  DesktopUpdateCoordinator
});
