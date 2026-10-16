/* Explicit page links choose the language; remember it for legacy gallery links. */
(() => {
  const supported=document.currentScript?.dataset.languages?.split(' ');
  const normalize=value=>{
    const base=String(value||'').toLowerCase().replaceAll('_','-').split('-')[0];
    const code=base==='no'?'nb':base;
    return (supported?supported.includes(code):/^[a-z]{2}$/.test(code))?code:null;
  };
  const key='tv-guide-site-language';
  if(document.currentScript?.hasAttribute('data-gallery-entry')){
    let remembered,referrer;
    try{remembered=localStorage.getItem(key);}catch{}
    try{
      const source=new URL(document.referrer);
      if(source.origin===location.origin){
        const file=source.pathname.split('/').at(-1);
        referrer=(!file||file==='index.html')?'de':file.replace(/\.html$/,'');
      }
    }catch{}
    const language=normalize(new URLSearchParams(location.search).get('lang'))||normalize(referrer)||normalize(remembered)||
      (navigator.languages||[navigator.language]).map(normalize).find(Boolean)||'en';
    location.replace(new URL('screenshots/'+language+'.html',location.href));
    return;
  }
  try{const language=normalize(document.documentElement.lang);if(language)localStorage.setItem(key,language);}catch{}
})();
