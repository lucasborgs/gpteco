import unittest
from unittest.mock import AsyncMock

from core.waha_monitor import acao_reconexao, solicitar_reconexao


class WahaMonitorTest(unittest.IsolatedAsyncioTestCase):
    def test_stopped_usa_start(self) -> None:
        self.assertEqual(acao_reconexao("STOPPED"), "start")

    def test_failed_usa_restart(self) -> None:
        self.assertEqual(acao_reconexao("FAILED"), "restart")

    async def test_start_e_enviado_com_post(self) -> None:
        client = AsyncMock()
        client.post.return_value.status_code = 201

        acao, response = await solicitar_reconexao(
            client,
            waha_url="http://waha:3000",
            session="default",
            status="STOPPED",
            headers={"X-Api-Key": "secret"},
        )

        self.assertEqual(acao, "start")
        self.assertEqual(response.status_code, 201)
        client.post.assert_awaited_once_with(
            "http://waha:3000/api/sessions/default/start",
            headers={"X-Api-Key": "secret"},
        )

    async def test_restart_e_enviado_com_post(self) -> None:
        client = AsyncMock()
        client.post.return_value.status_code = 201

        acao, _ = await solicitar_reconexao(
            client,
            waha_url="http://waha:3000",
            session="default",
            status="FAILED",
            headers={},
        )

        self.assertEqual(acao, "restart")
        client.post.assert_awaited_once_with(
            "http://waha:3000/api/sessions/default/restart",
            headers={},
        )


if __name__ == "__main__":
    unittest.main()
