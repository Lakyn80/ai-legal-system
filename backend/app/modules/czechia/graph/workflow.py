from app.modules.common.graph.builder import (
    StrategyGraphDependencies,
    build_jurisdiction_strategy_graph,
)


def build_czechia_strategy_graph(deps: StrategyGraphDependencies):
    return build_jurisdiction_strategy_graph(deps)
