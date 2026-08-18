# ============================================================
#  instalar_chromedriver.ps1
#
#  Poe na pasta do Anvisa.exe um chromedriver da mesma versao
#  do Chrome instalado. Chamado pelo INSTALAR_CHROMEDRIVER.bat.
#
#  O Anvisa.exe e automacao de navegador: sem esse arquivo ele
#  abre e fecha na hora, sem log e com codigo 0 - foi assim que
#  ele apareceu quebrado na farmacia em 18/08/2026.
#
#  Nao adivinha a versao: le o Chrome instalado e pergunta ao
#  Google qual driver corresponde. Tenta as fontes em ordem e
#  diz qual funcionou, para a proxima vez ser direta.
# ============================================================

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # sem isto o download fica lento
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Pasta = 'C:\Digifarma\Aplicativos\VerificaXML'
$Destino = Join-Path $Pasta 'chromedriver.exe'
$Base = 'https://storage.googleapis.com/chrome-for-testing-public'
$Cft  = 'https://googlechromelabs.github.io/chrome-for-testing'

function Diga($texto) { Write-Host "  $texto" }

Write-Host ''
Write-Host ' ============================================================'
Write-Host '  CHROMEDRIVER PARA O ANVISA.EXE'
Write-Host ' ============================================================'
Write-Host ''

if (-not (Test-Path $Pasta)) {
  Diga "NAO ACHEI a pasta $Pasta"
  Diga 'Ajuste o caminho no topo deste arquivo.'
  exit 1
}

# ---------- 1. que Chrome esta instalado ----------
# Filtra as raizes ANTES de montar o caminho: em Windows de 32 bits
# a variavel ProgramFiles(x86) nao existe, e Join-Path com nulo
# derruba o script inteiro por causa do ErrorActionPreference Stop.
$raizes = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) |
          Where-Object { $_ }
$chrome = $raizes |
          ForEach-Object { Join-Path $_ 'Google\Chrome\Application\chrome.exe' } |
          Where-Object { Test-Path $_ } |
          Select-Object -First 1
if (-not $chrome) {
  Diga 'NAO ACHEI o Chrome instalado.'
  Diga 'O Anvisa.exe precisa do Chrome; instale-o antes.'
  exit 1
}
$versaoChrome = (Get-Item $chrome).VersionInfo.ProductVersion
$maior = $versaoChrome.Split('.')[0]
Diga "Chrome $versaoChrome"
Diga "em $chrome"
Write-Host ''

# ---------- 2. que driver corresponde ----------
# Varias fontes porque o Google ja mudou o endereco disto mais de
# uma vez. A ordem vai da mais especifica para a mais generica, e
# no fim o script diz qual respondeu.
$versoes = New-Object System.Collections.Generic.List[string]
function Junte($v, $de) {
  if ($v -and -not $versoes.Contains("$v")) {
    $versoes.Add("$v")
    Diga "candidata $v  ($de)"
  }
}

Diga 'Perguntando ao Google qual driver corresponde...'
Junte $versaoChrome 'mesma versao do Chrome'

try {
  $b = ($versaoChrome.Split('.')[0..2]) -join '.'
  $j = Invoke-RestMethod -Uri "$Cft/latest-patch-versions-per-build.json" -TimeoutSec 40
  Junte $j.builds.$b.version 'ultimo patch deste build'
} catch { Diga "  (a tabela de builds nao respondeu: $($_.Exception.Message))" }

try {
  Junte (Invoke-RestMethod -Uri "$Cft/LATEST_RELEASE_$maior" -TimeoutSec 40).Trim() "ultimo do marco $maior"
} catch { Diga "  (o endereco por marco nao respondeu)" }

try {
  $j = Invoke-RestMethod -Uri "$Cft/last-known-good-versions.json" -TimeoutSec 40
  Junte $j.channels.Stable.version 'canal estavel'
} catch { Diga '  (a lista de versoes boas nao respondeu)' }

if ($versoes.Count -eq 0) {
  Diga 'Nenhuma fonte respondeu. Sem internet, ou o Google mudou os enderecos.'
  exit 1
}
Write-Host ''

# ---------- 3. baixar ----------
$temp = Join-Path $env:TEMP ('chromedriver_' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$zip = Join-Path $temp 'driver.zip'
$baixou = $null

foreach ($v in $versoes) {
  foreach ($plataforma in @('win64', 'win32')) {
    $url = "$Base/$v/$plataforma/chromedriver-$plataforma.zip"
    try {
      Invoke-WebRequest -Uri $url -OutFile $zip -TimeoutSec 120
      $baixou = @{ versao = $v; plataforma = $plataforma; url = $url }
      break
    } catch { }
  }
  if ($baixou) { break }
}

if (-not $baixou) {
  Diga 'Nenhuma das versoes candidatas tinha driver para baixar.'
  Diga 'Me mande esta tela: e informacao nova sobre os enderecos do Google.'
  Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
  exit 1
}

Diga "Baixado: $($baixou.url)"
if ($baixou.versao.Split('.')[0] -ne $maior) {
  Diga "ATENCAO: driver do marco $($baixou.versao.Split('.')[0]) para um Chrome $maior."
  Diga 'Pode nao funcionar. Foi o mais proximo que existia.'
}
Write-Host ''

# ---------- 4. instalar ----------
Expand-Archive -Path $zip -DestinationPath $temp -Force
$novo = Get-ChildItem -Path $temp -Filter 'chromedriver.exe' -Recurse |
        Select-Object -First 1
if (-not $novo) {
  Diga 'O zip nao trouxe chromedriver.exe dentro. Nada foi trocado.'
  Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
  exit 1
}

# Se ja existe um, guarda antes de trocar. Voltar atras tem que ser
# possivel sem baixar nada de novo.
if (Test-Path $Destino) {
  $backup = Join-Path $Pasta ('chromedriver_antes_de_' +
            (Get-Date -Format 'yyyy-MM-dd_HHmm') + '.exe')
  Copy-Item $Destino $backup -Force
  Diga "O driver antigo foi guardado em $(Split-Path $backup -Leaf)"
}

Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force
Copy-Item $novo.FullName $Destino -Force
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Diga "Instalado em $Destino"
Write-Host ''

# ---------- 5. conferir ----------
# Copiar nao e instalar: chromedriver e falso-positivo classico de
# antivirus, e sumir logo depois da copia e exatamente o que explica
# ele nao estar na pasta hoje. Por isso confere de novo depois de
# alguns segundos, em vez de dar por feito.
$saida = & $Destino --version 2>&1
Diga "Responde: $saida"

Start-Sleep -Seconds 5
if (-not (Test-Path $Destino)) {
  Write-Host ''
  Diga 'O ARQUIVO SUMIU LOGO DEPOIS DE INSTALADO.'
  Diga 'Isso e antivirus apagando: o chromedriver e falso-positivo'
  Diga 'classico. Abra o antivirus e crie uma excecao para a pasta'
  Diga "$Pasta - senao ele vai sumir de novo amanha."
  exit 1
}

Write-Host ''
Write-Host ' ------------------------------------------------------------'
Diga 'PRONTO. Agora abra o Anvisa.exe e faca o login no site do SNGPC.'
Diga 'O resto - ler o inventario e gravar no Digifarma - corre sozinho.'
Write-Host ' ------------------------------------------------------------'
Write-Host ''
exit 0
