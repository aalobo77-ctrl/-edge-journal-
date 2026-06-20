(function(){'use strict';let overlay=null,input=null,results=null;
const cmds=[
  {l:'Dashboard',u:'/',k:'dashboard home'},
  {l:'Trades',u:'/trades',k:'trades all trades'},
  {l:'Analytics',u:'/analytics',k:'analytics stats metrics'},
  {l:'Calendar',u:'/calendar',k:'calendar performance days'},
  {l:'Oracle',u:'/oracle',k:'oracle ai coach grade chat'},
  {l:'Strategies',u:'/strategies',k:'strategies backtest exchange'},
  {l:'Notebook',u:'/notebook',k:'notebook journal notes'},
  {l:'Reports',u:'/reports',k:'reports export csv download'},
  {l:'Import',u:'/import',k:'import upload csv'},
  {l:'Settings',u:'/settings',k:'settings configure goals balance'},
  {l:'Add Trade',u:'/trade/add',k:'add trade new entry log create'},
];
function create(){
  overlay=document.createElement('div');
  overlay.id='cmd-overlay';
  overlay.style.cssText='display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);z-index:9999;align-items:flex-start;justify-content:center;padding-top:10vh;';
  overlay.onclick=e=>{if(e.target===overlay)hide();};
  const box=document.createElement('div');
  box.style.cssText='background:var(--card2);border:1px solid var(--border);border-radius:12px;width:500px;max-width:90vw;max-height:60vh;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5);';
  input=document.createElement('input');
  input.id='cmd-input';
  input.placeholder='Search pages... (Ctrl+K)';
  input.style.cssText='width:100%;padding:16px 20px;background:transparent;border:none;border-bottom:1px solid var(--border);color:var(--text1);font-size:15px;outline:none;box-sizing:border-box;';
  input.oninput=filter;
  input.onkeydown=e=>{if(e.key==='Escape')hide();if(e.key==='Enter'){const f=results?.querySelector('div[data-url]');if(f)window.location.href=f.dataset.url;}};
  results=document.createElement('div');
  results.id='cmd-results';
  results.style.cssText='overflow-y:auto;max-height:400px;';
  box.appendChild(input);box.appendChild(results);overlay.appendChild(box);document.body.appendChild(overlay);
  filter();
}
function filter(){
  const q=input.value.toLowerCase();
  const f=cmds.filter(c=>c.l.toLowerCase().includes(q)||c.k.includes(q));
  results.innerHTML=f.map(c=>`<div data-url="${c.u}" style="padding:12px 20px;cursor:pointer;border-bottom:1px solid var(--border);font-size:13px;display:flex;align-items:center;gap:10px;" onmouseover="this.style.background='var(--card3)'" onmouseout="this.style.background='transparent'" onclick="window.location.href='${c.u}'"><span style="width:6px;height:6px;border-radius:50%;background:var(--purple);display:inline-block;"></span>${c.l}</div>`).join('');
}
function show(){overlay.style.display='flex';setTimeout(()=>input.focus(),50);}
function hide(){overlay.style.display='none';input.value='';}
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();if(!overlay)create();show();}});
})();
