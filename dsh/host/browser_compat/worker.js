/* Host adaptation for the pinned application's two explicitly owned Blob
 * workers. Copy the immutable original Blob before its caller revokes its URL;
 * prepend capabilities in the worker realm, preserving application bytes.
 * Unrecognized workers and compliant browser documents retain native behavior.
 */
(function(realmCode) {
  'use strict';
  if (typeof Worker !== 'function' || typeof Blob !== 'function') return;
  const key = Symbol.for('deepseek-win7.host.workers');
  if (globalThis[key]?.active) return;
  const NativeWorker = Worker, create = URL.createObjectURL, revoke = URL.revokeObjectURL;
  const terminate = NativeWorker.prototype.terminate;
  const blobs = new Map(), workers = new Map();
  const facts = {created: 0, terminated: 0, releasedUrls: 0, activeWorkers: 0, activeUrls: 0, errors: []};
  const manager = {active: true, facts, dispose};
  const createObjectURL = function createObjectURL(blob) {
    const url = Reflect.apply(create, URL, [blob]);
    if (blob instanceof Blob && /^(?:text|application)\/javascript(?:;|$)/i.test(blob.type)) blobs.set(url, blob);
    return url;
  };
  const revokeObjectURL = function revokeObjectURL(url) {
    if (!arguments.length) return Reflect.apply(revoke, URL, []);
    const value = String(url);
    blobs.delete(value);
    return Reflect.apply(revoke, URL, [value]);
  };
  const releaseWorker = worker => {
    const owned = workers.get(worker);
    if (!owned) return;
    owned.releaseUrl();owned.removeObservers();workers.delete(worker);facts.activeWorkers = workers.size;facts.terminated++;
  };
  const terminateWorker = function terminateWorker() {
    // Native brand errors must happen before releasing any owned resource.
    const result = Reflect.apply(terminate, this, []);
    releaseWorker(this);return result;
  };
  const Facade = new Proxy(NativeWorker, {
    construct(target, args, newTarget) {
      const [url, options] = args;
      const blob = typeof url === 'string' ? blobs.get(url) : undefined;
      if (!blob || !['dsh-pdf', 'dsh-file-upload'].includes(options?.name)) return Reflect.construct(target, args, newTarget);
      const adapted = new Blob([realmCode, '\n', blob], {type: 'text/javascript'});
      const ownedUrl = Reflect.apply(create, URL, [adapted]);
      facts.activeUrls++;
      let worker, released = false;
      const releaseUrl = () => {
        if (released) return;
        released = true;
        Reflect.apply(revoke, URL, [ownedUrl]);facts.activeUrls--;facts.releasedUrls++;
        worker?.removeEventListener('message', ready);
      };
      const ready = () => releaseUrl();
      const failed = event => {facts.errors.push({name: options.name, message: event.message ?? event.type,
        filename: event.filename ?? null, line: event.lineno ?? null, column: event.colno ?? null});releaseUrl();};
      const removeObservers = () => {
        worker.removeEventListener('error', failed);worker.removeEventListener('messageerror', failed);
      };
      try {
        worker = Reflect.construct(target, [ownedUrl, ...args.slice(1)], newTarget);
        workers.set(worker, {releaseUrl,removeObservers});facts.created++;facts.activeWorkers = workers.size;
        worker.addEventListener('message', ready, {once: true});
        worker.addEventListener('error', failed, {once: true});
        worker.addEventListener('messageerror', failed, {once: true});
        return worker;
      } catch (error) {releaseUrl();throw error;}
    },
  });
  URL.createObjectURL = createObjectURL;URL.revokeObjectURL = revokeObjectURL;
  NativeWorker.prototype.terminate = terminateWorker;
  globalThis.Worker = Facade;
  globalThis[key] = manager;
  function dispose() {
    if (!manager.active) return;
    manager.active = false;
    for (const worker of workers.keys()) {Reflect.apply(terminate, worker, []);releaseWorker(worker);}
    blobs.clear();
    if (globalThis.Worker === Facade) globalThis.Worker = NativeWorker;
    if (URL.createObjectURL === createObjectURL) URL.createObjectURL = create;
    if (URL.revokeObjectURL === revokeObjectURL) URL.revokeObjectURL = revoke;
    if (NativeWorker.prototype.terminate === terminateWorker) NativeWorker.prototype.terminate = terminate;
    if (globalThis[key] === manager) delete globalThis[key];
  }
})(__DSH_REALM_CODE__);
