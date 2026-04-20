"""因子注册表 - 统一管理所有预测因子"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum


class FactorCategory(Enum):
    """因子类别枚举"""
    SEAL_QUALITY = "seal_quality"           # 涨停质量因子
    CAPITAL_BEHAVIOR = "capital_behavior"   # 资金行为因子
    MARKET_ENVIRONMENT = "market_env"       # 市场环境因子
    TECHNICAL = "technical"                  # 技术形态因子
    HISTORICAL = "historical"               # 历史规律因子
    ORDER_BOOK = "order_book"               # 盘口数据因子
    NORTHBOUND = "northbound"               # 北向资金因子


@dataclass
class FactorDefinition:
    """因子定义"""
    name: str                              # 因子名称 (唯一标识)
    display_name: str                       # 显示名称
    category: FactorCategory                # 所属类别
    weight: float                           # 权重 (0-1)
    description: str = ""                   # 因子描述
    higher_is_better: bool = True           # True=越高越好, False=越低越好
    default_score: float = 50.0             # 数据缺失时的默认分


class FactorRegistry:
    """因子注册表管理器 - 单例模式"""

    _instance = None
    _factors: Dict[str, FactorDefinition] = {}
    _categories: Dict[FactorCategory, List[str]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_default_factors()
        return cls._instance

    def _initialize_default_factors(self):
        """初始化默认因子定义"""
        # ========== 涨停质量因子 (4个) ==========
        self.register(FactorDefinition(
            name="seal_time_score",
            display_name="涨停时间",
            category=FactorCategory.SEAL_QUALITY,
            weight=0.08,
            description="越早涨停越好，开盘即涨停最强"
        ))
        self.register(FactorDefinition(
            name="seal_pattern_score",
            display_name="涨停形态",
            category=FactorCategory.SEAL_QUALITY,
            weight=0.05,
            description="一字板最强(筹码稳定)，T字板次之，实体板最弱"
        ))
        self.register(FactorDefinition(
            name="seal_strength_score",
            display_name="封单强度",
            category=FactorCategory.SEAL_QUALITY,
            weight=0.10,
            description="封单金额/流通市值比，越高封板越稳"
        ))
        self.register(FactorDefinition(
            name="late_seal_score",
            display_name="封板及时性",
            category=FactorCategory.SEAL_QUALITY,
            weight=0.07,
            description="越早封板越好，尾盘封板风险大"
        ))

        # ========== 资金行为因子 (4个) ==========
        self.register(FactorDefinition(
            name="super_large_ratio_score",
            display_name="超大单占比",
            category=FactorCategory.CAPITAL_BEHAVIOR,
            weight=0.10,
            description="超大单净流入占比，机构/大资金参与度"
        ))
        self.register(FactorDefinition(
            name="consecutive_inflow_score",
            display_name="资金连续净买入",
            category=FactorCategory.CAPITAL_BEHAVIOR,
            weight=0.08,
            description="连续净买入天数越多越好"
        ))
        self.register(FactorDefinition(
            name="small_ratio_score",
            display_name="散户资金占比",
            category=FactorCategory.CAPITAL_BEHAVIOR,
            weight=0.05,
            higher_is_better=False,
            description="散户占比越低越好(反向指标)"
        ))
        self.register(FactorDefinition(
            name="main_force_ratio_score",
            display_name="主力资金占比",
            category=FactorCategory.CAPITAL_BEHAVIOR,
            weight=0.07,
            description="主力资金净流入占比"
        ))

        # ========== 市场环境因子 (4个) ==========
        self.register(FactorDefinition(
            name="market_zt_ratio_score",
            display_name="市场涨跌停比",
            category=FactorCategory.MARKET_ENVIRONMENT,
            weight=0.06,
            description="涨停家数/跌停家数，比值越高市场越强"
        ))
        self.register(FactorDefinition(
            name="sector_team_score",
            display_name="板块梯队完整性",
            category=FactorCategory.MARKET_ENVIRONMENT,
            weight=0.07,
            description="同板块涨停股数量，越多板块效应越强"
        ))
        self.register(FactorDefinition(
            name="leader_link_score",
            display_name="龙头股联动",
            category=FactorCategory.MARKET_ENVIRONMENT,
            weight=0.05,
            description="板块龙头是否也涨停，龙头强则跟风强"
        ))
        self.register(FactorDefinition(
            name="relative_strength_score",
            display_name="相对大盘强弱",
            category=FactorCategory.MARKET_ENVIRONMENT,
            weight=0.08,
            description="个股涨幅vs大盘涨幅，跑赢指数越好"
        ))

        # ========== 技术形态因子 (6个) ==========
        self.register(FactorDefinition(
            name="volume_price_momentum_score",
            display_name="量价齐升",
            category=FactorCategory.TECHNICAL,
            weight=0.06,
            description="量比>1.5且价格上涨，量价配合好"
        ))
        self.register(FactorDefinition(
            name="ma_bull_score",
            display_name="均线多头排列",
            category=FactorCategory.TECHNICAL,
            weight=0.05,
            description="MA5>MA10>MA20多头排列"
        ))
        self.register(FactorDefinition(
            name="rsi_score",
            display_name="RSI状态",
            category=FactorCategory.TECHNICAL,
            weight=0.04,
            description="RSI(6)在40-60区间最佳，既不超买也不超卖"
        ))
        self.register(FactorDefinition(
            name="breakout_score",
            display_name="突破前高",
            category=FactorCategory.TECHNICAL,
            weight=0.05,
            description="突破20日高点，趋势加速"
        ))
        self.register(FactorDefinition(
            name="boll_position_score",
            display_name="布林带位置",
            category=FactorCategory.TECHNICAL,
            weight=0.04,
            description="价格在中轨上方为强，布林带开口扩张更好"
        ))
        self.register(FactorDefinition(
            name="macd_signal_score",
            display_name="MACD信号",
            category=FactorCategory.TECHNICAL,
            weight=0.05,
            description="MACD金叉且在零轴上方最强"
        ))

        # ========== 历史规律因子 (3个) ==========
        self.register(FactorDefinition(
            name="hist_zt_count_score",
            display_name="历史涨停次数",
            category=FactorCategory.HISTORICAL,
            weight=0.05,
            description="历史涨停次数越多，股性越活"
        ))
        self.register(FactorDefinition(
            name="hist_premium_score",
            display_name="历史次溢价率",
            category=FactorCategory.HISTORICAL,
            weight=0.07,
            description="历史涨停次日平均涨幅，正溢价越多越好"
        ))
        self.register(FactorDefinition(
            name="volatility_score",
            display_name="股性评分",
            category=FactorCategory.HISTORICAL,
            weight=0.04,
            description="基于历史波动率的股性评估"
        ))

        # ========== 盘口数据因子 (3个) ==========
        self.register(FactorDefinition(
            name="committee_ratio_score",
            display_name="委比",
            category=FactorCategory.ORDER_BOOK,
            weight=0.04,
            description="委比正值越大，买盘力量越强"
        ))
        self.register(FactorDefinition(
            name="outin_ratio_score",
            display_name="内外盘比",
            category=FactorCategory.ORDER_BOOK,
            weight=0.05,
            description="外盘/内盘比值，越大主动买盘越强"
        ))
        self.register(FactorDefinition(
            name="tail_momentum_score",
            display_name="尾盘动量",
            category=FactorCategory.ORDER_BOOK,
            weight=0.06,
            description="尾盘成交量占比，尾盘放量上涨为强"
        ))

        # ========== 北向资金因子 (3个) ==========
        self.register(FactorDefinition(
            name="northbound_netbuy_score",
            display_name="北向净买入",
            category=FactorCategory.NORTHBOUND,
            weight=0.06,
            description="北向资金净买入金额，外资看多"
        ))
        self.register(FactorDefinition(
            name="northbound_consecutive_score",
            display_name="北向持续买入",
            category=FactorCategory.NORTHBOUND,
            weight=0.04,
            description="北向连续净买入天数"
        ))
        self.register(FactorDefinition(
            name="northbound_hold_change_score",
            display_name="北向持仓变化",
            category=FactorCategory.NORTHBOUND,
            weight=0.03,
            description="北向持仓占比变化"
        ))

    def register(self, factor: FactorDefinition) -> None:
        """注册因子"""
        self._factors[factor.name] = factor
        if factor.category not in self._categories:
            self._categories[factor.category] = []
        if factor.name not in self._categories[factor.category]:
            self._categories[factor.category].append(factor.name)

    def get_factor(self, name: str) -> Optional[FactorDefinition]:
        """获取单个因子定义"""
        return self._factors.get(name)

    def get_factors_by_category(self, category: FactorCategory) -> List[FactorDefinition]:
        """获取指定类别的所有因子"""
        names = self._categories.get(category, [])
        return [self._factors[n] for n in names if n in self._factors]

    def get_all_factors(self) -> List[FactorDefinition]:
        """获取所有因子定义"""
        return list(self._factors.values())

    def get_category_weights(self) -> Dict[FactorCategory, float]:
        """获取各类别权重"""
        weights = {}
        for cat in FactorCategory:
            factors = self.get_factors_by_category(cat)
            weights[cat] = sum(f.weight for f in factors)
        return weights

    def get_weights(self) -> Dict[str, float]:
        """获取所有因子权重"""
        return {f.name: f.weight for f in self._factors.values()}

    def get_factor_names(self) -> List[str]:
        """获取所有因子名称"""
        return list(self._factors.keys())


# 全局因子注册表实例
_registry = FactorRegistry()


def get_factor_registry() -> FactorRegistry:
    """获取全局因子注册表"""
    return _registry
