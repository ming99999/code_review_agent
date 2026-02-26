"""JavaScript/TypeScript/React code analyzer using ESLint."""

import json
import subprocess
import tempfile
import os
import re
from typing import Dict, List, Any, Optional
import logging

from .base_analyzer import BaseAnalyzer, CodeIssue, IssueSeverity, IssueType

logger = logging.getLogger(__name__)


class JavaScriptAnalyzer(BaseAnalyzer):
    """Analyzes JavaScript/TypeScript/React code using ESLint."""
    
    def __init__(self):
        super().__init__()
        self.eslint_config = self._get_eslint_config()
    
    def analyze_code(self, code: str, file_path: str = "") -> Dict[str, Any]:
        """Analyze JavaScript/TypeScript/React code using ESLint.
        
        Args:
            code: JavaScript/TypeScript/React source code
            file_path: Path to the file being analyzed (for extension detection)
            
        Returns:
            Dictionary containing issues, metrics, and summary
        """
        logger.info(f"Analyzing JavaScript code for file: {file_path}")
        logger.info(f"Code length: {len(code)} characters")
        
        self._clear_results()
        
        try:
            # Create temporary file for ESLint analysis in src directory
            with tempfile.NamedTemporaryFile(mode='w', suffix=self._get_file_extension(file_path), delete=False) as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name
            
            try:
                # Run ESLint analysis
                eslint_issues = self._run_eslint_analysis(temp_file_path)
                
                # Convert ESLint issues to CodeIssue objects
                self.issues = self._convert_eslint_issues(eslint_issues, file_path)
                
                # Add React-specific analysis
                react_issues = self._analyze_react_patterns(code, file_path)
                self.issues.extend(react_issues)
                
                # Calculate metrics
                self.metrics = self._calculate_metrics(code)
                
                logger.info(f"JavaScript analysis completed. Found {len(self.issues)} issues")
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"JavaScript analysis error in {file_path}: {e}")
            self.issues.append(CodeIssue(
                type=IssueType.BUG_RISK,
                severity=IssueSeverity.CRITICAL,
                message=f"JavaScript analysis failed: {str(e)}",
                file_path=file_path
            ))
            
        return {
            "issues": self.issues,
            "metrics": self.metrics,
            "summary": self._generate_summary()
        }
    
    def _get_file_extension(self, file_path: str) -> str:
        """Get appropriate file extension for temporary file.
        
        Args:
            file_path: Original file path
            
        Returns:
            File extension (.js, .jsx, .ts, .tsx)
        """
        if file_path.endswith('.tsx'):
            return '.tsx'
        elif file_path.endswith('.ts'):
            return '.ts'
        elif file_path.endswith('.jsx'):
            return '.jsx'
        else:
            return '.js'
    
    def _run_eslint_analysis(self, file_path: str) -> List[Dict[str, Any]]:
        """Run ESLint analysis on the file.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            List of ESLint issues
        """
        try:
            # Debug: Print the temporary file content
            with open(file_path, 'r') as f:
                content = f.read()
                print(f"DEBUG: Temporary file content:\n{content}")
                logger.info(f"Temporary file content:\n{content}")
            
            # Debug: Check if file exists
            import os
            print(f"DEBUG: Temporary file exists: {os.path.exists(file_path)}")
            print(f"DEBUG: Temporary file path: {file_path}")
            
            # ESLint command with JSON output format
            cmd = [
                'npx', 'eslint',
                file_path,
                '--config', 'eslint.config.js',
                '--format', 'json',
                '--no-error-on-unmatched-pattern',
                '--no-ignore',
                '--no-warn-ignored'
            ]
            
            print(f"DEBUG: Running ESLint command: {' '.join(cmd)}")
            
            # Run ESLint with current working directory set to project root
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            print(f"DEBUG: ESLint return code: {result.returncode}")
            print(f"DEBUG: ESLint stdout: {result.stdout}")
            print(f"DEBUG: ESLint stderr: {result.stderr}")
            
            if result.returncode > 1:
                logger.error(f"ESLint execution failed: {result.stderr}")
                return []
            
            # Parse ESLint output
            if result.stdout.strip():
                eslint_output = json.loads(result.stdout)
                if isinstance(eslint_output, list) and len(eslint_output) > 0:
                    return eslint_output[0].get('messages', [])
            
            return []
            
        except subprocess.TimeoutExpired:
            logger.error("ESLint analysis timed out")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ESLint output: {e}")
            return []
        except Exception as e:
            logger.error(f"ESLint analysis failed: {e}")
            return []
    
    def _convert_eslint_issues(self, eslint_issues: List[Dict[str, Any]], file_path: str) -> List[CodeIssue]:
        """Convert ESLint issues to CodeIssue objects.
        
        Args:
            eslint_issues: List of ESLint issues
            file_path: Original file path
            
        Returns:
            List of CodeIssue objects
        """
        issues = []
        
        for eslint_issue in eslint_issues:
            # Map ESLint severity to our severity levels
            eslint_severity = eslint_issue.get('severity', 0)
            if eslint_severity == 2:  # ESLint error
                severity = IssueSeverity.HIGH
            elif eslint_severity == 1:  # ESLint warning
                severity = IssueSeverity.MEDIUM
            else:
                severity = IssueSeverity.LOW
            
            # Map ESLint rule ID to issue type
            rule_id = eslint_issue.get('ruleId', '')
            issue_type = self._map_rule_to_type(rule_id)
            
            # Create CodeIssue
            issue = CodeIssue(
                type=issue_type,
                severity=severity,
                message=eslint_issue.get('message', ''),
                line_number=eslint_issue.get('line'),
                column_number=eslint_issue.get('column'),
                end_line=eslint_issue.get('endLine'),
                end_column=eslint_issue.get('endColumn'),
                file_path=file_path,
                rule_reference=f"ESLint Rule: {rule_id}" if rule_id else None
            )
            
            issues.append(issue)
        
        return issues
    
    def _map_rule_to_type(self, rule_id: str) -> IssueType:
        """Map ESLint rule ID to IssueType.
        
        Args:
            rule_id: ESLint rule ID
            
        Returns:
            Corresponding IssueType
        """
        # Handle None or empty rule_id
        if not rule_id:
            return IssueType.STYLE
            
        # React specific rules
        if rule_id.startswith('react/'):
            if 'hook' in rule_id.lower():
                return IssueType.REACT_HOOKS
            elif 'jsx' in rule_id.lower():
                return IssueType.JSX_STRUCTURE
            else:
                return IssueType.MAINTAINABILITY
        
        # General JavaScript rules
        if rule_id.startswith('no-'):
            return IssueType.BUG_RISK
        elif rule_id.startswith('prefer-'):
            return IssueType.STYLE
        elif 'complexity' in rule_id:
            return IssueType.COMPLEXITY
        elif 'security' in rule_id.lower():
            return IssueType.SECURITY
        else:
            return IssueType.STYLE
    
    def _calculate_metrics(self, code: str) -> Dict[str, Any]:
        """Calculate JavaScript code metrics.
        
        Args:
            code: JavaScript source code
            
        Returns:
            Dictionary of metrics
        """
        lines = code.split('\n')
        
        return {
            "total_lines": len(lines),
            "non_empty_lines": len([l for l in lines if l.strip()]),
            "comment_lines": len([l for l in lines if '//' in l or '/*' in l]),
            "function_count": code.count('function ') + code.count('=>'),
            "class_count": code.count('class '),
            "import_count": code.count('import ') + code.count('require(')
        }
    
    def _get_eslint_config(self) -> Dict[str, Any]:
        """Get ESLint configuration.
        
        Returns:
            ESLint configuration dictionary
        """
        return {
            "extends": [
                "eslint:recommended",
                "plugin:react/recommended",
                "plugin:react-hooks/recommended"
            ],
            "plugins": ["react", "react-hooks"],
            "parserOptions": {
                "ecmaVersion": 2021,
                "sourceType": "module",
                "ecmaFeatures": {
                    "jsx": True
                }
            },
            "settings": {
                "react": {
                    "version": "detect"
                }
            },
            "rules": {
                # React specific rules
                "react/prop-types": "warn",
                "react/react-in-jsx-scope": "off",  # Not needed for React 17+
                "react-hooks/rules-of-hooks": "error",
                "react-hooks/exhaustive-deps": "warn",
                
                # General JavaScript rules
                "no-unused-vars": "warn",
                "no-undef": "error",
                "no-console": "warn",
                "prefer-const": "warn",
                "no-var": "error"
            }
        }
    
    def _analyze_react_patterns(self, code: str, file_path: str) -> List[CodeIssue]:
        """Analyze React-specific patterns and anti-patterns.
        
        Args:
            code: JavaScript/React source code
            file_path: Path to the file being analyzed
            
        Returns:
            List of React-specific CodeIssue objects
        """
        issues = []
        
        # Check React Hook rules
        hook_issues = self._check_hook_rules(code, file_path)
        issues.extend(hook_issues)
        
        # Check JSX structure and patterns
        jsx_issues = self._check_jsx_patterns(code, file_path)
        issues.extend(jsx_issues)
        
        # Check component structure
        component_issues = self._check_component_patterns(code, file_path)
        issues.extend(component_issues)
        
        return issues
    
    def _check_hook_rules(self, code: str, file_path: str) -> List[CodeIssue]:
        """Check React Hook rules and best practices.
        
        Args:
            code: JavaScript/React source code
            file_path: Path to the file being analyzed
            
        Returns:
            List of Hook-related CodeIssue objects
        """
        issues = []
        
        # Check for useEffect dependencies
        useEffect_matches = re.finditer(r'useEffect\s*\(\s*\([^)]*\)\s*=>\s*{[^}]*}\s*,?\s*([^)]*)\s*\)', code)
        for match in useEffect_matches:
            deps = match.group(1).strip()
            line_number = code[:match.start()].count('\n') + 1
            
            # Check for missing dependencies
            if deps == '' or deps == '[]':
                # Check if there are variables used inside useEffect that should be dependencies
                effect_body = match.group(0)
                if 'useState' in effect_body or 'useRef' in effect_body or re.search(r'\b\w+\.\w+', effect_body):
                    issues.append(CodeIssue(
                        type=IssueType.REACT_HOOKS,
                        severity=IssueSeverity.MEDIUM,
                        message="useEffect has missing dependencies. Add dependencies or explicitly use empty array []",
                        line_number=line_number,
                        file_path=file_path,
                        suggestion="Add missing dependencies to the dependency array or use [] if no dependencies",
                        code_example="""
// ❌ Bad - Missing dependencies
useEffect(() => {
  console.log(count); // 'count' should be in dependencies
}, []);

// ✅ Good - With dependencies
useEffect(() => {
  console.log(count);
}, [count]);

// ✅ Good - Explicitly empty
useEffect(() => {
  console.log('This runs only once');
}, []);
"""
                    ))
        
        # Check for conditional hooks
        conditional_hook_patterns = [
            r'if\s*\([^)]*\)\s*{[^}]*\b(use\w+)\s*\(',
            r'for\s*\([^)]*\)\s*{[^}]*\b(use\w+)\s*\(',
            r'while\s*\([^)]*\)\s*{[^}]*\b(use\w+)\s*\(',
        ]
        
        for pattern in conditional_hook_patterns:
            matches = re.finditer(pattern, code, re.DOTALL)
            for match in matches:
                hook_name = match.group(1)
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    type=IssueType.REACT_HOOKS,
                    severity=IssueSeverity.HIGH,
                    message=f"React Hook '{hook_name}' is called conditionally. Hooks must be called in the exact same order in every component render.",
                    line_number=line_number,
                    file_path=file_path,
                    suggestion="Move the hook call outside of the condition or restructure the component logic",
                    rule_reference="React Hooks Rules: https://reactjs.org/docs/hooks-rules.html",
                    code_example="""
// ❌ Bad - Conditional hook
if (condition) {
  const [state, setState] = useState(initialValue);
}

// ✅ Good - Always call hooks
const [state, setState] = useState(condition ? initialValue : null);
"""
                ))
        
        return issues
    
    def _check_jsx_patterns(self, code: str, file_path: str) -> List[CodeIssue]:
        """Check JSX structure and patterns.
        
        Args:
            code: JavaScript/React source code
            file_path: Path to the file being analyzed
            
        Returns:
            List of JSX-related CodeIssue objects
        """
        issues = []
        
        # Check for inline styles that could be CSS classes
        inline_style_matches = re.finditer(r'style\s*=\s*{[^}]+}', code)
        for match in inline_style_matches:
            line_number = code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                type=IssueType.JSX_STRUCTURE,
                severity=IssueSeverity.LOW,
                message="Consider using CSS classes instead of inline styles for better maintainability",
                line_number=line_number,
                file_path=file_path,
                suggestion="Move styles to CSS classes or use styled-components/emotion",
                code_example="""
// ❌ Bad - Inline styles
<div style={{ color: 'red', fontSize: '16px' }}>Content</div>

// ✅ Good - CSS classes
<div className="content-style">Content</div>

// ✅ Good - CSS modules
<div className={styles.content}>Content</div>
"""
            ))
        
        # Check for deeply nested JSX (more than 3 levels)
        jsx_nesting_matches = re.finditer(r'(<\w+[^>]*>){4,}', code)
        for match in jsx_nesting_matches:
            line_number = code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                type=IssueType.JSX_STRUCTURE,
                severity=IssueSeverity.MEDIUM,
                message="Deeply nested JSX structure. Consider breaking into smaller components",
                line_number=line_number,
                file_path=file_path,
                suggestion="Extract nested JSX into separate components for better readability",
                code_example="""
// ❌ Bad - Deeply nested
<div>
  <div>
    <div>
      <div>
        <span>Deep content</span>
      </div>
    </div>
  </div>
</div>

// ✅ Good - Component extraction
const DeepComponent = () => <span>Deep content</span>;
const NestedComponent = () => <div><DeepComponent /></div>;
"""
            ))
        
        return issues
    
    def _check_component_patterns(self, code: str, file_path: str) -> List[CodeIssue]:
        """Check React component patterns and best practices.
        
        Args:
            code: JavaScript/React source code
            file_path: Path to the file being analyzed
            
        Returns:
            List of component-related CodeIssue objects
        """
        issues = []
        
        # Check for large components (more than 300 lines)
        lines = code.split('\n')
        if len(lines) > 300:
            # Find component definitions
            component_matches = re.finditer(r'(function\s+\w+Component|const\s+\w+Component\s*=\s*\([^)]*\)\s*=>|class\s+\w+Component)', code)
            for match in component_matches:
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    type=IssueType.MAINTAINABILITY,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Large component detected ({len(lines)} lines). Consider splitting into smaller components",
                    line_number=line_number,
                    file_path=file_path,
                    suggestion="Break this component into smaller, focused components",
                    code_example="""
// ❌ Bad - Large component
function LargeComponent() {
  // 300+ lines of code
}

// ✅ Good - Split into smaller components
function Header() { /* ... */ }
function Content() { /* ... */ }
function Footer() { /* ... */ }

function MainComponent() {
  return (
    <div>
      <Header />
      <Content />
      <Footer />
    </div>
  );
}
"""
                ))
        
        # Check for multiple useState calls that could be consolidated
        useState_count = len(re.findall(r'useState\s*\(', code))
        if useState_count > 5:
            issues.append(CodeIssue(
                type=IssueType.MAINTAINABILITY,
                severity=IssueSeverity.LOW,
                message=f"Multiple useState calls ({useState_count} found). Consider using useReducer for complex state logic",
                line_number=1,  # Hard to determine exact line, use file start
                file_path=file_path,
                suggestion="Consider using useReducer or custom hooks for complex state management",
                code_example="""
// ❌ Bad - Many useState calls
const [name, setName] = useState('');
const [age, setAge] = useState(0);
const [email, setEmail] = useState('');
const [phone, setPhone] = useState('');
const [address, setAddress] = useState('');

// ✅ Good - useReducer for related state
const [state, dispatch] = useReducer(userReducer, initialState);

// ✅ Good - Custom hook
const userState = useUserState();
"""
            ))
        
        return issues
