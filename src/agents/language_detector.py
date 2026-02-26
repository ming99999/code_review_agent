"""Language detection for multi-language code analysis."""

from typing import Dict, Set, Optional
import os


class LanguageDetector:
    """Language detection utility for code files."""
    
    # Supported languages and their file extensions
    SUPPORTED_LANGUAGES = {
        'python': {'.py'},
        'javascript': {'.js', '.jsx'},
        'typescript': {'.ts', '.tsx'},
        'vue': {'.vue'},  # Vue.js single file components
        'unknown': set()  # For unknown file types
    }
    
    # Combined set of all supported extensions for quick lookup
    SUPPORTED_EXTENSIONS: Set[str] = set()
    for extensions in SUPPORTED_LANGUAGES.values():
        SUPPORTED_EXTENSIONS.update(extensions)
    
    @classmethod
    def detect_language(cls, file_path: str) -> str:
        """Detect language based on file extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language name ('python', 'javascript', 'typescript', 'vue', 'unknown')
        """
        _, ext = os.path.splitext(file_path.lower())
        
        for language, extensions in cls.SUPPORTED_LANGUAGES.items():
            if ext in extensions:
                return language
                
        return 'unknown'
    
    @classmethod
    def is_supported_file(cls, file_path: str) -> bool:
        """Check if file extension is supported.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if supported, False otherwise
        """
        _, ext = os.path.splitext(file_path.lower())
        return ext in cls.SUPPORTED_EXTENSIONS
    
    @classmethod
    def get_supported_extensions(cls) -> Set[str]:
        """Get all supported file extensions.
        
        Returns:
            Set of supported extensions
        """
        return cls.SUPPORTED_EXTENSIONS.copy()
    
    @classmethod
    def get_supported_languages(cls) -> Dict[str, Set[str]]:
        """Get supported languages and their extensions.
        
        Returns:
            Dictionary mapping languages to their extensions
        """
        return {lang: exts.copy() for lang, exts in cls.SUPPORTED_LANGUAGES.items()}
