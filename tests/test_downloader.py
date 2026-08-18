import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def _import_downloader_with_fake_dependencies():
    fake_yt_dlp = types.ModuleType("yt_dlp")
    fake_yt_dlp.YoutubeDL = object

    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.extensions = types.SimpleNamespace(connection=object)
    fake_psycopg2_extras = types.ModuleType("psycopg2.extras")

    with patch.dict(
        sys.modules,
        {
            "yt_dlp": fake_yt_dlp,
            "psycopg2": fake_psycopg2,
            "psycopg2.extras": fake_psycopg2_extras,
        },
    ):
        sys.modules.pop("core.downloader", None)
        sys.modules.pop("core.database", None)
        return importlib.import_module("core.downloader")


def test_downloader_tenta_proximo_resultado_depois_de_403(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    chamadas: list[tuple[str, bool]] = []

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            chamadas.append((alvo, download))
            if not download:
                return {
                    "entries": [
                        {"id": "bloqueado", "duration": 180},
                        {"id": "disponivel", "duration": 210},
                    ]
                }
            if alvo.endswith("bloqueado"):
                raise RuntimeError("HTTP Error 403: Forbidden")
            (tmp_path / "disponivel.webm").write_bytes(b"audio")
            return {"ext": "webm", "title": "Resultado disponível"}

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL
    ):
        resultado = downloader._baixar_youtube("artista musica official audio")

    assert resultado == str(tmp_path / "disponivel.webm")
    assert chamadas == [
        ("ytsearch5:artista musica official audio", False),
        ("https://www.youtube.com/watch?v=bloqueado", True),
        ("https://www.youtube.com/watch?v=disponivel", True),
    ]


def test_downloader_remove_parcial_da_tentativa_falha(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                return {"entries": [{"id": "bloqueado", "duration": 180}]}
            parcial = tmp_path / "bloqueado.webm.part"
            parcial.write_bytes(b"parcial")
            raise RuntimeError("HTTP Error 403: Forbidden")

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL
    ):
        with pytest.raises(RuntimeError, match="bloqueados"):
            downloader._baixar_youtube("artista musica official audio")

    assert not (tmp_path / "bloqueado.webm.part").exists()


def test_downloader_preserva_parcial_preexistente_ao_limpar_tentativa(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    preexistente = tmp_path / "id.webm"
    preexistente.write_bytes(b"nao apagar")

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)):
        downloader._limpar_download_parcial("id", preservar={preexistente.resolve()})

    assert preexistente.read_bytes() == b"nao apagar"


def test_downloader_faz_fallback_lyrics_quando_todos_os_principais_sao_bloqueados(
    tmp_path: Path,
) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    buscas: list[str] = []
    processamento = Mock()
    registro = Mock()

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                buscas.append(alvo)
                if "lyrics" in alvo:
                    return {"entries": [{"id": "lyrics-ok", "duration": 200}]}
                return {
                    "entries": [
                        {"id": "bloqueado-1", "duration": 180},
                        {"id": "bloqueado-2", "duration": 210},
                    ]
                }
            if alvo.endswith("bloqueado-1") or alvo.endswith("bloqueado-2"):
                raise RuntimeError("HTTP Error 403: Forbidden")
            (tmp_path / "lyrics-ok.webm").write_bytes(b"audio")
            return {"ext": "webm", "title": "Lyrics"}

    processamento.side_effect = lambda _entrada, saida: Path(saida).write_bytes(b"mp3")

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader, "ACERVO_DIR", str(tmp_path / "acervo")
    ), patch.object(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL), patch.object(
        downloader, "_processar_ffmpeg", processamento
    ), patch.object(downloader.database, "inserir_musica", registro):
        resultado = downloader.baixar("artista", "musica")

    assert resultado == str(tmp_path / "acervo" / "artista - musica.mp3")
    assert buscas == [
        "ytsearch5:artista musica official audio",
        "ytsearch5:artista musica lyrics",
    ]
    processamento.assert_called_once_with(
        str(tmp_path / "lyrics-ok.webm"),
        str(tmp_path / "acervo" / "artista - musica.mp3"),
    )
    registro.assert_called_once_with(
        "artista", "musica", str(tmp_path / "acervo" / "artista - musica.mp3")
    )
    assert not (tmp_path / "lyrics-ok.webm").exists()


def test_downloader_falha_quando_principais_e_fallback_se_esgotam(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    buscas: list[str] = []

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                buscas.append(alvo)
                if "lyrics" in alvo:
                    return {"entries": [{"id": "lyrics-bloqueado", "duration": 200}]}
                return {
                    "entries": [
                        {"id": "bloqueado-1", "duration": 180},
                        {"id": "bloqueado-2", "duration": 210},
                    ]
                }
            raise RuntimeError("HTTP Error 403: Forbidden")

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader, "ACERVO_DIR", str(tmp_path / "acervo")
    ), patch.object(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL):
        with pytest.raises(RuntimeError, match="lyrics-bloqueado"):
            downloader.baixar("artista", "musica")

    assert buscas == [
        "ytsearch5:artista musica official audio",
        "ytsearch5:artista musica lyrics",
    ]
    assert not list(tmp_path.glob("*.part"))


def test_downloader_nao_faz_fallback_para_falha_nao_prevista(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    buscas: list[str] = []

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                buscas.append(alvo)
                return {"entries": [{"id": "erro-generico", "duration": 180}]}
            raise RuntimeError("socket timeout")

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader, "ACERVO_DIR", str(tmp_path / "acervo")
    ), patch.object(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL):
        with pytest.raises(RuntimeError, match="Todos os resultados falharam"):
            downloader.baixar("artista", "musica")

    assert buscas == ["ytsearch5:artista musica official audio"]


def test_downloader_preserva_comportamento_quando_primeiro_resultado_funciona(
    tmp_path: Path,
) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    chamadas: list[tuple[str, bool]] = []

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            chamadas.append((alvo, download))
            if not download:
                return {
                    "entries": [
                        {"id": "primeiro", "duration": 180},
                        {"id": "segundo", "duration": 210},
                    ]
                }
            (tmp_path / "primeiro.webm").write_bytes(b"audio")
            return {"ext": "webm", "title": "Primeiro resultado"}

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL
    ):
        resultado = downloader._baixar_youtube("artista musica official audio")

    assert resultado == str(tmp_path / "primeiro.webm")
    assert chamadas == [
        ("ytsearch5:artista musica official audio", False),
        ("https://www.youtube.com/watch?v=primeiro", True),
    ]


def test_downloader_descarta_candidatos_com_duracao_invalida(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    chamadas: list[str] = []

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                return {
                    "entries": [
                        {"id": "longo", "duration": 901},
                        {"id": "sem-duracao", "duration": None},
                        {"duration": 180},
                        {"id": "valido", "duration": 180},
                    ]
                }
            chamadas.append(alvo)
            (tmp_path / "valido.webm").write_bytes(b"audio")
            return {"ext": "webm", "title": "Resultado válido"}

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL
    ):
        resultado = downloader._baixar_youtube("artista musica official audio")

    assert resultado == str(tmp_path / "valido.webm")
    assert chamadas == ["https://www.youtube.com/watch?v=valido"]


def test_downloader_remove_temp_se_ffmpeg_falha(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    baixado = tmp_path / "video.webm"
    baixado.write_bytes(b"audio")

    with patch.object(downloader, "ACERVO_DIR", str(tmp_path / "acervo")), patch.object(
        downloader, "_baixar_youtube", return_value=str(baixado)
    ), patch.object(
        downloader, "_processar_ffmpeg", side_effect=RuntimeError("ffmpeg falhou")
    ):
        with pytest.raises(RuntimeError, match="ffmpeg falhou"):
            downloader.baixar("artista", "musica")

    assert not baixado.exists()


def test_downloader_remove_temp_se_registro_falha(tmp_path: Path) -> None:
    downloader = _import_downloader_with_fake_dependencies()
    baixado = tmp_path / "video.webm"
    baixado.write_bytes(b"audio")

    with patch.object(downloader, "ACERVO_DIR", str(tmp_path / "acervo")), patch.object(
        downloader, "_baixar_youtube", return_value=str(baixado)
    ), patch.object(
        downloader, "_processar_ffmpeg", side_effect=lambda _entrada, saida: Path(saida).write_bytes(b"mp3")
    ), patch.object(
        downloader.database, "inserir_musica", side_effect=RuntimeError("banco indisponivel")
    ):
        with pytest.raises(RuntimeError, match="banco indisponivel"):
            downloader.baixar("artista", "musica")

    assert not baixado.exists()


def test_downloader_passa_player_client_e_pot_provider_ao_yt_dlp(tmp_path: Path) -> None:
    """Sem estes extractor_args o YouTube recusa a mídia com HTTP 403."""
    downloader = _import_downloader_with_fake_dependencies()
    opcoes_recebidas: dict = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            opcoes_recebidas.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, alvo: str, download: bool):
            if not download:
                return {"entries": [{"id": "disponivel", "duration": 200}]}
            (tmp_path / "disponivel.webm").write_bytes(b"audio")
            return {"ext": "webm", "title": "Resultado disponível"}

    with patch.object(downloader, "TEMP_DIR", str(tmp_path)), patch.object(
        downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL
    ):
        downloader._baixar_youtube("artista musica official audio")

    extractor_args = opcoes_recebidas["extractor_args"]
    assert extractor_args["youtube"]["player_client"] == [downloader.YT_PLAYER_CLIENT]
    assert extractor_args["youtubepot-bgutilhttp"]["base_url"] == [downloader.POT_PROVIDER_URL]
