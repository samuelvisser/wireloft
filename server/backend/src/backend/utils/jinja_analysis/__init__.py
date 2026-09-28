"""Reusable, side-effect-free Jinja dependency and conditional-output analysis."""
from .custom_indexes import (
    CustomIndexReachabilityComparison,
    CustomIndexReachabilityStatus,
    CustomIndexUsage,
    CustomIndexUsageAnalysis,
    analyze_custom_index_usage,
    compare_custom_index_reachability,
)
from .expressions import expression_dependencies
from .paths import OutputVariant, TemplateAnalysis, UnknownOutput, analyze_template

__all__ = [
    "CustomIndexReachabilityComparison",
    "CustomIndexReachabilityStatus",
    "CustomIndexUsage",
    "CustomIndexUsageAnalysis",
    "analyze_custom_index_usage",
    "compare_custom_index_reachability",
    "expression_dependencies",
    "OutputVariant",
    "TemplateAnalysis",
    "UnknownOutput",
    "analyze_template",
]
