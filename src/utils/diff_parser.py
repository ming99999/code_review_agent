"""Parse and analyze diff content."""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DiffHunk:
    """Represents a diff hunk."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]
    additions: List[Tuple[int, str]]  # (new_line_num, line_content)
    deletions: List[Tuple[int, str]]  # (old_line_num, line_content)


@dataclass
class FileDiff:
    """Represents changes to a single file."""
    old_path: str
    new_path: str
    is_new_file: bool
    is_deleted: bool
    hunks: List[DiffHunk]
    additions: int
    deletions: int


class DiffParser:
    """Parse and analyze diff content."""
    
    def __init__(self):
        self.file_diffs: List[FileDiff] = []
    
    def parse_diff(self, diff_content: str) -> List[FileDiff]:
        """Parse diff content into structured format.
        
        Args:
            diff_content: Raw diff content
            
        Returns:
            List of FileDiff objects
        """
        self.file_diffs = []
        
        if not diff_content:
            return self.file_diffs
        
        lines = diff_content.split('\n')
        current_file_diff = None
        current_hunk = None
        
        for line in lines:
            if line.startswith('diff --git'):
                # Start of new file diff
                if current_file_diff:
                    self.file_diffs.append(current_file_diff)
                
                # Parse file paths
                match = re.match(r'diff --git a/(.*) b/(.*)', line)
                if match:
                    old_path = match.group(1)
                    new_path = match.group(2)
                    current_file_diff = FileDiff(
                        old_path=old_path,
                        new_path=new_path,
                        is_new_file=False,
                        is_deleted=False,
                        hunks=[],
                        additions=0,
                        deletions=0
                    )
                    current_hunk = None
            
            elif line.startswith('new file mode'):
                if current_file_diff:
                    current_file_diff.is_new_file = True
            
            elif line.startswith('deleted file mode'):
                if current_file_diff:
                    current_file_diff.is_deleted = True
            
            elif line.startswith('@@'):
                # Start of new hunk
                if current_file_diff:
                    hunk_info = self._parse_hunk_header(line)
                    current_hunk = DiffHunk(
                        old_start=hunk_info['old_start'],
                        old_count=hunk_info['old_count'],
                        new_start=hunk_info['new_start'],
                        new_count=hunk_info['new_count'],
                        lines=[],
                        additions=[],
                        deletions=[]
                    )
                    current_file_diff.hunks.append(current_hunk)
            
            elif current_hunk is not None:
                # Process line within hunk
                if line.startswith('+') and not line.startswith('+++'):
                    # Added line
                    current_hunk.lines.append(line)
                    current_hunk.additions.append((current_hunk.new_start + len(current_hunk.lines) - 1, line[1:]))
                    if current_file_diff:
                        current_file_diff.additions += 1
                
                elif line.startswith('-') and not line.startswith('---'):
                    # Removed line
                    current_hunk.lines.append(line)
                    current_hunk.deletions.append((current_hunk.old_start + len(current_hunk.lines) - 1, line[1:]))
                    if current_file_diff:
                        current_file_diff.deletions += 1
                
                elif line.startswith(' '):
                    # Context line
                    current_hunk.lines.append(line)
                
                elif line == '\\ No newline at end of file':
                    # Special case
                    current_hunk.lines.append(line)
        
        # Add the last file diff
        if current_file_diff:
            self.file_diffs.append(current_file_diff)
        
        return self.file_diffs
    
    def _parse_hunk_header(self, header: str) -> Dict[str, int]:
        """Parse hunk header to extract line information.
        
        Format: @@ -old_start,old_count +new_start,new_count @@
        """
        match = re.match(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', header)
        if match:
            old_start = int(match.group(1))
            new_start = int(match.group(2))
            
            # Extract counts if available
            count_match = re.match(r'@@ -\d+(,\d+)? \+\d+(,\d+)? @@', header)
            old_count = int(count_match.group(1)[1:]) if count_match and count_match.group(1) else 1
            new_count = int(count_match.group(2)[1:]) if count_match and count_match.group(2) else 1
            
            return {
                'old_start': old_start,
                'old_count': old_count,
                'new_start': new_start,
                'new_count': new_count
            }
        
        return {
            'old_start': 1,
            'old_count': 1,
            'new_start': 1,
            'new_count': 1
        }
    
    def get_changed_files(self) -> List[str]:
        """Get list of changed files."""
        return [diff.new_path for diff in self.file_diffs]
    
    def get_added_lines(self, file_path: str) -> List[Tuple[int, str]]:
        """Get added lines for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of (line_number, line_content) tuples
        """
        for diff in self.file_diffs:
            if diff.new_path == file_path:
                added_lines = []
                for hunk in diff.hunks:
                    added_lines.extend(hunk.additions)
                return added_lines
        return []
    
    def get_deleted_lines(self, file_path: str) -> List[Tuple[int, str]]:
        """Get deleted lines for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of (line_number, line_content) tuples
        """
        for diff in self.file_diffs:
            if diff.old_path == file_path:
                deleted_lines = []
                for hunk in diff.hunks:
                    deleted_lines.extend(hunk.deletions)
                return deleted_lines
        return []
    
    def get_modified_lines_range(self, file_path: str) -> List[Tuple[int, int]]:
        """Get ranges of modified lines for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of (start_line, end_line) tuples
        """
        for diff in self.file_diffs:
            if diff.new_path == file_path:
                ranges = []
                for hunk in diff.hunks:
                    start = hunk.new_start
                    end = hunk.new_start + hunk.new_count - 1
                    ranges.append((start, end))
                return ranges
        return []
    
    def extract_context_around_changes(self, file_content: str, file_path: str, context_lines: int = 3) -> Dict[int, str]:
        """Extract context around changed lines.
        
        Args:
            file_content: Full file content
            file_path: Path to the file
            context_lines: Number of context lines around changes
            
        Returns:
            Dictionary mapping line numbers to context snippets
        """
        lines = file_content.split('\n')
        modified_ranges = self.get_modified_lines_range(file_path)
        
        context_snippets = {}
        
        for start_line, end_line in modified_ranges:
            # Calculate context range
            context_start = max(1, start_line - context_lines)
            context_end = min(len(lines), end_line + context_lines)
            
            # Extract context
            context_lines_list = lines[context_start-1:context_end]
            context_content = '\n'.join(context_lines_list)
            
            # Store with the start line as key
            context_snippets[start_line] = context_content
        
        return context_snippets
    
    def is_python_file(self, file_path: str) -> bool:
        """Check if file is a Python file based on path."""
        return file_path.endswith('.py')
    
    def is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file."""
        test_patterns = [
            'test_',
            '_test.py',
            '/tests/',
            '/test/'
        ]
        return any(pattern in file_path for pattern in test_patterns)
    
    def filter_python_files(self) -> List[FileDiff]:
        """Get only Python file diffs."""
        return [diff for diff in self.file_diffs if self.is_python_file(diff.new_path)]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of diff changes.
        
        Returns:
            Dictionary with summary statistics
        """
        total_files = len(self.file_diffs)
        total_additions = sum(diff.additions for diff in self.file_diffs)
        total_deletions = sum(diff.deletions for diff in self.file_diffs)
        python_files = len(self.filter_python_files())
        
        return {
            'total_files': total_files,
            'python_files': python_files,
            'total_additions': total_additions,
            'total_deletions': total_deletions,
            'total_changes': total_additions + total_deletions
        }