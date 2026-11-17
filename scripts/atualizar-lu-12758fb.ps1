& {
    $ErrorActionPreference = 'Stop'
    $imagem = 'iamlucb/gpteco:main-12758fb'
    $revisao = '12758fb6fac577e0614350efb2a66d47fa71a893'

    function Read-ComposeConfig {
        $json = docker compose -f docker-compose.dist.yml config --format json
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao ler o Compose.' }
        return (($json -join "`n") | ConvertFrom-Json)
    }

    $antes = Read-ComposeConfig
    $perfil = @($antes.services.servidor.volumes | Where-Object {
        $_.target -eq '/app/config/assistente.md'
    })
    if ($perfil.Count -ne 1 -or -not (Test-Path -LiteralPath $perfil[0].source -PathType Leaf)) {
        throw 'Perfil atual nao encontrado como arquivo. Envie esta mensagem antes de continuar.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$antes.services.servidor.environment.OPENAI_API_KEY)) {
        throw 'Configure OPENAI_API_KEY no .env para usar GPT-5.6. Nao envie a chave aqui.'
    }

    docker pull --platform linux/amd64 $imagem
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar a imagem. Nada foi alterado.' }
    $metaJson = docker image inspect $imagem
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar a imagem.' }
    $meta = @(($metaJson -join "`n") | ConvertFrom-Json)[0]
    if ($meta.Config.Labels.'org.opencontainers.image.revision' -ne $revisao) {
        throw 'A imagem nao corresponde ao commit esperado.'
    }

    $raiz = (Get-Location).Path
    $data = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $backup = Join-Path (Join-Path $env:LOCALAPPDATA 'gpteco\backups') "lu-$data"
    $nomePerfil = "assistente.lu-12758fb-$data.md"
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $raiz '.env') -Destination (Join-Path $backup 'env.original')
    Copy-Item -LiteralPath $perfil[0].source -Destination (Join-Path $backup 'perfil.original.md')
    Write-Host "Backup: $backup"

    @'
import codecs, os, re
from pathlib import Path
from core import luzia
from core.luzia.schema import validar

pasta = Path('/upgrade')
def ler(caminho):
    b = caminho.read_bytes()
    enc = 'utf-16' if b.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-8-sig'
    return b.decode(enc).replace('\r\n', '\n')

original = ler(pasta / 'perfil.original.md')
novo = Path('/app/config/assistente.md').read_text(encoding='utf-8')
def chave(bloco):
    return luzia._canonical(bloco.splitlines()[0][2:]) if bloco.startswith('# ') else None
partes = lambda texto: re.split(r'(?m)(?=^# )', texto)
substituir = {'mensagens', 'tom', 'composer', 'curador', 'classificador'}
novas = {chave(b): b for b in partes(novo) if chave(b) in substituir}
vistas = {chave(b) for b in partes(original)}
mesclado = ''.join(novas.get(chave(b), b) for b in partes(original))
for k in novas:
    if k not in vistas:
        mesclado += '\n\n' + novas[k]
antigo, atual = luzia._parse(original), luzia._parse(mesclado)
assert antigo['frontmatter'] == atual['frontmatter'], 'Metadados alterados'
for k in ('repertorio', 'regras_duras'):
    assert antigo['secoes'].get(k) == atual['secoes'].get(k), 'Regra alterada: ' + k
destino = pasta / 'perfil.novo.md'
destino.write_text(mesclado, encoding='utf-8')
os.environ['ASSISTANT_PROFILE_PATH'] = str(destino)
erros = validar()
if erros:
    raise RuntimeError('Perfil invalido: ' + '; '.join(erros))

env = ler(pasta / 'env.original')
valores = {
    'GPTECO_IMAGE': 'iamlucb/gpteco:main-12758fb',
    'YT_PLAYER_CLIENT': 'default',
    'COMPOSER_MODELO': 'gpt-5.6',
    'PILULAS_MODELO': 'gpt-5.6',
    'PILULAS_CONTEXTO_MODELO': 'gpt-5.6',
    'CANAL_VOZ_ATIVADO': 'true',
    'ASSISTANT_PROFILE_FILE': './' + os.environ['NOVO_PERFIL'],
}
for k, v in valores.items():
    padrao = r'(?m)^[ \t]*(?:export[ \t]+)?' + re.escape(k) + r'[ \t]*=[^\r\n]*'
    if re.search(padrao, env):
        env = re.sub(padrao, lambda m: k + '=' + v, env)
    else:
        env = env.rstrip('\n') + '\n' + k + '=' + v + '\n'
(pasta / 'env.novo').write_text(env, encoding='utf-8')
print('Perfil validado; dados da radio, repertorio e regras duras preservados.')
'@ | docker run --rm -i --platform linux/amd64 --network none --mount "type=bind,source=$backup,target=/upgrade" --env "NOVO_PERFIL=$nomePerfil" --entrypoint python $imagem -B -
    if ($LASTEXITCODE -ne 0) { throw 'Falha na preparacao. A instalacao atual foi preservada.' }

    Copy-Item -LiteralPath (Join-Path $backup 'perfil.novo.md') -Destination (Join-Path $raiz $nomePerfil)
    $recriacaoIniciada = $false
    try {
        Copy-Item -LiteralPath (Join-Path $backup 'env.novo') -Destination (Join-Path $raiz '.env') -Force
        $depois = Read-ComposeConfig
        if ($depois.services.servidor.image -ne $imagem -or
            $depois.services.servidor.environment.YT_PLAYER_CLIENT -ne 'default') {
            throw 'O Compose nao assumiu a imagem ou o cliente esperado.'
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

        docker compose -f docker-compose.dist.yml exec -T servidor python -B -c "from core import luzia, composer, curador, downloader; assert downloader.YT_PLAYER_CLIENT == 'default'; assert composer.MODELO == curador.PILULAS_MODELO == curador.PILULAS_CONTEXTO_MODELO == 'gpt-5.6'; assert 'voz feminina' in luzia.tom_luzia(); print('ATUALIZACAO_OK: Lu / GPT-5.6 / YouTube default')"
        if ($LASTEXITCODE -ne 0) { throw 'Falha na verificacao final.' }
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
