"""limit_broken_fetcher_adapter 单元测试——Fetcher 协议契约。

设计要点（AGENTS.md §6 / §8.1）：
- fake client 满足 AkshareClientPort 协议
- 验证 adapter.run 内部委托给 fetcher 模块
"""
from __future__ import annotations

from typing import Any

import pytest

from domain.stock.models import LimitStock


class _FakeRepo:
    def __init__(self) -> None:
        self.rows: list[LimitStock] = []

    def upsert_limit_stocks(self, *, trade_date: str, stocks: list[Any]) -> None:
        for s in stocks:
            self.rows = [
                x for x in self.rows
                if not (x.trade_date == s.trade_date and x.stock_code == s.stock_code)
            ]
        self.rows.extend(stocks)

    def select_limit_stocks(self, trade_date: str) -> list[Any]:
        return [x for x in self.rows if x.trade_date == trade_date]

    def upsert_market_index(self, **kw: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    def upsert_emotion_daily(self, **kw: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    def upsert_sector_daily(self, **kw: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    def upsert_board_ladder(self, **kw: Any) -> None:  # pragma: no cover
        raise NotImplementedError


class _FakeClient:
    def __init__(self, stocks: list[LimitStock]) -> None:
        self._stocks = stocks
        self.calls: list[str] = []

    async def get_broken_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        self.calls.append(trade_date)
        return list(self._stocks)


@pytest.mark.asyncio
async def test_adapter_implements_fetcher_protocol() -> None:
    """adapter 必须满足 Fetcher 协议：name + run(trade_date, repo)。"""
    from infrastructure.stock.limit_broken_fetcher_adapter import (
        LimitBrokenFetcherAdapter,
    )

    adapter = LimitBrokenFetcherAdapter(client=_FakeClient(stocks=[]))
    assert adapter.name == "limit_broken_fetcher"
    assert callable(adapter.run)


@pytest.mark.asyncio
async def test_adapter_run_delegates_to_client_and_writes_repo() -> None:
    """adapter.run 调 client.get_broken_limit_stocks 并写 repo。"""
    from infrastructure.stock.limit_broken_fetcher_adapter import (
        LimitBrokenFetcherAdapter,
    )

    fake_stocks = [
        LimitStock(
            trade_date="20260731",
            stock_code="600000",
            stock_name="浦发银行",
            limit_type="broken",
            consecutive_boards=0,
            first_limit_time=None,
            last_limit_time="14:35:21",
            open_count=2,
            is_valid_limit_up=False,
        ),
    ]
    client = _FakeClient(stocks=fake_stocks)
    repo = _FakeRepo()
    adapter = LimitBrokenFetcherAdapter(client=client)

    written = await adapter.run(trade_date="20260731", repo=repo)

    assert written == 1
    assert client.calls == ["20260731"]
    assert len(repo.rows) == 1
    assert repo.rows[0].limit_type == "broken"
    assert repo.rows[0].is_valid_limit_up is False
