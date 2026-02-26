"""Code analysis module for identifying issues and improvements."""

import ast
import re
from typing import Dict, List, Any, Optional, Tuple
import logging

from .base_analyzer import BaseAnalyzer, CodeIssue, IssueSeverity, IssueType

logger = logging.getLogger(__name__)


class CodeAnalyzer(BaseAnalyzer):
    """Analyzes Python code for various issues and improvements."""
    
    def __init__(self):
        super().__init__()
    
    def analyze_code(self, code: str, file_path: str = "") -> Dict[str, Any]:
        """Comprehensive code analysis."""
        logger.info(f"Analyzing code for file: {file_path}")
        logger.info(f"Code length: {len(code)} characters")
        logger.info(f"Code preview (first 100 chars): {repr(code[:100])}")
        
        self.issues.clear()
        self.metrics = {}
        
        try:
            tree = ast.parse(code)
            self._analyze_ast(tree, file_path)
            self._analyze_raw_code(code, file_path)
            self._calculate_metrics(code, tree)
            
            logger.info(f"Analysis completed. Found {len(self.issues)} issues")
            logger.info(f"Metrics: {self.metrics}")
            
        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {str(e)}")
            self.issues.append(CodeIssue(
                type=IssueType.BUG_RISK,
                severity=IssueSeverity.CRITICAL,
                message=f"Syntax error: {str(e)}",
                file_path=file_path
            ))
        except Exception as e:
            logger.error(f"Analysis error in {file_path}: {e}")
            logger.error(f"Code that caused error: {repr(code[:200])}")
            
        return {
            "issues": self.issues,
            "metrics": self.metrics,
            "summary": self._generate_summary()
        }
    
    def _analyze_ast(self, tree: ast.AST, file_path: str) -> None:
        """Analyze AST for code issues."""
        self._check_naming_conventions(tree, file_path)
        self._check_complexity(tree, file_path)
        self._check_docstrings(tree, file_path)
        self._check_imports(tree, file_path)
        self._check_functions(tree, file_path)
        self._check_classes(tree, file_path)
    
    def _analyze_raw_code(self, code: str, file_path: str) -> None:
        """Analyze raw code for style issues."""
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            self._check_line_length(line, i, file_path)
            self._check_trailing_whitespace(line, i, file_path)
            self._check_tabs_vs_spaces(line, i, file_path)
    
    def _check_naming_conventions(self, tree: ast.AST, file_path: str) -> None:
        """Check Python naming conventions."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not self._is_snake_case(node.name):
                    self.issues.append(CodeIssue(
                        type=IssueType.STYLE,
                        severity=IssueSeverity.LOW,
                        message=f"Function name '{node.name}' should use snake_case",
                        line_number=node.lineno,
                        file_path=file_path,
                        suggestion="Use snake_case for function names",
                        rule_reference="PEP 8: Function and Variable Names"
                    ))
            elif isinstance(node, ast.ClassDef):
                if not self._is_pascal_case(node.name):
                    self.issues.append(CodeIssue(
                        type=IssueType.STYLE,
                        severity=IssueSeverity.LOW,
                        message=f"Class name '{node.name}' should use PascalCase",
                        line_number=node.lineno,
                        file_path=file_path,
                        suggestion="Use PascalCase for class names",
                        rule_reference="PEP 8: Class Names"
                    ))
    
    def _check_complexity(self, tree: ast.AST, file_path: str) -> None:
        """Check code complexity."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = self._calculate_cyclomatic_complexity(node)
                if complexity > 10:
                    self.issues.append(CodeIssue(
                        type=IssueType.COMPLEXITY,
                        severity=IssueSeverity.MEDIUM,
                        message=f"Function '{node.name}' has high cyclomatic complexity ({complexity})",
                        line_number=node.lineno,
                        file_path=file_path,
                        suggestion="Consider breaking down into smaller functions",
                        code_example="""
# Instead of one complex function:
def process_data(data):
    if condition1:
        if condition2:
            if condition3:
                # many nested conditions
                pass

# Break into smaller functions:
def validate_data(data):
    return condition1 and condition2 and condition3

def process_valid_data(data):
    # processing logic
    pass

def process_data(data):
    if validate_data(data):
        process_valid_data(data)
"""
                    ))
    
    def _check_docstrings(self, tree: ast.AST, file_path: str) -> None:
        """Check for missing docstrings."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                if not ast.get_docstring(node):
                    if isinstance(node, ast.FunctionDef):
                        message = f"Function '{node.name}' is missing a docstring"
                        line_no = node.lineno
                    elif isinstance(node, ast.ClassDef):
                        message = f"Class '{node.name}' is missing a docstring"
                        line_no = node.lineno
                    else:  # Module
                        message = "Module is missing a module-level docstring"
                        line_no = 1
                    
                    self.issues.append(CodeIssue(
                        type=IssueType.MAINTAINABILITY,
                        severity=IssueSeverity.MEDIUM,
                        message=message,
                        line_number=line_no,
                        file_path=file_path,
                        suggestion="Add descriptive docstrings",
                        code_example='''
def my_function(param1: str, param2: int) -> bool:
    """Brief description of the function.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When invalid input is provided
    """
    # function implementation
    pass
''',
                        rule_reference="PEP 257: Docstring Conventions"
                    ))
    
    def _check_imports(self, tree: ast.AST, file_path: str) -> None:
        """Check import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        # Check for unused imports (basic check)
        if len(imports) > 15:
            self.issues.append(CodeIssue(
                type=IssueType.MAINTAINABILITY,
                severity=IssueSeverity.LOW,
                message="Large number of imports - consider organizing imports",
                file_path=file_path,
                suggestion="Group imports: standard library, third-party, local",
                code_example="""
# Standard library imports
import os
import sys
from typing import List, Dict

# Third-party imports
import numpy as np
import pandas as pd

# Local imports
from mymodule import myfunction
from .utils import helper
"""
            ))
    
    def _check_functions(self, tree: ast.AST, file_path: str) -> None:
        """Check function definitions."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check function length
                func_length = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 50
                if func_length > 50:
                    self.issues.append(CodeIssue(
                        type=IssueType.MAINTAINABILITY,
                        severity=IssueSeverity.MEDIUM,
                        message=f"Function '{node.name}' is very long ({func_length} lines)",
                        line_number=node.lineno,
                        file_path=file_path,
                        suggestion="Break long functions into smaller, focused functions",
                        code_example="""
# Instead of one long function:
def process_everything():
    # 100+ lines of code
    pass

# Break into smaller functions:
def validate_input(data):
    # validation logic
    pass

def process_step1(data):
    # step 1 logic
    pass

def process_step2(data):
    # step 2 logic
    pass

def process_everything(data):
    validate_input(data)
    process_step1(data)
    process_step2(data)
"""
                    ))
    
    def _check_classes(self, tree: ast.AST, file_path: str) -> None:
        """Check class definitions."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check for too many methods
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if len(methods) > 20:
                    self.issues.append(CodeIssue(
                        type=IssueType.MAINTAINABILITY,
                        severity=IssueSeverity.MEDIUM,
                        message=f"Class '{node.name}' has many methods ({len(methods)})",
                        line_number=node.lineno,
                        file_path=file_path,
                        suggestion="Consider splitting into multiple classes or using composition"
                    ))
    
    def _check_line_length(self, line: str, line_num: int, file_path: str) -> None:
        """Check line length (PEP 8: 79 characters)."""
        if len(line) > 79:
            self.issues.append(CodeIssue(
                type=IssueType.STYLE,
                severity=IssueSeverity.LOW,
                message=f"Line exceeds 79 characters ({len(line)})",
                line_number=line_num,
                file_path=file_path,
                suggestion="Break long lines for better readability",
                rule_reference="PEP 8: Maximum Line Length"
            ))
    
    def _check_trailing_whitespace(self, line: str, line_num: int, file_path: str) -> None:
        """Check for trailing whitespace."""
        if line.endswith(' ') or line.endswith('\t'):
            self.issues.append(CodeIssue(
                type=IssueType.STYLE,
                severity=IssueSeverity.LOW,
                message="Trailing whitespace detected",
                line_number=line_num,
                file_path=file_path,
                suggestion="Remove trailing whitespace"
            ))
    
    def _check_tabs_vs_spaces(self, line: str, line_num: int, file_path: str) -> None:
        """Check for mixed tabs and spaces."""
        if '\t' in line and '    ' in line:
            self.issues.append(CodeIssue(
                type=IssueType.STYLE,
                severity=IssueSeverity.MEDIUM,
                message="Mixed tabs and spaces for indentation",
                line_number=line_num,
                file_path=file_path,
                suggestion="Use spaces for indentation (PEP 8)",
                rule_reference="PEP 8: Tabs or Spaces?"
            ))
    
    def _is_snake_case(self, name: str) -> bool:
        """Check if name is snake_case."""
        return name.islower() and '_' in name and not name.startswith('_')
    
    def _is_pascal_case(self, name: str) -> bool:
        """Check if name is PascalCase."""
        return name[0].isupper() and '_' not in name
    
    def _calculate_cyclomatic_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity for a function."""
        complexity = 1
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
                
        return complexity
    
    def _calculate_metrics(self, code: str, tree: ast.AST) -> None:
        """Calculate code metrics."""
        lines = code.split('\n')
        
        self.metrics = {
            "total_lines": len(lines),
            "non_empty_lines": len([l for l in lines if l.strip()]),
            "comment_lines": len([l for l in lines if l.strip().startswith('#')]),
            "function_count": len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]),
            "class_count": len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]),
            "import_count": len([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))])
        }
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate analysis summary."""
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
