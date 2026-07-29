"""Isolated backend used only by the desktop release journey.

It deliberately uses SQLite and a deterministic model, so Playwright never
writes fake users into production Supabase and never depends on a paid model.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kyrozen.api.server import create_app  # noqa: E402
from kyrozen.config import KyrozenConfig  # noqa: E402
from kyrozen.models.base import ModelInterface, ModelResponse  # noqa: E402


class ReleaseJourneyModel(ModelInterface):
    def __init__(self) -> None:
        super().__init__(model="release-journey")

    @property
    def provider_name(self) -> str:
        return "release-journey"

    def chat(self, messages, model=None):  # type: ignore[override]
        return ModelResponse(
            content="我已经理解这个需求。先以单页笔记应用验证记录、保存和按日期筛选这三个核心流程。",
            model="release-journey",
            provider=self.provider_name,
        )


workspace = tempfile.mkdtemp(prefix="kyrozen-release-server-")
config = KyrozenConfig(
    provider="mock",
    api_key="release-test",
    permission_mode="permissive",
    workspace_root=workspace,
    db_backend="sqlite",
    db_path=str(Path(workspace) / "release.db"),
    task_store_path=str(Path(workspace) / "tasks.json"),
    supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", ""),
    supabase_url=os.environ.get("SUPABASE_URL", ""),
    cors_origins=["http://127.0.0.1"],
)
app = create_app(config=config, model=ReleaseJourneyModel())


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
