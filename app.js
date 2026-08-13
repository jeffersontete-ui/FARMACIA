/* FARMÁCIA — SNGPC
   Conferência Digifarma × SNGPC. O app só LÊ farmacia/inventario:
   quem escreve ali é o agente que roda no servidor da farmácia.
   O app escreve em farmacia/aceites, farmacia/comando e farmacia/operadores.

   Regras do projeto respeitadas aqui:
   - quem entra é identificado pelo login do Firebase; ler o inventário
     depende do UID estar em farmacia/autorizados;
   - nada de prompt()/confirm() nativos: modais próprios;
   - localStorage só para preferência do aparelho;
   - o aceite da ANVISA é marcado à mão, com nome de quem marcou.
*/
'use strict';

/* ============================================================
   1. CONFIGURAÇÃO
   ============================================================ */
const CONFIG_FIREBASE = {
  apiKey: 'AIzaSyC3nXsBC2ARX8IOLITHUtovPn4DONEQe7g',
  authDomain: 'estoque-remedios-7b785.firebaseapp.com',
  databaseURL: 'https://estoque-remedios-7b785-default-rtdb.firebaseio.com',
  projectId: 'estoque-remedios-7b785',
  storageBucket: 'estoque-remedios-7b785.firebasestorage.app',
  messagingSenderId: '1005921072336',
  appId: '1:1005921072336:web:964ca0ae079b5e796e5ad5'
};

const CHAVE_OPERADOR = 'farmacia.operador';

firebase.initializeApp(CONFIG_FIREBASE);
const auth = firebase.auth();
const db = firebase.database();

/* ============================================================
   2. ESTADO
   ============================================================ */
const estado = {
  operador: null,
  inventario: {},   // farmacia/inventario
  aceites: {},      // farmacia/aceites
  comando: null,    // farmacia/comando
  operadores: [],
  vista: 'painel',
  buscaSaldo: '',
  buscaXml: '',
  abertos: new Set()
};

/* ============================================================
   3. UTILIDADES
   ============================================================ */
const $ = (id) => document.getElementById(id);
const criar = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const esc = (s) => String(s ?? '');
const agora = () => new Date().toISOString();

function avisar(texto, ms = 2800) {
  const el = $('aviso');
  el.textContent = texto;
  el.hidden = false;
  clearTimeout(avisar._t);
  avisar._t = setTimeout(() => { el.hidden = true; }, ms);
}

function dataHora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function dataBR(iso) {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : esc(iso);
}

function normalizar(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function combina(obj, termo, campos) {
  if (!termo) return true;
  const t = normalizar(termo);
  return campos.some((c) => normalizar(obj[c]).includes(t));
}

function lista(no) {
  const v = estado.inventario?.[no];
  if (!v) return [];
  return Array.isArray(v) ? v.filter(Boolean) : Object.values(v);
}

/* ============================================================
   4. MODAIS
   ============================================================ */
let fecharModalAtual = null;

function abrirModal({ titulo, corpo, acoes }) {
  $('modal-titulo').textContent = titulo;
  const alvo = $('modal-corpo');
  alvo.innerHTML = '';
  if (typeof corpo === 'string') alvo.innerHTML = corpo;
  else if (corpo) alvo.appendChild(corpo);

  const barra = $('modal-acoes');
  barra.innerHTML = '';
  (acoes || []).forEach((a) => {
    const b = criar('button', 'botao ' + (a.estilo || 'botao-fantasma'));
    b.textContent = a.texto;
    b.onclick = () => a.aoClicar?.();
    barra.appendChild(b);
  });
  $('modal').hidden = false;
  fecharModalAtual = () => { $('modal').hidden = true; fecharModalAtual = null; };
  const primeiro = alvo.querySelector('input, select, textarea');
  if (primeiro) setTimeout(() => primeiro.focus(), 60);
}

function fecharModal() { fecharModalAtual?.(); }

function confirmar(titulo, texto, textoOk = 'Confirmar', estilo = 'botao-principal') {
  return new Promise((resolve) => {
    abrirModal({
      titulo,
      corpo: `<p class="sublinha">${esc(texto)}</p>`,
      acoes: [
        { texto: 'Cancelar', aoClicar: () => { fecharModal(); resolve(false); } },
        { texto: textoOk, estilo, aoClicar: () => { fecharModal(); resolve(true); } }
      ]
    });
  });
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharModal(); });
$('modal').addEventListener('click', (e) => { if (e.target.id === 'modal') fecharModal(); });

/* ============================================================
   5. ENTRAR
   ============================================================ */
$('btn-entrar').onclick = async () => {
  const erro = $('login-erro');
  erro.hidden = true;
  const email = $('login-email').value.trim();
  const senha = $('login-senha').value;
  if (!email || !senha) { erro.textContent = 'Preencha e-mail e senha.'; erro.hidden = false; return; }
  $('btn-entrar').disabled = true;
  try {
    await auth.signInWithEmailAndPassword(email, senha);
  } catch (e) {
    const c = e?.code || '';
    erro.textContent = c.includes('invalid-credential') || c.includes('wrong-password') || c.includes('user-not-found')
      ? 'E-mail ou senha não conferem.'
      : 'Não foi possível entrar: ' + (e?.message || c);
    erro.hidden = false;
  } finally {
    $('btn-entrar').disabled = false;
  }
};
$('login-senha').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('btn-entrar').click(); });

$('btn-sair').onclick = async () => {
  if (!(await confirmar('Sair do app', 'Você vai precisar entrar de novo com o seu e-mail e senha.', 'Sair', 'botao-perigo'))) return;
  desligarEscutas();
  await auth.signOut();
};

auth.onAuthStateChanged(async (user) => {
  if (!user) {
    desligarEscutas();
    ['app', 'tela-operador'].forEach((id) => { $(id).hidden = true; });
    $('tela-login').hidden = false;
    $('login-senha').value = '';
    return;
  }
  $('tela-login').hidden = true;
  ligarEscutas();
  // Não há senha de farmácia: o login por e-mail do Firebase já identifica
  // quem entrou, e as regras do banco só liberam quem está em
  // farmacia/autorizados.
  escolherOperador();
});

/* ============================================================
   6. OPERADOR
   ============================================================ */
function escolherOperador() {
  const salvo = localStorage.getItem(CHAVE_OPERADOR);
  if (salvo) { entrarNoApp(salvo); return; }
  $('tela-operador').hidden = false;
  pintarOperadores();
}

function pintarOperadores() {
  const alvo = $('lista-operadores');
  if (!alvo) return;
  alvo.innerHTML = '';
  estado.operadores.forEach((nome) => {
    const b = criar('button', 'chip');
    b.textContent = nome;
    b.onclick = () => entrarNoApp(nome);
    alvo.appendChild(b);
  });
}

$('btn-operador').onclick = async () => {
  const nome = $('operador-novo').value.trim();
  if (!nome) { avisar('Escolha um nome ou digite um novo.'); return; }
  if (!estado.operadores.includes(nome)) {
    await db.ref('farmacia/operadores').set([...estado.operadores, nome].sort((a, b) => a.localeCompare(b, 'pt-BR')));
  }
  entrarNoApp(nome);
};

function entrarNoApp(nome) {
  estado.operador = nome;
  localStorage.setItem(CHAVE_OPERADOR, nome);
  $('rotulo-operador').textContent = 'Conferindo: ' + nome;
  $('tela-operador').hidden = true;
  $('app').hidden = false;
  pintar();
}

/* ============================================================
   7. SINCRONIZAÇÃO (só leitura do inventário)
   ============================================================ */
const escutas = [];

function escutar(caminho, aoMudar) {
  const ref = db.ref(caminho);
  const cb = ref.on('value',
    (s) => aoMudar(s.val()),
    (e) => {
      $('barra-estado').textContent = 'Sem acesso a ' + caminho + ' — confira as regras do Firebase e se o seu UID está em farmacia/autorizados.';
      $('barra-estado').hidden = false;
      console.error(caminho, e);
    });
  escutas.push({ ref, cb });
}

function ligarEscutas() {
  if (escutas.length) return;
  escutar('farmacia/inventario', (v) => { estado.inventario = v || {}; pintar(); });
  escutar('farmacia/aceites', (v) => { estado.aceites = v || {}; if (estado.vista === 'aceites') pintarAceites(); });
  escutar('farmacia/comando', (v) => { estado.comando = v; pintarComando(); });
  escutar('farmacia/operadores', (v) => {
    estado.operadores = Array.isArray(v) ? v.filter(Boolean) : Object.values(v || {});
    pintarOperadores();
  });
}

function desligarEscutas() {
  escutas.forEach(({ ref, cb }) => ref.off('value', cb));
  escutas.length = 0;
}

/* ============================================================
   8. BOTÕES QUE PEDEM AO AGENTE (farmacia/comando)
   ============================================================ */
async function pedirAoAgente(acao, rotulo) {
  await db.ref('farmacia/comando').set({
    acao,                    // 'sincronizar_vendas' | 'atualizar_envio'
    pedidoEm: agora(),
    pedidoPor: estado.operador,
    estado: 'pendente'
  });
  avisar(rotulo + ' pedido. O agente atende em até 5 minutos.');
}

$('btn-sincronizar').onclick = () => pedirAoAgente('sincronizar_vendas', 'Sincronizar vendas');
$('btn-atualizar-envio').onclick = () => pedirAoAgente('atualizar_envio', 'Atualizar envio');

function pintarComando() {
  const barra = $('fila-comando');
  const c = estado.comando;
  if (!c || c.estado === 'concluido') {
    if (c?.estado === 'concluido' && c.concluidoEm) {
      barra.textContent = `Último pedido (${c.acao}) atendido em ${dataHora(c.concluidoEm)}.`;
      barra.hidden = false;
    } else {
      barra.hidden = true;
    }
    return;
  }
  if (c.estado === 'erro') {
    barra.textContent = `O agente não conseguiu atender “${c.acao}”: ${c.mensagem || 'sem detalhe'}.`;
  } else {
    barra.textContent = `Pedido “${c.acao}” na fila desde ${dataHora(c.pedidoEm)} — o agente roda de 5 em 5 minutos.`;
  }
  barra.hidden = false;
}

/* ============================================================
   9. NAVEGAÇÃO
   ============================================================ */
function irPara(vista) {
  estado.vista = vista;
  document.querySelectorAll('.nav-item').forEach((x) => x.classList.toggle('nav-ativo', x.dataset.vista === vista));
  document.querySelectorAll('.vista').forEach((v) => { v.hidden = v.id !== 'v-' + vista; });
  pintar();
}
document.querySelectorAll('.nav-item').forEach((b) => { b.onclick = () => irPara(b.dataset.vista); });
document.querySelectorAll('[data-ir]').forEach((b) => { b.onclick = () => irPara(b.dataset.ir); });
$('busca-saldo').oninput = (e) => { estado.buscaSaldo = e.target.value; pintarSaldo(); };
$('busca-xml').oninput = (e) => { estado.buscaXml = e.target.value; pintarXml(); };

/* ============================================================
   10. DESENHO
   ============================================================ */
function divergenciasDeSaldo() {
  return lista('itens').filter((i) => Number(i.diferenca || 0) !== 0);
}
function pendenciasXml() {
  return lista('conferencia_xml').filter((c) => c && c.situacao !== 'ok');
}
function vendasProblema() {
  return lista('vendas_problema');
}

function pintar() {
  if (!estado.operador) return;
  const s = divergenciasDeSaldo().length, x = pendenciasXml().length, v = vendasProblema().length;
  [['selo-saldo', s], ['selo-xml', x], ['selo-vendas', v]].forEach(([id, n]) => {
    const el = $(id); el.textContent = n; el.hidden = n === 0;
  });
  $('n-saldo').textContent = s;
  $('n-xml').textContent = x;
  $('n-vendas').textContent = v;
  document.querySelectorAll('.cartao-numero').forEach((c) => {
    const n = Number(c.querySelector('strong').textContent) || 0;
    c.classList.toggle('alerta', n > 0);
  });

  const carimbo = estado.inventario?.atualizadoEm;
  $('carimbo').textContent = carimbo
    ? 'Dados do Digifarma de ' + dataHora(carimbo) + (estado.inventario?.inventario?.data ? ' · inventário de ' + dataBR(estado.inventario.inventario.data) : '')
    : 'O agente ainda não publicou nada. Rode o INSTALAR_AGENTE.bat no servidor.';

  pintarEnvio();
  pintarPendentes();
  avisarSobreAnvisa();
  if (estado.vista === 'saldo') pintarSaldo();
  if (estado.vista === 'xml') pintarXml();
  if (estado.vista === 'vendas') pintarVendas();
  if (estado.vista === 'aceites') pintarAceites();
}

const ROTULO_PENDENTE = {
  vendas: 'Vendas', entradas: 'Entradas',
  perdas: 'Perdas', transferencias: 'Transferências'
};

function pintarPendentes() {
  const dl = $('dados-pendentes');
  if (!dl) return;
  dl.innerHTML = '';
  const resumo = estado.inventario?.resumoPendentes;
  if (!resumo) {
    const dt = criar('dt'); dt.textContent = 'Sem dados';
    const dd = criar('dd'); dd.textContent = 'o agente ainda não publicou';
    dl.append(dt, dd);
    return;
  }
  Object.entries(ROTULO_PENDENTE).forEach(([chave, rotulo]) => {
    const dt = criar('dt'); dt.textContent = rotulo;
    const dd = criar('dd');
    const n = Number(resumo[chave] || 0);
    dd.textContent = n === 0 ? 'nada pendente' : n + ' movimento(s)';
    dl.append(dt, dd);
  });
}

function avisarSobreAnvisa() {
  const a = estado.inventario?.anvisa;
  const barra = $('barra-estado');
  if (!a || !a.precisaLogin) return;
  const dias = a.diasSemSincronizar;
  barra.textContent = dias === null || dias === undefined
    ? 'O inventário da ANVISA nunca foi baixado. Abra o Anvisa.exe no servidor e faça o login no site do SNGPC.'
    : `O inventário da ANVISA está com ${dias} dia(s). Abra o Anvisa.exe no servidor e faça o login — ele para na tela de login e não anda sozinho.`;
  barra.hidden = false;
}

const ROTULO_MODO_SALDO = {
  saldo: 'saldo do lote, direto da coluna',
  movimento: 'movimentos de estoque menos vendas e perdas'
};

function baseDoSaldo() {
  const inv = estado.inventario?.inventario || {};
  if (!inv.colunaSaldo) return '—';
  const modo = ROTULO_MODO_SALDO[inv.modoSaldo];
  return 'LOTES.' + inv.colunaSaldo + (modo ? ' — ' + modo : '');
}

function pintarEnvio() {
  const e = estado.inventario?.envio || {};
  const dl = $('dados-envio');
  dl.innerHTML = '';
  const linhas = [
    ['Como o saldo é apurado', baseDoSaldo()],
    ['Data do envio', dataBR(e.data)],
    ['Movimentos de', e.movimentosDe ? dataBR(e.movimentosDe) + ' a ' + dataBR(e.movimentosAte) : '—'],
    ['Envio por API', e.envioPorApi ? 'ligado no Digifarma' : 'desligado (envio manual)'],
    ['Última venda transmitida', e.ULT_SAIDA_VENDA_NOTA_ID ?? '—'],
    ['Última entrada transmitida', e.ULT_ENTRADA_CAB_NOTA_ID ?? '—'],
    ['XML arquivado', e.arquivoXml || '—']
  ];
  linhas.forEach(([k, v]) => {
    const dt = criar('dt'); dt.textContent = k;
    const dd = criar('dd'); dd.textContent = esc(v);
    dl.append(dt, dd);
  });
}

/* --- linha expansível com tarja --- */
function linha({ chave, titulo, meta, tarja, tarjaClasse, detalhe }) {
  const el = criar('div', 'linha');

  const cabeca = criar('button', 'linha-cabeca');
  const t = criar('p', 'linha-titulo'); t.textContent = titulo;
  cabeca.appendChild(t);
  const m = criar('p', 'linha-meta');
  meta.filter(Boolean).forEach((x) => { const s = criar('span'); s.textContent = x; m.appendChild(s); });
  cabeca.appendChild(m);
  cabeca.setAttribute('aria-expanded', String(estado.abertos.has(chave)));
  el.appendChild(cabeca);

  const faixa = criar('div', 'linha-tarja ' + (tarjaClasse || ''));
  const esquerda = criar('span'); esquerda.textContent = tarja[0];
  const direita = criar('span'); direita.textContent = tarja[1];
  faixa.append(esquerda, direita);
  el.appendChild(faixa);

  const caixa = criar('div', 'linha-detalhe');
  caixa.appendChild(detalhe);
  caixa.hidden = !estado.abertos.has(chave);
  el.appendChild(caixa);

  cabeca.onclick = () => {
    const aberto = !caixa.hidden;
    caixa.hidden = aberto;
    cabeca.setAttribute('aria-expanded', String(!aberto));
    if (aberto) estado.abertos.delete(chave); else estado.abertos.add(chave);
  };
  return el;
}

function definicoes(pares) {
  const d = criar('div');
  const dl = criar('dl');
  pares.filter(([, v]) => v !== undefined && v !== null && v !== '').forEach(([k, v]) => {
    const dt = criar('dt'); dt.textContent = k;
    const dd = criar('dd'); dd.textContent = esc(v);
    dl.append(dt, dd);
  });
  d.appendChild(dl);
  return d;
}

function pintarAlertaSaldo() {
  const barra = $('saldo-alerta');
  const inv = estado.inventario?.inventario;
  if (!inv) { barra.hidden = true; return; }
  // Sem o lado ANVISA, TODO lote do Digifarma aparece como sobra. São
  // milhares de divergências que não são divergência nenhuma — o app
  // precisa dizer isso, senão o número vira ruído.
  if (!inv.itens) {
    barra.textContent = 'O inventário da ANVISA está vazio, então todo lote do Digifarma '
      + 'aparece aqui como sobra. Rode o Anvisa.exe no servidor e faça o login no site do '
      + 'SNGPC antes de conferir estes números.';
    barra.hidden = false;
    return;
  }
  barra.hidden = true;
}

function pintarSaldo() {
  pintarAlertaSaldo();
  const alvo = $('lista-saldo');
  alvo.innerHTML = '';
  const itens = divergenciasDeSaldo()
    .filter((i) => combina(i, estado.buscaSaldo, ['descricao', 'ms', 'ean', 'lote', 'codigo']))
    .sort((a, b) => Math.abs(Number(b.diferenca || 0)) - Math.abs(Number(a.diferenca || 0)));
  $('saldo-vazio').hidden = itens.length > 0 || !!estado.buscaSaldo;

  itens.forEach((i, n) => {
    const dif = Number(i.diferenca || 0);
    alvo.appendChild(linha({
      chave: 'saldo:' + (i.codigo || n) + ':' + (i.lote || ''),
      titulo: i.descricao || i.codigo || '(sem descrição)',
      meta: [
        i.ms && 'M.S. ' + i.ms,
        i.ean && 'EAN ' + i.ean,
        i.lote && 'Lote ' + i.lote,
        i.validade && 'Val. ' + i.validade
      ],
      tarja: [dif < 0 ? 'Falta no Digifarma' : 'Sobra no Digifarma', (dif > 0 ? '+' : '') + dif],
      tarjaClasse: dif < 0 ? 'falta' : 'sobra',
      detalhe: definicoes([
        ['Código', i.codigo],
        ['Saldo Digifarma', i.saldoDigifarma],
        // só vêm quando LOTES é tabela de movimento: mostram de onde
        // o saldo saiu, para conferir contra a tela do Digifarma
        ['Entrou no lote', i.entradas],
        ['Baixado (vendas e perdas)', i.baixas],
        ['Saldo do inventário SNGPC', i.saldoSngpc],
        ['Diferença', (dif > 0 ? '+' : '') + dif],
        ['Registro M.S.', i.ms],
        ['Código de barras', i.ean],
        ['Lote', i.lote],
        ['Validade', i.validade],
        ['Classe', i.classe]
      ])
    }));
  });

  if (!itens.length && estado.buscaSaldo) {
    const p = criar('p', 'vazio');
    p.textContent = 'Nada encontrado para “' + estado.buscaSaldo + '”.';
    alvo.appendChild(p);
  }
}

function pintarXml() {
  const alvo = $('lista-xml');
  alvo.innerHTML = '';
  const itens = pendenciasXml()
    .filter((c) => combina(c, estado.buscaXml, ['descricao', 'ms', 'lote']));
  $('xml-vazio').hidden = itens.length > 0 || !!estado.buscaXml;

  const ROTULO = {
    fora_do_xml: ['Saiu no banco e não está no XML', 'falta'],
    so_no_xml: ['Está no XML e não achei no banco', 'sobra'],
    quantidade: ['Quantidade diferente', 'sobra']
  };

  itens.forEach((c, n) => {
    const [rotulo, classe] = ROTULO[c.situacao] || ['Divergência', 'falta'];
    alvo.appendChild(linha({
      chave: 'xml:' + (c.ms || n) + ':' + (c.lote || ''),
      titulo: c.descricao || ('M.S. ' + (c.ms || '?')),
      meta: [
        c.ms && 'M.S. ' + c.ms,
        c.lote && 'Lote ' + c.lote,
        c.periodo && 'Período ' + c.periodo
      ],
      tarja: [rotulo, `banco ${c.qtdBanco ?? 0} · xml ${c.qtdXml ?? 0}`],
      tarjaClasse: classe,
      detalhe: definicoes([
        ['Registro M.S.', c.ms],
        ['Lote', c.lote],
        ['Quantidade no banco', c.qtdBanco],
        ['Quantidade no XML', c.qtdXml],
        ['Período conferido', c.periodo],
        ['Arquivo XML', c.arquivo],
        ['Vendas envolvidas', Array.isArray(c.vendas) ? c.vendas.join(', ') : c.vendas]
      ])
    }));
  });

  if (!itens.length && estado.buscaXml) {
    const p = criar('p', 'vazio');
    p.textContent = 'Nada encontrado para “' + estado.buscaXml + '”.';
    alvo.appendChild(p);
  }
}

function pintarVendas() {
  const alvo = $('lista-vendas');
  alvo.innerHTML = '';
  const itens = vendasProblema();
  $('vendas-vazio').hidden = itens.length > 0;

  const MOTIVO = {
    sem_receita: 'Controlado vendido sem receita escriturada (VENDAS_PSICOTROPICOS).',
    sem_lote: 'Item sem lote informado (ITEM_VENDAS_LOTES).',
    sem_ms: 'Produto sem registro M.S. cadastrado.'
  };

  itens.forEach((v, n) => {
    const detalhe = definicoes([
      ['Venda', v.venda],
      ['Data', dataBR(v.data)],
      ['Produto', v.descricao],
      ['Registro M.S.', v.ms],
      ['Lote', v.lote],
      ['Quantidade', v.quantidade],
      ['Operador da venda', v.operador]
    ]);
    const nota = criar('p', 'motivo');
    nota.textContent = MOTIVO[v.motivo] || v.motivo || 'Pendência não classificada.';
    detalhe.appendChild(nota);

    alvo.appendChild(linha({
      chave: 'venda:' + (v.venda || n),
      titulo: v.descricao || ('Venda ' + (v.venda ?? '?')),
      meta: [v.data && dataBR(v.data), v.ms && 'M.S. ' + v.ms, v.lote ? 'Lote ' + v.lote : 'Sem lote'],
      tarja: ['Corrigir no Digifarma antes do próximo envio', 'Venda ' + (v.venda ?? '—')],
      tarjaClasse: 'falta',
      detalhe
    }));
  });
}

/* ============================================================
   11. ACEITES
   ============================================================ */
function datasDeEnvio() {
  const datas = new Set(Object.keys(estado.aceites || {}));
  const envio = estado.inventario?.envio?.data;
  if (envio) datas.add(String(envio).slice(0, 10));
  lista('enviosConhecidos').forEach((d) => datas.add(String(d).slice(0, 10)));
  return [...datas].filter(Boolean).sort().reverse();
}

function pintarAceites() {
  const alvo = $('lista-aceites');
  alvo.innerHTML = '';
  const datas = datasDeEnvio();
  $('aceites-vazio').hidden = datas.length > 0;

  datas.forEach((data) => {
    const a = estado.aceites?.[data] || {};
    const estadoAtual = a.status || 'pendente';
    const el = criar('div', 'aceite');

    const esquerda = criar('div');
    const d = criar('p', 'aceite-data');
    d.textContent = 'Envio de ' + dataBR(data);
    esquerda.appendChild(d);
    const sub = criar('p', 'sublinha');
    sub.style.margin = '2px 0 0';
    sub.textContent = a.por ? `${estadoAtual === 'aceito' ? 'Aceite' : 'Recusa'} marcada por ${a.por} em ${dataHora(a.em)}` : 'Ainda não conferido no site da ANVISA';
    esquerda.appendChild(sub);
    el.appendChild(esquerda);

    const direita = criar('div');
    direita.style.display = 'flex';
    direita.style.gap = '8px';
    direita.style.alignItems = 'center';
    direita.style.flexWrap = 'wrap';

    const selo = criar('span', 'estado estado-' + estadoAtual);
    selo.textContent = { aceito: 'Aceito', recusado: 'Recusado', pendente: 'Pendente' }[estadoAtual];
    direita.appendChild(selo);

    if (estadoAtual !== 'aceito') {
      const ok = criar('button', 'botao botao-secundario');
      ok.textContent = 'Marcar aceito';
      ok.onclick = () => marcarAceite(data, 'aceito');
      direita.appendChild(ok);
    }
    if (estadoAtual !== 'recusado') {
      const nao = criar('button', 'botao botao-fantasma');
      nao.textContent = 'Marcar recusado';
      nao.onclick = () => marcarAceite(data, 'recusado');
      direita.appendChild(nao);
    }
    el.appendChild(direita);
    alvo.appendChild(el);
  });
}

async function marcarAceite(data, status) {
  const texto = status === 'aceito'
    ? `Confirma que o envio de ${dataBR(data)} aparece como aceito no site da ANVISA?`
    : `Confirma que o envio de ${dataBR(data)} foi recusado? Vale anotar a recusa para conferir as vendas do período.`;
  if (!(await confirmar('Marcar ' + status, texto, 'Marcar', status === 'aceito' ? 'botao-principal' : 'botao-perigo'))) return;
  await db.ref('farmacia/aceites/' + data).set({ status, por: estado.operador, em: agora() });
  avisar('Envio de ' + dataBR(data) + ' marcado como ' + status + '.');
}

/* ============================================================
   12. PWA
   ============================================================ */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch((e) => console.warn('Service worker não registrado:', e));
  });
}
window.addEventListener('offline', () => {
  $('barra-estado').textContent = 'Sem internet — os números na tela são os últimos que chegaram.';
  $('barra-estado').hidden = false;
});
window.addEventListener('online', () => { $('barra-estado').hidden = true; });

/* exposto para o teste de fumaça */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalizar, combina, dataBR };
}
