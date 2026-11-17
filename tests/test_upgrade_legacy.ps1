# Regressao: a instalacao antiga usa perfil embutido, sem bind mount.
# O Docker e simulado; este teste nao altera a instalacao.
function global:docker {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'pull') { throw 'CHEGOU_AO_PULL' }
    if ($args -contains 'config') {
        return '{"services":{"servidor":{"environment":{"OPENAI_API_KEY":"chave-ficticia"},"volumes":[{"type":"volume","source":"temp","target":"/app/workspace/temp"},{"type":"bind","source":"C:/LUZ FM/AR/MUSICAS","target":"/app/workspace/musicas"},{"type":"bind","source":"C:/Users/user","target":"/app/workspace/current_song"}]}}}'
    }
    if ($args -contains 'exec') { return '/app/core/luzia/luzia.md' }
    if ($args -contains 'ps') { return 'container-ficticio' }
    throw ('Chamada inesperada: ' + ($args -join ' '))
}
try {
    & (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/atualizar-lu-12758fb.ps1')
    Write-Output 'ERRO: instalador terminou sem chegar ao teste de compatibilidade'
    exit 1
} catch {
    if ($_.Exception.Message -eq 'CHEGOU_AO_PULL') {
        Write-Output 'LEGADO_SUPORTADO'
        exit 0
    }
    Write-Output $_.Exception.Message
    exit 1
}
