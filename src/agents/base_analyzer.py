"""Base analyzer interface for multi-language code analysis."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueType(Enum):
    """Types of code issues."""
    STYLE = "style"
    PERFORMANCE = "performance"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    BUG_RISK = "bug_risk"
    COMPLEXITY = "complexity"
    BEST_PRACTICES = "best_practices"
    TOOL_ISSUE = "tool_issue"
    SYNTAX_ERROR = "syntax_error"
    # JavaScript/React/Vue specific types
    REACT_HOOKS = "react_hooks"
    JSX_STRUCTURE = "jsx_structure"
    STATE_MANAGEMENT = "state_management"
    ACCESSIBILITY = "accessibility"
    VUE_COMPONENT_STRUCTURE = "vue_component_structure"
    VUE_TEMPLATE_SYNTAX = "vue_template_syntax"
    VUE_LIFECYCLE = "vue_lifecycle"


@dataclass
class CodeIssue:
    """Represents a code issue or suggestion."""
    type: IssueType
    severity: IssueSeverity
    message: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    file_path: Optional[str] = None
    suggestion: Optional[str] = None
    code_example: Optional[str] = None
    rule_reference: Optional[str] = None


class BaseAnalyzer(ABC):
    """Abstract base class for code analyzers."""
    
    def __init__(self):
        self.issues: List[CodeIssue] = []
        self.metrics: Dict[str, Any] = {}
    
    @abstractmethod
    def analyze_code(self, code: str, file_path: str = "") -> Dict[str, Any]:
        """Analyze code and return issues, metrics, and summary.
        
        Args:
            code: Source code content
            file_path: Path to the file being analyzed
            
        Returns:
            Dictionary containing:
                - issues: List of CodeIssue objects
                - metrics: Code metrics dictionary
                - summary: Analysis summary
        """
        pass
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate analysis summary from collected issues."""
        severity_counts = {}
        type_counts = {}
        
        for issue in self.issues:
            severity_counts[issue.severity.value] = severity_counts.get(issue.severity.value, 0) + 1
            type_counts[issue.type.value] = type_counts.get(issue.type.value, 0) + 1
            
        return {
            "total_issues": len(self.issues),
            "severity_distribution": severity_counts,
            "type_distribution": type_counts,
            "critical_issues": len([i for i in self.issues if i.severity == IssueSeverity.CRITICAL]),
            "high_issues": len([i for i in self.issues if i.severity == IssueSeverity.HIGH])
        }
    
    def _clear_results(self):
        """Clear previous analysis results."""
        self.issues.clear()
        self.metrics = {}
