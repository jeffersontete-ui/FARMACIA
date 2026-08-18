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
  relatorios: {},   // farmacia/relatorios — a saída dos comandos pedidos daqui
  ultimoPedido: null,
  operadores: [],
  vista: 'painel',
  buscaSaldo: '',
  buscaXml: '',
  buscaVendas: '',
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

function horaBR(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : dataBR(iso);
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
  escutar('farmacia/aceites', (v) => { estado.aceites = v || {}; pintar(); });
  escutar('farmacia/comando', (v) => { estado.comando = v; pintarComando(); pintarServidor(); });
  escutar('farmacia/relatorios', (v) => { estado.relatorios = v || {}; pintarServidor(); });
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
  avisar(rotulo + ' pedido. O agente atende em cerca de um minuto.');
}

$('btn-sincronizar').onclick = () => pedirAoAgente('sincronizar_vendas', 'Sincronizar vendas');
$('btn-atualizar-envio').onclick = () => pedirAoAgente('atualizar_envio', 'Atualizar envio');

/* --- aba Servidor: os comandos do terminal, pedidos daqui ---
   O agente devolve em farmacia/relatorios/<acao> exatamente o texto que
   imprimiria no servidor. Nada aqui escreve no Digifarma: os pedidos são de
   leitura, e o único que grava algo grava no agente_config.json. */
const ROTULO_PEDIDO = {
  tarefas: 'Tarefas', comparacao: 'Folha de conferência', negativos: 'Lotes negativos',
  resumo: 'Resumo', inventario: 'Inventário SNGPC', produto: 'Cadastro do produto',
  saldo: 'Apuração do saldo', sincronizar_vendas: 'Sincronizar tudo',
  atualizar_envio: 'Atualizar envio', atualizar_agente: 'Atualizar o agente',
  config: 'Ajuste do agente', colunas: 'Colunas da tabela',
  totais: 'Total do produto x soma dos lotes',
  receitas: 'Receitas lançadas',
  zerar_negativos: 'Zerar lotes negativos', ajustar_lote: 'Gravar contagem no lote'
};

async function pedirRelatorio(acao, texto) {
  await db.ref('farmacia/comando').set({
    acao,
    texto: texto || '',
    pedidoEm: agora(),
    pedidoPor: estado.operador,
    estado: 'pendente'
  });
  estado.ultimoPedido = acao;
  avisar((ROTULO_PEDIDO[acao] || acao) + ' pedido. O agente atende em cerca de um minuto.');
}

document.querySelectorAll('[data-pedir]').forEach((b) => {
  b.onclick = () => pedirRelatorio(b.dataset.pedir);
});

$('btn-produto').onclick = () => {
  const alvo = $('campo-produto').value.trim();
  if (!alvo) { avisar('Escreva parte do nome do medicamento.'); return; }
  pedirRelatorio('produto', alvo);
};

$('btn-colunas').onclick = () => {
  const tabela = $('campo-tabela').value.trim().toUpperCase();
  if (!tabela) { avisar('Escreva o nome da tabela, por exemplo PRODUTOS.'); return; }
  pedirRelatorio('colunas', tabela);
};

$('btn-ponteiro').onclick = async () => {
  const valor = Number($('campo-ponteiro').value || 0);
  if (!Number.isInteger(valor) || valor < 0) { avisar('Número de venda inválido.'); return; }
  const ok = await confirmar('Gravar no agente',
    'O agente vai tratar como já transmitido tudo até a venda ' + valor + '. '
    + 'Isso muda os números da conferência — e não conserta o Digifarma, que '
    + 'continuará querendo retransmitir. Confirma?', 'Gravar');
  if (!ok) return;
  await db.ref('farmacia/comando').set({
    acao: 'config', chave: 'transmitido_ate_venda', valor,
    pedidoEm: agora(), pedidoPor: estado.operador, estado: 'pendente'
  });
  avisar('Ajuste pedido. O agente atende em cerca de um minuto.');
};

/* Os dois únicos botões do projeto que escrevem no Digifarma. A confirmação
   diz o que vai mudar e o que NÃO pode ser feito depois — transmitir. */
$('btn-zerar-negativos').onclick = async () => {
  const ok = await confirmar('Zerar os lotes negativos',
    'O agente vai pôr em zero, no Digifarma, todo lote com saldo negativo. '
    + 'Saldo negativo não é estoque, é lançamento errado. Fica registrado o '
    + 'antes, o depois e quem pediu. Este acerto NÃO pode ser transmitido ao '
    + 'SNGPC. Confirma?', 'Zerar', 'botao-perigo');
  if (!ok) return;
  await db.ref('farmacia/comando').set({
    acao: 'zerar_negativos', texto: '',
    pedidoEm: agora(), pedidoPor: estado.operador, estado: 'pendente'
  });
  estado.ultimoPedido = 'zerar_negativos';
  avisar('Pedido enviado. O agente atende em cerca de um minuto.');
};

$('btn-ajustar-lote').onclick = async () => {
  const ms = $('ajuste-ms').value.trim();
  const lote = $('ajuste-lote').value.trim();
  const qtd = $('ajuste-qtd').value;
  if (!lote || qtd === '') { avisar('Preencha o lote e a quantidade contada.'); return; }
  const ok = await confirmar('Gravar a contagem',
    `O saldo do lote ${lote} no Digifarma vai passar a ser ${Number(qtd)}, `
    + 'o que foi contado na prateleira. Fica registrado o antes, o depois e '
    + 'quem pediu. Este acerto NÃO pode ser transmitido ao SNGPC. Confirma?',
    'Gravar', 'botao-perigo');
  if (!ok) return;
  await db.ref('farmacia/comando').set({
    acao: 'ajustar_lote', ms, lote, quantidade: Number(qtd),
    motivo: 'contagem de prateleira',
    pedidoEm: agora(), pedidoPor: estado.operador, estado: 'pendente'
  });
  estado.ultimoPedido = 'ajustar_lote';
  avisar('Pedido enviado. O agente atende em cerca de um minuto.');
};

$('btn-atualizar-agente').onclick = async () => {
  const ok = await confirmar('Atualizar o agente',
    'O servidor vai baixar a versão mais nova do GitHub e substituir o arquivo. '
    + 'O atual vai para backup, e se o arquivo baixado tiver qualquer problema '
    + 'nada é trocado. Confirma?', 'Atualizar');
  if (ok) pedirRelatorio('atualizar_agente');
};

function pintarServidor() {
  const c = estado.comando;
  const barra = $('servidor-fila');
  if (c && c.estado === 'pendente') {
    barra.textContent = `“${ROTULO_PEDIDO[c.acao] || c.acao}” na fila desde `
      + `${dataHora(c.pedidoEm)} — o agente roda a cada minuto.`;
    barra.hidden = false;
  } else if (c && c.estado === 'erro') {
    barra.textContent = `O agente não conseguiu: ${c.mensagem || 'sem detalhe'}`;
    barra.hidden = false;
  } else if (c && c.estado === 'concluido' && c.mensagem) {
    barra.textContent = `${c.mensagem} (${dataHora(c.concluidoEm)})`;
    barra.hidden = false;
  } else {
    barra.hidden = true;
  }

  // o relatório mostrado é o do último pedido, ou o mais recente que existir
  const todos = estado.relatorios || {};
  let acao = estado.ultimoPedido && todos[estado.ultimoPedido] ? estado.ultimoPedido : null;
  if (!acao) {
    acao = Object.keys(todos).sort((a, b) =>
      String(todos[b]?.em || '').localeCompare(String(todos[a]?.em || '')))[0];
  }
  const r = acao ? todos[acao] : null;
  $('relatorio-texto').textContent = r?.texto || '';
  $('relatorio-carimbo').textContent = r
    ? `${ROTULO_PEDIDO[acao] || acao} · ${dataHora(r.em)}`
      + (r.filtro ? ` · filtro “${r.filtro}”` : '')
      + (r.cortado ? ' · texto cortado, o arquivo completo está no servidor' : '')
    : 'Nenhum relatório pedido ainda.';
  $('btn-ver-folha').hidden = !(todos.comparacao && todos.comparacao.html);

  const a = estado.inventario?.agente || {};
  const dl = $('dados-agente');
  dl.innerHTML = '';
  [['Arquivo no servidor', a.hash ? a.hash + ' · ' + (a.bytes || 0) + ' bytes' : '—'],
   ['Gravado em', a.em ? dataHora(a.em) : '—']].forEach(([k, v]) => {
    const dt = criar('dt'); dt.textContent = k;
    const dd = criar('dd'); dd.textContent = esc(v);
    dl.append(dt, dd);
  });

  const ponteiroAtual = estado.inventario?.envio?.ULT_SAIDA_VENDA_NOTA_ID;
  if (ponteiroAtual != null && !$('campo-ponteiro').value) {
    $('campo-ponteiro').placeholder = String(ponteiroAtual);
  }
}

/* A folha é HTML pronto para impressão: abrir num iframe evita depender de
   pop-up, que o celular bloqueia, e o botão de imprimir fala com o iframe. */
$('btn-ver-folha').onclick = () => {
  const html = estado.relatorios?.comparacao?.html;
  if (!html) { avisar('A folha ainda não foi gerada.'); return; }
  const caixa = criar('div');
  const quadro = criar('iframe', 'folha-quadro');
  quadro.srcdoc = html;
  caixa.appendChild(quadro);
  abrirModal({
    titulo: 'Folha de conferência',
    corpo: caixa,
    acoes: [
      { texto: 'Fechar', aoClicar: fecharModal },
      { texto: 'Imprimir', estilo: 'botao-principal', aoClicar: () => {
        quadro.contentWindow.focus();
        quadro.contentWindow.print();
      } }
    ]
  });
};

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
    barra.textContent = `Pedido “${c.acao}” na fila desde ${dataHora(c.pedidoEm)} — o agente roda a cada minuto.`;
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
$('busca-vendas-recentes').oninput = (e) => { estado.buscaVendas = e.target.value; pintarVendasRecentes(); };

/* ============================================================
   10. DESENHO
   ============================================================ */
/* Produto sem M.S. não é divergência de estoque: o SNGPC recusa medicamento
   sem registro, então ele nunca é transmitido e não tem como bater. Contar
   junto infla o número de divergências com item que nenhuma conferência de
   prateleira resolve. */
function divergenciasDeSaldo(itens) {
  return (itens || lista('itens'))
    .filter((i) => Number(i.diferenca || 0) !== 0 && i.motivo !== 'sem_ms');
}
/* Pelo M.S. em falta, não pelo motivo: o motivo é um só por item, e
   'negativo' ganha de 'sem_ms' na classificação. Um controlado sem registro
   E com saldo negativo saía rotulado de negativo e sumia desta lista — foi
   assim que a amoxicilina da Cimed passou meses sem ser escriturada, com as
   entradas e as vendas fora do SNGPC, sem aparecer em lugar nenhum. */
function pendenciasDeCadastro(itens) {
  return (itens || lista('itens')).filter((i) => !i.ms);
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
  // envio sem aceite marcado também é pendência: sem saber o que a ANVISA
  // aceitou, não há como explicar divergência de saldo
  const ac = envioSemAceite().length;
  [['selo-saldo', s], ['selo-xml', x], ['selo-vendas', v], ['selo-aceites', ac]].forEach(([id, n]) => {
    // 4 dígitos no selo transbordam por cima do item vizinho da navegação
    const el = $(id); el.textContent = n > 999 ? '999+' : n; el.hidden = n === 0;
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
  pintarDiagnostico();
  pintarPendentes();
  avisarSobreAnvisa();
  if (estado.vista === 'saldo') pintarSaldo();
  if (estado.vista === 'xml') pintarXml();
  if (estado.vista === 'vendas') { pintarSemReceita(); pintarVendas(); pintarVendasRecentes(); }
  if (estado.vista === 'aceites') pintarAceites();
  if (estado.vista === 'servidor') pintarServidor();
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

/* O diagnóstico existe para responder de longe "por que ainda há
   divergência". Sobe a cada minuto junto com as vendas. */
function pintarDiagnostico() {
  const dl = $('dados-diagnostico');
  dl.innerHTML = '';
  const d = estado.inventario?.diagnostico;
  if (!d) {
    const dt = criar('dt'); dt.textContent = 'Sem dados';
    const dd = criar('dd'); dd.textContent = 'o agente ainda não publicou o diagnóstico';
    dl.append(dt, dd);
    return;
  }
  const pend = d.pendentes || {};
  const inv = d.inventarioSngpc || {};
  const total = Object.values(pend).reduce((s, n) => s + Number(n || 0), 0);
  const linhas = [
    ['Lido em', dataHora(d.em)],
    ['Esperando transmissão', total === 0
      ? 'nada — tudo que o Digifarma tem já foi enviado'
      : Object.entries(pend).map(([t, n]) => n + ' ' + t).join(' · ')],
    ['Ponteiros', 'venda ' + (d.ponteiroVenda ?? '—') + ' · entrada ' + (d.ponteiroEntrada ?? '—')],
    ['Último envio', dataBR(d.ultimoEnvio)],
    ['Inventário SNGPC (linhas)', inv.linhas],
    ['— entram na comparação', inv.entram],
    ['— fora do critério', inv.foraDoCriterio],
    ['— sem produto no cadastro', inv.semProdutoNoCadastro]
  ];
  linhas.filter(([, v]) => v !== undefined && v !== null).forEach(([k, v]) => {
    const dt = criar('dt'); dt.textContent = k;
    const dd = criar('dd'); dd.textContent = esc(v);
    dl.append(dt, dd);
  });
}

function pintarEnvio() {
  const e = estado.inventario?.envio || {};
  const dl = $('dados-envio');
  dl.innerHTML = '';
  const linhas = [
    ['Como o saldo é apurado', baseDoSaldo()],
    ['Data do envio', dataBR(e.data)],
    // "Movimentos de" sai do CABEÇALHO DO XML que está na pasta, e um XML
    // gerado não é um XML transmitido. Dizer só o período fazia a tela
    // afirmar um envio que podia não ter acontecido — foi assim que a
    // farmácia leu "movimentos de 16 a 17/08" e não achou envio nenhum
    // desse período no site da ANVISA.
    ['Movimentos do último XML', e.movimentosDe
      ? dataBR(e.movimentosDe) + ' a ' + dataBR(e.movimentosAte) : '—'],
    ['Envio por API', e.envioPorApi ? 'ligado no Digifarma' : 'desligado (envio manual)'],
    // o remendo do transmitido_ate_venda tem que aparecer aqui: quem lê
    // "última venda transmitida" no celular precisa saber que esse número
    // saiu do agente_config.json e não do ponteiro do Digifarma
    ['Última venda transmitida', (e.ULT_SAIDA_VENDA_NOTA_ID ?? '—')
      + (e.ponteiroForcado ? ' (posto à mão no agente_config.json — o ponteiro do '
        + 'Digifarma ficou atrás, por envio feito em outra máquina)' : '')],
    ['Última entrada transmitida', e.ULT_ENTRADA_CAB_NOTA_ID ?? '—'],
    ['XML arquivado', e.arquivoXml || '—'],
    // veio da tabela SNGPC do Digifarma, não de marcação à mão
    ['Inventário aceito pela ANVISA', e.inventarioAceito === undefined ? '—'
      : (e.inventarioAceito ? 'sim' : 'NÃO')
        + (e.inventarioEnviadoEm ? ' · enviado em ' + dataBR(e.inventarioEnviadoEm) : '')],
    ['Período transmitido', e.periodoTransmitido || '—'],
    ['Última sincronização', e.sincronizadoEm
      ? dataHora(e.sincronizadoEm) + (e.terminalSinc ? ' · terminal ' + e.terminalSinc : '')
      : '—']
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

  // O detalhe abre com transição, e `hidden` não anima. Em vez de esconder,
  // a caixa é uma grade que vai de 0fr a 1fr; o filho recorta o conteúdo.
  // Fechada, ela some do leitor de tela pelo aria-expanded da cabeça.
  const caixa = criar('div', 'linha-detalhe');
  const dentro = criar('div', 'linha-detalhe-dentro');
  dentro.appendChild(detalhe);
  caixa.appendChild(dentro);
  el.classList.toggle('aberta', estado.abertos.has(chave));
  el.appendChild(caixa);

  cabeca.onclick = () => {
    const aberto = el.classList.toggle('aberta');
    cabeca.setAttribute('aria-expanded', String(aberto));
    if (aberto) estado.abertos.add(chave); else estado.abertos.delete(chave);
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

/* Cada divergência de saldo se resolve num lugar diferente: uma entrada que
   não subiu ao SNGPC não é a mesma coisa que uma contagem que não fecha. A
   tarja diz qual é qual; o agente classifica em farmacia/inventario. */
const MOTIVO_SALDO = {
  sem_ms: ['Sem registro M.S.', 'falta',
    'A conferência casa por registro M.S. + lote. Sem M.S. no cadastro, este item não pode casar com a ANVISA de jeito nenhum — a diferença aqui é do cadastro, não do estoque. Cadastre o registro no Digifarma e ele volta a ser conferível.'],
  anvisa_zerada_produto: ['Zerado na ANVISA', 'sobra',
    'A ANVISA não tem saldo em lote nenhum deste registro M.S. Pode ser entrada que não subiu, ou saldo errado no Digifarma. Confira o estoque físico antes de mexer na escrituração.'],
  anvisa_zerada_lote: ['Lote zerado na ANVISA', 'sobra',
    'A ANVISA tem saldo em outros lotes deste medicamento, mas não neste. Confira o número do lote e a entrada dele.'],
  quantidade: ['Quantidade diferente', 'sobra',
    'Os dois lados têm o lote, com contagens diferentes. É conferência de prateleira.'],
  so_na_anvisa: ['Só no inventário SNGPC', 'falta',
    'A ANVISA tem saldo deste lote e o Digifarma não. Costuma ser saída lançada só de um lado.'],
  negativo: ['Saldo negativo no Digifarma', 'falta',
    'O próprio Digifarma está com saldo negativo neste lote: saída lançada sem a entrada. Corrija no Digifarma.']
};

/* Ordem de gravidade, não alfabética: é a ordem em que a farmácia resolve. */
const ORDEM_MOTIVO = ['negativo', 'so_na_anvisa', 'quantidade',
  'anvisa_zerada_lote', 'anvisa_zerada_produto'];

/* indexOf devolve -1 para o que não está na lista, e -1 ordena ANTES de
   tudo: item sem motivo — de uma publicação antiga do agente, por exemplo —
   ia parar no topo, acima dos saldos negativos. Desconhecido vai para o fim. */
function ordemDoMotivo(motivo) {
  const i = ORDEM_MOTIVO.indexOf(motivo);
  return i === -1 ? ORDEM_MOTIVO.length : i;
}

/* Psicotrópico e antimicrobiano são duas escriturações e duas conferências:
   a receita de psicotrópico fica retida, a de antimicrobiano não. Quem
   confere faz uma lista de cada vez, então a tela separa as duas.
   O agente antigo publicava item sem classe; esses ficam no fim, juntos. */
const CLASSES_SALDO = ['psicotropico', 'antimicrobiano'];
const NOME_CLASSE = {
  psicotropico: 'Psicotrópicos e entorpecentes',
  antimicrobiano: 'Antimicrobianos',
  '': 'Sem classe marcada no cadastro'
};

function ordemDaClasse(classe) {
  const i = CLASSES_SALDO.indexOf(classe);
  return i === -1 ? CLASSES_SALDO.length : i;
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

  // O site da ANVISA já recebeu o que este Digifarma ainda tem na fila:
  // a mesma venda é descontada dos dois lados e a lista incha. Avisar vale
  // mais que o número, porque transmitir daqui escrituraria tudo em dobro.
  const ja = Number(inv.jaNaAnvisa || 0);
  const naFila = Number(estado.inventario?.resumoPendentes?.vendas || 0);
  if (ja && naFila) {
    barra.textContent = ja + ' lote(s) já batem com a ANVISA sem contar o que está na '
      + 'fila: o site recebeu essas vendas e o ponteiro do Digifarma não avançou. '
      + 'Os números abaixo estão inflados — e transmitir por este computador '
      + 'escrituraria as ' + naFila + ' venda(s) em dobro.';
    barra.hidden = false;
    return;
  }

  const resumo = estado.inventario?.resumoSaldo;
  if (resumo) {
    const partes = Object.entries(resumo)
      // o sem_ms tem bloco próprio logo abaixo; repetir aqui só polui
      .filter(([motivo, n]) => n > 0 && motivo !== 'sem_ms')
      .sort((a, b) => b[1] - a[1])
      .map(([motivo, n]) => n + ' ' + (MOTIVO_SALDO[motivo]?.[0] || motivo).toLowerCase());
    if (partes.length) {
      barra.textContent = partes.join(' · ');
      barra.hidden = false;
      return;
    }
  }
  barra.hidden = true;
}

function pintarSemMs() {
  const itens = pendenciasDeCadastro();
  $('bloco-sem-ms').hidden = itens.length === 0;
  const alvo = $('lista-sem-ms');
  alvo.innerHTML = '';
  itens.forEach((i, n) => {
    alvo.appendChild(linha({
      chave: 'semms:' + (i.codigo || n) + ':' + (i.lote || ''),
      titulo: i.descricao || i.codigo || '(sem descrição)',
      meta: [
        i.ean && 'EAN ' + i.ean,
        i.lote && 'Lote ' + i.lote,
        i.validade && 'Val. ' + i.validade
      ],
      tarja: ['Cadastrar o registro M.S.', i.saldoDigifarma + ' em estoque'],
      tarjaClasse: 'falta',
      detalhe: definicoes([
        ['Código', i.codigo],
        ['Saldo Digifarma', i.saldoDigifarma],
        ['Código de barras', i.ean],
        ['Lote', i.lote],
        ['Validade', i.validade]
      ])
    }));
  });
}

function pintarSaldo() {
  pintarAlertaSaldo();
  pintarSemMs();
  const alvo = $('lista-saldo');
  alvo.innerHTML = '';
  // Cem itens numa lista corrida não se trabalha. Cada tipo se resolve num
  // lugar diferente, então a lista vem agrupada — e a ordem dos grupos é a
  // ordem de gravidade: dado torto no Digifarma primeiro, porque reaparece
  // em toda conferência; depois o que sumiu do estoque e o SNGPC ainda
  // acusa; por último o que a ANVISA só não recebeu ainda.
  // Dentro do grupo, ordem alfabética pelo nome: é assim que o medicamento
  // é procurado na prateleira, e é a ordem em que a folha impressa sai.
  const itens = divergenciasDeSaldo()
    .filter((i) => combina(i, estado.buscaSaldo, ['descricao', 'ms', 'ean', 'lote', 'codigo']))
    .sort((a, b) => (ordemDaClasse(a.classe) - ordemDaClasse(b.classe))
      || (ordemDoMotivo(a.motivo) - ordemDoMotivo(b.motivo))
      || (a.descricao || '').localeCompare(b.descricao || '', 'pt-BR')
      || (a.lote || '').localeCompare(b.lote || '', 'pt-BR'));
  $('saldo-vazio').hidden = itens.length > 0 || !!estado.buscaSaldo;

  const quantosPorMotivo = {};
  const quantosPorClasse = {};
  itens.forEach((i) => {
    const c = CLASSES_SALDO.includes(i.classe) ? i.classe : '';
    quantosPorMotivo[c + '|' + i.motivo] = (quantosPorMotivo[c + '|' + i.motivo] || 0) + 1;
    quantosPorClasse[c] = (quantosPorClasse[c] || 0) + 1;
  });

  let classeAtual = null;
  let grupoAtual = null;
  itens.forEach((i, n) => {
    const daLista = CLASSES_SALDO.includes(i.classe) ? i.classe : '';
    if (daLista !== classeAtual) {
      classeAtual = daLista;
      grupoAtual = null;
      const cabeca = criar('h3', 'grupo-saldo grupo-classe');
      const nome = criar('span');
      nome.textContent = NOME_CLASSE[daLista];
      const conta = criar('span', 'grupo-conta');
      conta.textContent = quantosPorClasse[daLista];
      cabeca.append(nome, conta);
      alvo.appendChild(cabeca);
    }
    if (i.motivo && i.motivo !== grupoAtual) {
      grupoAtual = i.motivo;
      const cabeca = criar('h3', 'grupo-saldo');
      const nome = criar('span');
      nome.textContent = MOTIVO_SALDO[grupoAtual]?.[0] || grupoAtual;
      const conta = criar('span', 'grupo-conta');
      conta.textContent = quantosPorMotivo[classeAtual + '|' + grupoAtual];
      cabeca.append(nome, conta);
      alvo.appendChild(cabeca);
    }
    const dif = Number(i.diferenca || 0);
    const [rotulo, classe, explicacao] = MOTIVO_SALDO[i.motivo]
      || [dif < 0 ? 'Falta no Digifarma' : 'Sobra no Digifarma', dif < 0 ? 'falta' : 'sobra', ''];
    const detalhe = definicoes([
      ['Código', i.codigo],
      ['Digifarma (este lote)', i.saldoDigifarma],
      // só vêm quando LOTES é tabela de movimento: mostram de onde
      // o saldo saiu, para conferir contra a tela do Digifarma
      ['Entrou no lote', i.entradas],
      ['Baixado (vendas e perdas)', i.baixas],
      // a conta, na ordem em que se lê: a foto do último envio, o que se
      // moveu desde então, o que o SNGPC deveria mostrar, e o que o
      // Digifarma mostra. A diferença é do último par, não do primeiro.
      ['SNGPC no último envio', i.saldoSngpc],
      ['Movimento desde o envio', i.movimentoDesdeEnvio === undefined ? undefined
        : (i.movimentoDesdeEnvio > 0 ? '+' : '') + i.movimentoDesdeEnvio],
      ['Esperado no SNGPC hoje', i.esperadoSngpc],
      ['Diferença', (dif > 0 ? '+' : '') + dif],
      // a tela do Digifarma mostra o produto inteiro; a conferência é por
      // lote. Sem estes dois, o número do app não bate com o da tela e
      // parece errado quando está certo.
      ['Digifarma (todos os lotes)', i.saldoDigifarmaMs],
      ['SNGPC (todos os lotes)', i.saldoSngpcMs],
      ['Registro M.S.', i.ms],
      ['Código de barras', i.ean],
      ['Lote', i.lote],
      ['Validade', i.validade],
      ['Classe', i.classe ? (NOME_CLASSE[i.classe] || i.classe) : undefined]
    ]);
    if (explicacao) {
      const nota = criar('p', 'nota-info');
      nota.textContent = explicacao;
      detalhe.appendChild(nota);
    }
    if (i.movimentoDesdeEnvio !== undefined) {
      const nota = criar('p', 'nota-info');
      nota.textContent = 'Este lote se moveu depois do último envio. O inventário do '
        + 'SNGPC é a foto daquele momento, então a conferência soma o que entrou e '
        + 'desconta o que saiu desde então — a diferença é contra o esperado, não '
        + 'contra a foto.';
      detalhe.appendChild(nota);
    }
    if (i.saldoDigifarmaMs !== undefined) {
      const nota = criar('p', 'nota-info');
      nota.textContent = 'Este medicamento tem mais de um lote. A tela do Digifarma soma '
        + 'todos; aqui a conferência é lote a lote, porque é assim que o SNGPC guarda. '
        + 'Os outros lotes não aparecem nesta lista quando batem com a ANVISA.';
      detalhe.appendChild(nota);
    }
    // todos os lotes do medicamento, inclusive os que batem e por isso não
    // entram na lista — é o que explica o total e permite conferir na tela
    if (Array.isArray(i.lotesDoMs) && i.lotesDoMs.length > 1) {
      const titulo = criar('p', 'linha-titulo');
      titulo.style.margin = '14px 0 6px';
      titulo.textContent = 'Todos os lotes deste medicamento';
      detalhe.appendChild(titulo);
      const dl = criar('dl', 'dados');
      i.lotesDoMs.forEach((l) => {
        const dt = criar('dt');
        dt.textContent = 'Lote ' + (l.lote || '(vazio)') + (l.lote === i.lote ? ' ←' : '');
        const dd = criar('dd');
        dd.textContent = 'Digifarma ' + Number(l.digifarma || 0)
          + ' · SNGPC ' + Number(l.sngpc || 0);
        dl.append(dt, dd);
      });
      detalhe.appendChild(dl);
    }

    // A primeira pergunta diante de uma divergência é "esse saiu?". Sem a
    // resposta aqui, a conferência começa indo à prateleira procurar um
    // lote que pode simplesmente ter sido vendido.
    const v = i.vendas;
    if (v && v.linhas) {
      const titulo = criar('p', 'linha-titulo');
      titulo.style.margin = '14px 0 6px';
      titulo.textContent = 'Vendas deste lote';
      detalhe.appendChild(titulo);
      detalhe.appendChild(definicoes([
        ['Saiu', Number(v.quantidade || 0) + ' em ' + v.linhas + ' venda(s)'],
        ['Últimos', (v.dias || 45) + ' dias'],
        ['Última venda', v.ultima
          ? dataHora(v.ultima) + (v.ultimaVenda ? ' · nº ' + v.ultimaVenda : '')
          : undefined],
        // Só o lado negativo do teste é confiável: o Digifarma cria a linha
        // da receita junto com a venda e preenche depois, então "tem linha"
        // não prova que a receita foi lançada. Faltar a linha, sim, prova.
        ['Sem receita no Digifarma', v.semReceita ? v.semReceita + ' venda(s)' : undefined]
      ]));
      const nota = criar('p', 'nota-info');
      nota.textContent = v.semReceita
        ? 'Há venda deste lote sem receita escriturada no Digifarma. Lance a receita '
          + 'antes do próximo envio — depois de transmitido o conserto é bem mais caro. '
          + 'O contrário não vale: não aparecer aqui não garante que as outras receitas '
          + 'estejam completas.'
        : 'Este lote saiu em venda. Confira se a diferença não é justamente o que foi '
          + 'vendido e ainda não subiu ao SNGPC, antes de contar na prateleira.';
      detalhe.appendChild(nota);
    }

    alvo.appendChild(linha({
      chave: 'saldo:' + (i.codigo || n) + ':' + (i.lote || ''),
      titulo: i.descricao || i.codigo || '(sem descrição)',
      meta: [
        i.ms && 'M.S. ' + i.ms,
        i.ean && 'EAN ' + i.ean,
        i.lote && 'Lote ' + i.lote,
        i.validade && 'Val. ' + i.validade,
        // sem abrir a linha: saiu ou não saiu, e se ficou receita para trás.
        // É o que decide entre ir à prateleira e ir ao Digifarma.
        v && v.linhas && 'Vendeu ' + Number(v.quantidade || 0),
        v && v.semReceita && v.semReceita + ' sem receita'
      ],
      // Dentro de um grupo, repetir o rótulo na tarja é desperdiçar a única
      // faixa que a linha tem. Ali vai a comparação, que é o que se quer ver
      // sem abrir: quanto tem de cada lado.
      tarja: [
        i.motivo
          ? 'Digifarma ' + Number(i.saldoDigifarma || 0) + ' · SNGPC ' + Number(i.saldoSngpc || 0)
          : rotulo,
        (dif > 0 ? '+' : '') + dif
      ],
      tarjaClasse: classe,
      detalhe
    }));
  });

  if (!itens.length && estado.buscaSaldo) {
    const p = criar('p', 'vazio');
    p.textContent = 'Nada encontrado para “' + estado.buscaSaldo + '”.';
    alvo.appendChild(p);
  }
}

/* Zero divergências pode ser conferência limpa ou conferência que não
   aconteceu. O texto do vazio tem que dizer qual dos dois. */
function textoXmlVazio() {
  const r = estado.inventario?.conferenciaXmlResumo;
  if (!r) return 'O agente ainda não conferiu o XML.';
  if (!r.conferiu) {
    return 'Não deu para conferir o XML: ' + (r.porque || 'motivo não informado')
      + '. Este zero não quer dizer que está tudo certo.';
  }
  if (!r.vendasNoBanco && !r.itensNoXml) {
    return 'Nenhuma venda de controlado entre ' + dataBR(r.periodoDe) + ' e '
      + dataBR(r.periodoAte) + ' — não havia nada a conferir neste envio.';
  }
  return 'Confere: ' + r.vendasNoBanco + ' saída(s) no banco e ' + r.itensNoXml
    + ' item(ns) no XML ' + esc(r.arquivo) + ', de ' + dataBR(r.periodoDe)
    + ' a ' + dataBR(r.periodoAte) + '. Tudo bateu.';
}

function pintarXml() {
  const alvo = $('lista-xml');
  alvo.innerHTML = '';
  const itens = pendenciasXml()
    .filter((c) => combina(c, estado.buscaXml, ['descricao', 'ms', 'lote']));
  $('xml-vazio').textContent = textoXmlVazio();
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
  const desde = estado.inventario?.vendasProblemaDesde;
  // a consulta corta por data: sem dizer desde quando, o zero parece
  // valer para toda a história da farmácia
  $('vendas-vazio').textContent = desde
    ? 'Nenhuma venda pendente de correção desde ' + dataBR(desde)
      + '. Vendas anteriores a essa data não entram nesta conferência.'
    : 'Nenhuma venda pendente de correção.';
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

/* Acompanhamento das vendas: sobe pela tarefa de cada minuto, então a
   tela vive sozinha — o Firebase empurra a atualização sem ninguém recarregar. */
function pintarSemReceita() {
  const itens = lista('vendasSemReceita');
  $('bloco-sem-receita').hidden = itens.length === 0;
  const alvo = $('lista-sem-receita');
  alvo.innerHTML = '';
  itens.forEach((v, n) => {
    alvo.appendChild(linha({
      chave: 'semreceita:' + (v.venda ?? n) + ':' + (v.lote || ''),
      titulo: v.descricao || ('Venda ' + (v.venda ?? '?')),
      meta: [
        v.quando && horaBR(v.quando),
        v.ms && 'M.S. ' + v.ms,
        v.lote ? 'Lote ' + v.lote : 'Sem lote'
      ],
      tarja: ['Escriturar a receita', 'Venda ' + (v.venda ?? '—')],
      tarjaClasse: 'falta',
      detalhe: definicoes([
        ['Venda', v.venda],
        ['Quando', horaBR(v.quando)],
        ['Produto', v.descricao],
        ['Registro M.S.', v.ms],
        ['Lote', v.lote],
        ['Quantidade', v.quantidade]
      ])
    }));
  });
}

function pintarVendasRecentes() {
  const alvo = $('lista-vendas-recentes');
  if (!alvo) return;
  alvo.innerHTML = '';

  const carimbo = estado.inventario?.vendasRecentesEm;
  $('vendas-recentes-carimbo').textContent = carimbo
    ? 'Atualizado em ' + dataHora(carimbo)
    : 'O agente ainda não publicou as vendas. A tarefa de cada minuto faz isso sozinha.';

  const todas = lista('vendasRecentes');
  const itens = todas.filter((v) => combina(
    { ...v, venda: String(v.venda ?? '') },
    estado.buscaVendas, ['descricao', 'lote', 'venda', 'ms']));

  if (!itens.length) {
    const p = criar('p', 'vazio');
    p.textContent = todas.length
      ? 'Nada encontrado para “' + estado.buscaVendas + '”.'
      : 'Nenhuma venda de controlado nos últimos dias.';
    alvo.appendChild(p);
    return;
  }

  itens.slice(0, 300).forEach((v) => {
    const el = criar('div', 'aceite');

    const esquerda = criar('div');
    const titulo = criar('p', 'aceite-data');
    titulo.textContent = v.descricao || '(sem descrição)';
    esquerda.appendChild(titulo);
    const sub = criar('p', 'sublinha');
    sub.style.margin = '2px 0 0';
    sub.textContent = 'Venda ' + (v.venda ?? '—')
      + (v.lote ? ' · Lote ' + v.lote : ' · sem lote')
      + (v.ms ? ' · M.S. ' + v.ms : '');
    esquerda.appendChild(sub);
    el.appendChild(esquerda);

    const direita = criar('div');
    direita.style.display = 'flex';
    direita.style.gap = '10px';
    direita.style.alignItems = 'center';
    /* O rótulo verde já esteve aqui, saiu, e voltou — mas só agora com base
       para existir. Antes o agente testava se havia LINHA em
       VENDAS_PSICOTROPICOS, e o Digifarma cria a linha junto com a venda:
       dizia "receita ok" em venda que a farmácia sabia não ter lançado.
       Agora o teste é o PRESCRITOR preenchido, medido pelo --receitas contra
       vendas que a farmácia confirmou uma a uma. Os dois lados valem. */
    const receita = criar('span', v.receita ? 'estado estado-aceito' : 'estado estado-recusado');
    receita.textContent = v.receita ? 'receita ok' : 'SEM RECEITA';
    direita.appendChild(receita);
    const qtd = criar('span', 'estado estado-aceito');
    qtd.textContent = Number(v.quantidade || 0) + ' un';
    const hora = criar('span', 'sublinha');
    hora.textContent = horaBR(v.quando);
    direita.append(qtd, hora);
    el.appendChild(direita);

    alvo.appendChild(el);
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

/* Movimento de envio recusado NÃO entra no inventário do SNGPC. Por isso um
   envio sem aceite marcado não é só papelada atrasada: é a explicação mais
   provável para lote que a farmácia transmitiu e a ANVISA não tem. A aba
   precisa cobrar, não esperar. */
function envioSemAceite() {
  return datasDeEnvio().filter((d) => !estado.aceites?.[d]?.status);
}

function pintarAlertaAceites() {
  const barra = $('aceites-alerta');
  const pendentes = envioSemAceite();
  if (!pendentes.length) { barra.hidden = true; return; }

  const zerados = (estado.inventario?.resumoSaldo || {}).anvisa_zerada_produto || 0;
  barra.textContent = pendentes.length === 1
    ? 'O envio de ' + dataBR(pendentes[0]) + ' ainda não foi conferido no site da ANVISA.'
      + (zerados ? ' Há ' + zerados + ' lote(s) que a farmácia transmitiu e o SNGPC não '
        + 'tem — se este envio foi recusado, é exatamente isso que acontece.' : '')
    : pendentes.length + ' envios sem aceite marcado, de ' + dataBR(pendentes[pendentes.length - 1])
      + ' a ' + dataBR(pendentes[0]) + '. Envio recusado não entra no inventário do SNGPC: '
      + 'enquanto não se sabe quais foram aceitos, divergência de saldo fica sem explicação.';
  barra.hidden = false;
}

function pintarAceites() {
  pintarAlertaAceites();
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
  module.exports = {
    normalizar, combina, dataBR, horaBR,
    divergenciasDeSaldo, pendenciasDeCadastro
  };
}
