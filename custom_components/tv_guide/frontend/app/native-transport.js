/* RPC only to the embedding native card. No tokens, Ingress or add-on calls. */
(() => {
  const pending = new Map();
  let sequence = 0;
  window.addEventListener("message", event => {
    if (event.origin !== window.location.origin || event.source !== window.parent || event.data?.type !== "tv-guide-native-response") return;
    const request = pending.get(event.data.id);
    if (!request) return;
    pending.delete(event.data.id);
    clearTimeout(request.timer);
    if (event.data.error) request.reject(new Error(event.data.error));
    else request.resolve(event.data.response);
  });
  window.TVGuideNativeFetch = async (input, options={}) => {
    const url = new URL(input,window.location.href);
    const match = url.pathname.match(/^\/tv_guide\/frontend\/app\/api\/([a-z-]+)$/);
    if (!match || url.origin !== window.location.origin) throw new Error("Unsupported native TV Guide URL");
    const id = "native-"+(++sequence);
    const data = await new Promise((resolve,reject) => {
      const timer = setTimeout(() => {pending.delete(id);reject(new Error("Home Assistant request timed out"));},15000);
      pending.set(id,{resolve,reject,timer});
      window.parent.postMessage({type:"tv-guide-native-request",id,endpoint:match[1],method:options.method || "GET",at:url.searchParams.get("at"),body:options.body ? JSON.parse(options.body) : (url.searchParams.get("known_revision") ? {known_revision:url.searchParams.get("known_revision")} : null)},window.location.origin);
    });
    return {ok:true,json:async () => data};
  };
  window.addEventListener("pagehide",() => {for (const item of pending.values()) {clearTimeout(item.timer);item.reject(new Error("Card closed"));}pending.clear();});
})();
