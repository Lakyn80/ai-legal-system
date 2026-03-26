from fastapi import APIRouter, Depends

from app.core.dependencies import get_strategy_engine
from app.modules.common.graph.schemas import StrategyRequest, StrategyResponse
from app.modules.common.graph.strategy_engine import StrategyEngine


router = APIRouter()


@router.post("/generate", response_model=StrategyResponse)
def generate_strategy(
    request: StrategyRequest,
    strategy_engine: StrategyEngine = Depends(get_strategy_engine),
):
    return strategy_engine.generate(request)
