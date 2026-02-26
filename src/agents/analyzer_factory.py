"""Factory for creating language-specific analyzers."""

from typing import Dict, Type
from .base_analyzer import BaseAnalyzer
from .code_analyzer import CodeAnalyzer
from .javascript_analyzer import JavaScriptAnalyzer
from .vue_analyzer import VueAnalyzer
from .language_detector import LanguageDetector

class AnalyzerFactory:
    """Factory class for creating language-specific analyzers."""
    
    # Registry of available analyzers
    _analyzers: Dict[str, Type[BaseAnalyzer]] = {
        'python': CodeAnalyzer,
        'javascript': JavaScriptAnalyzer,
        'typescript': JavaScriptAnalyzer,
        'vue': VueAnalyzer,
        'unknown': CodeAnalyzer      # Default fallback
    }
    
    @classmethod
    def create_analyzer(cls, language: str) -> BaseAnalyzer:
        """Create analyzer instance for the specified language.
        
        Args:
            language: Language name ('python', 'javascript', 'typescript', 'vue')
            
        Returns:
            BaseAnalyzer instance for the specified language
        """
        analyzer_class = cls._analyzers.get(language.lower(), CodeAnalyzer)
        return analyzer_class()
    
    @classmethod
    def register_analyzer(cls, language: str, analyzer_class: Type[BaseAnalyzer]) -> None:
        """Register a new analyzer for a language.
        
        Args:
            language: Language name
            analyzer_class: Analyzer class to register
        """
        cls._analyzers[language.lower()] = analyzer_class
    
    @classmethod
    def get_supported_languages(cls) -> list:
        """Get list of supported languages.
        
        Returns:
            List of supported language names
        """
        return list(cls._analyzers.keys())
    
    @classmethod
    def create_analyzer_for_file(cls, file_path: str, diff_content: str = "") -> BaseAnalyzer:
        """Create analyzer instance based on file extension.
        
        Args:
            file_path: Path to the file
            diff_content: Git diff content for diff-based analysis
            
        Returns:
            BaseAnalyzer instance appropriate for the file
        """
        language = LanguageDetector.detect_language(file_path)
        analyzer = cls.create_analyzer(language)
        
        # VueAnalyzer의 경우 diff_content 전달
        if hasattr(analyzer, 'analyze_code') and 'vue' in file_path.lower():
            # analyzer가 diff_content를 지원하는지 확인
            import inspect
            sig = inspect.signature(analyzer.analyze_code)
            if 'diff_content' in sig.parameters:
                # diff_content를 전달할 수 있도록 래핑
                original_analyze_code = analyzer.analyze_code
                def wrapped_analyze_code(code: str, file_path: str):
                    return original_analyze_code(code, file_path, diff_content)
                analyzer.analyze_code = wrapped_analyze_code
        
        return analyzer
