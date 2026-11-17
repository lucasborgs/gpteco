param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Revisao
)

& {
    $ErrorActionPreference = 'Stop'
    $versao = $Revisao.Substring(0, 7)
    $imagem = "iamlucb/gpteco:main-$versao"

    function Read-ComposeConfig {
        $json = docker compose -f docker-compose.dist.yml config --format json
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao ler o Compose.' }
        return (($json -join "`n") | ConvertFrom-Json)
    }

    $antes = Read-ComposeConfig
    $montagemAtual = @($antes.services.servidor.volumes | Where-Object {
        $_.type -eq 'bind' -and $_.target -eq '/app/config/assistente.md'
    })
    if ($montagemAtual.Count -ne 1 -or
        $antes.services.servidor.environment.ASSISTANT_PROFILE_PATH -ne '/app/config/assistente.md') {
        throw 'Perfil editavel nao encontrado. Envie esta mensagem antes de continuar.'
    }

    docker pull --platform linux/amd64 $imagem
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar a imagem. Nada foi alterado.' }
    $metaJson = docker image inspect $imagem
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar a imagem.' }
    $meta = @(($metaJson -join "`n") | ConvertFrom-Json)[0]
    if ($meta.Config.Labels.'org.opencontainers.image.revision' -ne $Revisao) {
        throw 'A imagem nao corresponde ao commit esperado. Nada foi alterado.'
    }

    $raiz = (Get-Location).Path
    $data = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $backup = Join-Path (Join-Path $env:LOCALAPPDATA 'gpteco\backups') "curiosidades-$data"
    $nomePerfil = "assistente.curiosidades-$versao-$data.md"
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $raiz '.env') -Destination (Join-Path $backup 'env.original')
    docker compose -f docker-compose.dist.yml cp 'servidor:/app/config/assistente.md' (Join-Path $backup 'perfil.original.md')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar o perfil atual. Instalacao preservada.' }
    Write-Host "Backup: $backup"

    @'
import codecs, os, re, sys
from pathlib import Path
from core import luzia
from core.luzia.schema import validar

pasta = Path(sys.argv[1])
def ler(caminho):
    b = caminho.read_bytes()
    enc = 'utf-16' if b.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-8-sig'
    return b.decode(enc).replace('\r\n', '\n')

original = ler(pasta / 'perfil.original.md')
padrao = re.compile(r'(?ms)(^## pilula_prefixo[ \t]*\n).*?(?=^#{1,2} |\Z)')
novo, quantidade = padrao.subn(lambda m: m.group(1) + '*Curiosidade:*\n\n', original)
if quantidade != 1:
    raise RuntimeError('Secao pilula_prefixo ausente ou duplicada; perfil preservado')
assert padrao.sub('', original) == padrao.sub('', novo), 'Conteudo fora do cabecalho alterado'
destino = pasta / 'perfil.novo.md'
destino.write_text(novo, encoding='utf-8')
os.environ['ASSISTANT_PROFILE_PATH'] = str(destino)
erros = validar()
if erros:
    raise RuntimeError('Perfil invalido: ' + '; '.join(erros))
assert luzia.MSG_PILULA_PREFIXO == '*Curiosidade:*\n\n'

env = ler(pasta / 'env.original')
for k, v in {
    'GPTECO_IMAGE': os.environ['NOVA_IMAGEM'],
    'ASSISTANT_PROFILE_FILE': './' + os.environ['NOVO_PERFIL'],
}.items():
    chave = r'(?m)^[ \t]*(?:export[ \t]+)?' + re.escape(k) + r'[ \t]*=[^\r\n]*'
    if re.search(chave, env):
        env = re.sub(chave, lambda m: k + '=' + v, env)
    else:
        env = env.rstrip('\n') + '\n' + k + '=' + v + '\n'
(pasta / 'env.novo').write_text(env, encoding='utf-8')
print('Perfil validado; somente o cabecalho da curiosidade foi alterado.')
'@ | docker run --rm -i --platform linux/amd64 --network none --mount "type=bind,source=$backup,target=/upgrade" --env "NOVA_IMAGEM=$imagem" --env "NOVO_PERFIL=$nomePerfil" --entrypoint python $imagem -B - /upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Falha na preparacao. A instalacao atual foi preservada.' }

    Copy-Item -LiteralPath (Join-Path $backup 'perfil.novo.md') -Destination (Join-Path $raiz $nomePerfil)
    $recriacaoIniciada = $false
    try {
        Copy-Item -LiteralPath (Join-Path $backup 'env.novo') -Destination (Join-Path $raiz '.env') -Force
        $depois = Read-ComposeConfig
        if ($depois.services.servidor.image -ne $imagem) {
            throw 'O Compose nao assumiu a imagem nova.'
        }
        foreach ($servico in $antes.services.PSObject.Properties) {
            if ($servico.Name -eq 'servidor') { continue }
            $valorDepois = $depois.services.PSObject.Properties[$servico.Name].Value
            if (($servico.Value | ConvertTo-Json -Depth 100 -Compress) -ne
                ($valorDepois | ConvertTo-Json -Depth 100 -Compress)) {
                throw "Mudanca inesperada em outro servico: $($servico.Name)"
            }
        }
        $montagem = @($depois.services.servidor.volumes | Where-Object {
            $_.target -eq '/app/config/assistente.md'
        })
        if ($montagem.Count -ne 1 -or
            [IO.Path]::GetFullPath($montagem[0].source) -ne (Join-Path $raiz $nomePerfil)) {
            throw 'O Compose nao assumiu o novo perfil.'
        }

        $recriacaoIniciada = $true
        docker compose -f docker-compose.dist.yml up -d --no-deps --no-build --pull never --force-recreate servidor
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao recriar o servidor.' }

        $pronto = $false
        for ($tentativa = 0; $tentativa -lt 20; $tentativa++) {
            try {
                $resposta = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8002/openapi.json' -TimeoutSec 3
                if ($resposta.StatusCode -eq 200) { $pronto = $true; break }
            } catch { }
            Start-Sleep -Seconds 2
        }
        if (-not $pronto) { throw 'O servidor nao ficou pronto no tempo esperado.' }

        docker compose -f docker-compose.dist.yml exec -T servidor python -B -c "import hashlib; from pathlib import Path; from core import curador, luzia; assert hashlib.sha256(Path(curador.__file__).read_bytes()).hexdigest() == '1eb0ed82f7e63af0fe3b17cffbe77f9e98a5a66c48350cb100a9fc6c8201d91d'; assert luzia.MSG_PILULA_PREFIXO == '*Curiosidade:*\n\n'; assert str(luzia._cache['path']) == '/app/config/assistente.md'; print('ATUALIZACAO_OK: curiosidades contextualizadas / Curiosidade')"
        if ($LASTEXITCODE -ne 0) { throw 'Falha na verificacao do codigo ou do perfil instalado.' }
    } catch {
        $motivo = $_.Exception.Message
        Copy-Item -LiteralPath (Join-Path $backup 'env.original') -Destination (Join-Path $raiz '.env') -Force
        if ($recriacaoIniciada) {
            docker compose -f docker-compose.dist.yml up -d --no-deps --no-build --pull never --force-recreate servidor
            if ($LASTEXITCODE -ne 0) {
                throw "Falha na atualizacao e na reversao. Backup: $backup. Motivo inicial: $motivo"
            }
        }
        throw "Atualizacao cancelada; configuracao anterior restaurada. Motivo: $motivo"
    }
    Write-Host "Perfil ativo: $nomePerfil"
    docker compose -f docker-compose.dist.yml ps servidor
}
