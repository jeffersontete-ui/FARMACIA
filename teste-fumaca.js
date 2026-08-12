/* Teste de fumaça — roda os dois app.js num DOM simulado.
   Objetivo: pegar erro de sintaxe, id de elemento que não existe no HTML
   e regressão nas funções de validade e busca, antes de publicar.

   uso: node teste-fumaca.js            (a partir da pasta do app)
        node teste-fumaca.js ../ESTOQUE
*/
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const pasta = path.resolve(process.argv[2] || '.');
const nome = path.basename(pasta);

let falhas = 0;
const ok = (t) => console.log('  ok    ' + t);
const erro = (t, e) => { falhas++; console.log('  FALHA ' + t + (e ? '\n        ' + e : '')); };
function conferir(titulo, fn) {
  try { fn(); ok(titulo); } catch (e) { erro(titulo, e.message); }
}
function igual(a, b, msg) {
  if (String(a) !== String(b)) throw new Error(`${msg}: esperado ${b}, veio ${a}`);
}

/* ---------- DOM simulado ---------- */
const idsUsados = new Set();

function elemento(id) {
  const el = {
    id, hidden: false, value: '', textContent: '', innerHTML: '',
    className: '', type: '', checked: false, style: {}, dataset: {},
    srcObject: null, min: '', inputMode: '',
    classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
    appendChild(x) { return x; },
    append() {},
    removeChild() {},
    remove() {},
    setAttribute() {}, getAttribute: () => null,
    focus() {}, play: async () => {},
    addEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    set onclick(v) { this._onclick = v; },
    get onclick() { return this._onclick; },
    set oninput(v) { this._oninput = v; },
    get oninput() { return this._oninput; },
    set onchange(v) { this._onchange = v; },
    get onchange() { return this._onchange; }
  };
  return el;
}

const cache = new Map();
const idsNoHtml = new Set(
  [...fs.readFileSync(path.join(pasta, 'index.html'), 'utf8').matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])
);

const documento = {
  getElementById(id) {
    idsUsados.add(id);
    if (!cache.has(id)) cache.set(id, elemento(id));
    return cache.get(id);
  },
  createElement: (t) => elemento('<' + t + '>'),
  querySelectorAll: () => [],
  addEventListener() {}
};

const armazem = () => {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k)
  };
};

function refFalsa() {
  const r = {
    on: () => () => {},
    off() {},
    get: async () => ({ val: () => null }),
    set: async () => {},
    update: async () => {},
    remove: async () => {},
    push: async () => ({ key: 'chave-teste' })
  };
  r.push = Object.assign(async () => ({ key: 'chave-teste' }), { key: 'chave-teste' });
  r.push = () => ({ key: 'chave-teste', then: (f) => Promise.resolve({ key: 'chave-teste' }).then(f) });
  return r;
}

const firebaseFalso = {
  initializeApp() {},
  auth: () => ({
    onAuthStateChanged() {},                    // não dispara: só queremos carregar
    signInWithEmailAndPassword: async () => {},
    signOut: async () => {}
  }),
  database: () => ({ ref: () => refFalsa() })
};

const contexto = {
  console,
  document: documento,
  firebase: firebaseFalso,
  localStorage: armazem(),
  sessionStorage: armazem(),
  navigator: { mediaDevices: {}, serviceWorker: undefined },
  crypto: globalThis.crypto,
  TextEncoder,
  setTimeout, clearTimeout, requestAnimationFrame: () => {},
  module: { exports: {} }
};
contexto.window = contexto;
contexto.globalThis = contexto;
contexto.window.addEventListener = () => {};

console.log('\n' + nome + '\n' + '-'.repeat(nome.length));

/* ---------- 1. carrega o app.js ---------- */
let exportado = {};
conferir('app.js carrega sem erro de sintaxe nem elemento faltando', () => {
  const codigo = fs.readFileSync(path.join(pasta, 'app.js'), 'utf8');
  vm.createContext(contexto);
  new vm.Script(codigo, { filename: 'app.js' }).runInContext(contexto);
  exportado = contexto.module.exports;
});

/* ---------- 2. todo id usado existe no HTML ---------- */
conferir('todos os getElementById existem no index.html', () => {
  const orfaos = [...idsUsados].filter((id) => !idsNoHtml.has(id));
  if (orfaos.length) throw new Error('sem elemento no HTML: ' + orfaos.join(', '));
});

/* ---------- 3. JSON e manifest ---------- */
conferir('manifest.json é JSON válido e aponta para ícones existentes', () => {
  const m = JSON.parse(fs.readFileSync(path.join(pasta, 'manifest.json'), 'utf8'));
  m.icons.forEach((i) => {
    if (!fs.existsSync(path.join(pasta, i.src))) throw new Error('ícone faltando: ' + i.src);
  });
});

conferir('sw.js lista só arquivos que existem', () => {
  const sw = fs.readFileSync(path.join(pasta, 'sw.js'), 'utf8');
  const casca = [...sw.matchAll(/'\.\/([^']*)'/g)].map((m) => m[1]).filter(Boolean);
  casca.forEach((f) => {
    if (!fs.existsSync(path.join(pasta, f))) throw new Error('no cache mas não existe: ' + f);
  });
});

/* ---------- 4. regras de negócio ---------- */
if (exportado.fimDaValidade) {
  conferir('validade MM/AA vale até o ÚLTIMO dia do mês', () => {
    const fim = exportado.fimDaValidade('02/24');   // ano bissexto
    igual(fim.getMonth(), 1, 'mês');
    igual(fim.getDate(), 29, 'dia');
    const fim2 = exportado.fimDaValidade('09/27');
    igual(fim2.getDate(), 30, 'dia de setembro');
    igual(exportado.fimDaValidade('13/27'), null, 'mês 13 deve ser inválido');
    igual(exportado.fimDaValidade('agosto'), null, 'texto solto deve ser inválido');
  });

  conferir('item vence só depois do último dia do mês', () => {
    const hoje = new Date();
    const mm = String(hoje.getMonth() + 1).padStart(2, '0');
    const aa = String(hoje.getFullYear() % 100).padStart(2, '0');
    const dias = exportado.diasAteVencer(mm + '/' + aa);
    if (dias < 0) throw new Error('o mês corrente não pode estar vencido (veio ' + dias + ')');
  });

  conferir('situação classifica vencido, baixo e em dia', () => {
    igual(exportado.situacao({ validade: '01/20', quantidade: 5 }), 'vencido', 'vencido');
    igual(exportado.situacao({ quantidade: 2, minimo: 5 }), 'baixo', 'estoque baixo');
    igual(exportado.situacao({ quantidade: 50, minimo: 5 }), 'ok', 'em dia');
  });
}

conferir('busca ignora acento e maiúscula', () => {
  const alvo = { nome: 'Diazepam Solução', ms: '1234', codigoBarras: '789', lote: 'A1', descricao: 'Diazepam Solução' };
  const campos = exportado.combina.length >= 3 ? ['descricao', 'ms', 'lote'] : null;
  const teste = campos
    ? exportado.combina(alvo, 'solucao', campos)
    : exportado.combina(alvo, 'SOLUCAO');
  if (!teste) throw new Error('não achou "solucao" em "Solução"');
});

console.log(falhas ? `\n${falhas} falha(s)\n` : '\nTudo passou.\n');
process.exit(falhas ? 1 : 0);
