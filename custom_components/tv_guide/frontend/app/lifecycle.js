/* Own every external listener, observer and timer for one connected card. */
export function createScope() {
  let active = true;
  let resizeFrame = null;
  const resizeCallbacks = new Set();
  const listeners = [], observers = [], intervals = [];
  const timeouts = new Set(), idle = new Set();
  const clearTimeout = id => { window.clearTimeout(id); timeouts.delete(id); };
  function setTimeout(callback, delay) {
    if (!active) return null;
    const id = window.setTimeout(() => { timeouts.delete(id); if(active)callback(); }, delay);
    timeouts.add(id); return id;
  }
  function pause() {
    if (!active) return;
    active = false;
    if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
    resizeFrame = null;
    resizeCallbacks.clear();
    for (const [target,type,handler,options] of listeners) target.removeEventListener(type,handler,options);
    for (const {observer} of observers) observer.disconnect();
    for (const entry of intervals) window.clearInterval(entry.id);
    for (const id of timeouts) window.clearTimeout(id);
    timeouts.clear();
    for (const id of idle) window.cancelIdleCallback(id);
    idle.clear();
  }
  function resume() {
    if (active) return;
    active = true;
    for (const args of listeners) args[0].addEventListener(...args.slice(1));
    for (const {observer,target} of observers) observer.observe(target);
    for (const entry of intervals) entry.id=window.setInterval(entry.callback,entry.delay);
  }
  return {
    setTimeout, clearTimeout, pause, resume,
    listen(target,type,handler,options) {
      listeners.push([target,type,handler,options]);
      if(active)target.addEventListener(type,handler,options);
    },
    observe(target,callback) {
      const observer = new ResizeObserver(()=>{
        if (!active) return;
        resizeCallbacks.add(callback);
        if (resizeFrame !== null) return;
        // Keep layout writes out of ResizeObserver delivery, and coalesce the
        // root/header observations into a single update per frame.
        resizeFrame = window.requestAnimationFrame(()=>{
          resizeFrame = null;
          const callbacks = [...resizeCallbacks];
          resizeCallbacks.clear();
          if (active) for (const update of callbacks) update();
        });
      });
      observers.push({observer,target}); if(active)observer.observe(target);
    },
    setInterval(callback,delay) {
      const entry={callback:()=>{if(active)callback();},delay};
      intervals.push(entry); if(active)entry.id=window.setInterval(entry.callback,delay);
    },
    idle(callback) {
      if (!active) return;
      if (!window.requestIdleCallback) {setTimeout(callback,0); return;}
      const id=window.requestIdleCallback(()=>{idle.delete(id);if(active)callback();},{timeout:3000});
      idle.add(id);
    }
  };
}
