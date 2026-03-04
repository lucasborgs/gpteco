@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Agente Virtual Musical — Instalador
echo ============================================================
echo.

:: ---- 1. Verifica Docker -----------------------------------------------
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Docker nao encontrado ou nao esta rodando.
    echo.
    echo Instale o Docker Desktop em: https://www.docker.com/products/docker-desktop/
    echo Apos instalar, abra o Docker Desktop e execute este script novamente.
    echo.
    pause
    exit /b 1
)
echo [OK] Docker encontrado.

:: ---- 2. Cria pastas necessarias ----------------------------------------
echo.
echo Criando pastas de trabalho...
if not exist "workspace\acervo_limpo" mkdir "workspace\acervo_limpo"
if not exist "workspace\fila_zara"    mkdir "workspace\fila_zara"
if not exist "workspace\temp"         mkdir "workspace\temp"
if not exist "data"                   mkdir "data"
echo [OK] Pastas criadas.

:: ---- 3. Cria .env a partir do .env.example (se nao existir) ------------
echo.
if exist ".env" (
    echo [OK] Arquivo .env ja existe — mantido sem alteracoes.
) else (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Arquivo .env criado a partir do .env.example.
        echo.
        echo  IMPORTANTE: Edite o arquivo .env antes de continuar.
        echo  Preencha as chaves:
        echo    GROQ_API_KEY  — obtenha em: console.groq.com
        echo    WAHA_API_KEY  — escolha uma senha qualquer (ex: minhaChave123)
        echo.
        echo  Pressione qualquer tecla apos editar o .env para continuar...
        pause >nul
    ) else (
        echo [AVISO] .env.example nao encontrado. Criando .env minimo...
        (
            echo GROQ_API_KEY=gsk_SUBSTITUA_PELA_SUA_CHAVE
            echo WHISPER_MODEL=whisper-large-v3-turbo
            echo DISABLE_COOLDOWN=false
            echo WAHA_URL=http://localhost:3001
            echo WAHA_API_KEY=minhaChave123
            echo WAHA_SESSION=default
        ) > .env
        echo [OK] .env criado. Edite-o com suas chaves antes de continuar.
        notepad .env
        echo.
        echo  Pressione qualquer tecla apos salvar o .env para continuar...
        pause >nul
    )
)

:: ---- 4. Baixa as imagens -----------------------------------------------
echo.
echo Baixando imagens Docker (pode demorar alguns minutos na primeira vez)...
echo.
docker compose -f docker-compose.dist.yml pull
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao baixar imagens. Verifique sua conexao com a internet.
    pause
    exit /b 1
)
echo.
echo [OK] Imagens baixadas.

:: ---- 5. Sobe os containers ---------------------------------------------
echo.
echo Iniciando os servicos...
docker compose -f docker-compose.dist.yml up -d
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao iniciar os servicos.
    echo Verifique os logs com: docker compose -f docker-compose.dist.yml logs
    pause
    exit /b 1
)

:: ---- 6. Aguarda WAHA inicializar ---------------------------------------
echo.
echo Aguardando WAHA inicializar (15 segundos)...
timeout /t 15 /nobreak >nul

:: ---- 7. Abre o dashboard -----------------------------------------------
echo.
echo Abrindo dashboard do WhatsApp no navegador...
start http://localhost:3001/dashboard

:: ---- 8. Instrucoes finais ----------------------------------------------
echo.
echo ============================================================
echo  Instalacao concluida!
echo ============================================================
echo.
echo  Proximos passos:
echo  1. No dashboard (http://localhost:3001/dashboard):
echo     - Login: admin / [valor de WAHA_API_KEY no .env]
echo     - A sessao "default" deve aparecer como WORKING
echo     - Se aparecer STOPPED, clique em Start
echo  2. Escaneie o QR Code com o WhatsApp do numero da radio
echo  3. Pronto! O agente ja esta recebendo pedidos.
echo.
echo  Comandos uteis:
echo    Ver logs:    docker compose -f docker-compose.dist.yml logs -f servidor
echo    Parar:       docker compose -f docker-compose.dist.yml down
echo    Atualizar:   docker compose -f docker-compose.dist.yml pull ^&^& docker compose -f docker-compose.dist.yml up -d
echo.
pause
