"""
Local Repo Compiler (LRC) - Public API.

LRC is a declarative tool for generating repository structures from text schemas.
It provides cross-platform support with security-focused features and enterprise integration.

Key Features:
- Declarative schema language for repository definition
- Cross-platform support (Windows, macOS, Linux, Android, Termux, WSL)
- Template system for common project types
- Security features including path traversal protection and signature verification
- DAT (Dev Audit Tool) integration for security auditing
- Extensible architecture with plugin support

Example Usage:
    >>> from lrc import parse_schema, realize
    >>> actions, metadata, variables = parse_schema(schema_text, output_dir)
    >>> result = realize(actions, output_dir)

Command Line:
    $ lrc schema.txt
    $ lrc --help

For complete documentation, visit: https://github.com/org/lrc
"""

from __future__ import annotations

__version__ = "1.0.0-alpha.1"
__author__ = "Justadudeinspace"
__email__ = "justadudeinspace@example.com"
__license__ = "MIT"
__copyright__ = "Copyright 2024 LRC Project"

import sys
from typing import TYPE_CHECKING

# Public API imports
from .core import (
    ParseError,
    do_bootstrap,
    get_default_output_dir,
    parse_schema,
    print_platform_info,
    realize,
)

from .audit import run_dat_audit
from .cli import main as cli_main

# Re-export types for public API
if TYPE_CHECKING:
    from .core import Action, GenerationResult
    from .compiler import BuildPlan

# Public API exports
__all__ = [
    # Core functionality
    "parse_schema",
    "realize", 
    "get_default_output_dir",
    "print_platform_info",
    "do_bootstrap",
    
    # Error handling
    "ParseError",
    
    # Enterprise features
    "run_dat_audit",
    
    # CLI interface
    "cli_main",
    
    # Types (re-exported for type checking)
    "Action",
    "BuildPlan", 
    "GenerationResult",
]


def get_version_info() -> dict[str, str]:
    """
    Get comprehensive version information for debugging and support.
    
    Returns:
        Dictionary containing version metadata
        
    Example:
        >>> get_version_info()
        {
            'version': '1.0.0-alpha.1',
            'author': 'Justadudeinspace',
            'python_version': '3.9.0',
            'platform': 'linux'
        }
    """
    import platform
    
    return {
        'version': __version__,
        'author': __author__,
        'python_version': platform.python_version(),
        'platform': platform.system().lower(),
        'license': __license__,
    }


def check_compatibility(min_python_version: tuple[int, int] = (3, 8)) -> bool:
    """
    Check if the current environment meets LRC's requirements.
    
    Args:
        min_python_version: Minimum Python version as (major, minor)
        
    Returns:
        True if compatible, False otherwise
        
    Raises:
        SystemExit: If running as main and incompatible
    """
    if sys.version_info < min_python_version:
        if __name__ == "__main__":
            min_ver_str = ".".join(map(str, min_python_version))
            current_ver = ".".join(map(str, sys.version_info[:2]))
            print(
                f"Error: LRC requires Python {min_ver_str} or newer. "
                f"Current version: {current_ver}",
                file=sys.stderr
            )
            sys.exit(1)
        return False
    return True


def setup_logging(level: str = "WARNING") -> None:
    """
    Configure logging for LRC modules.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Note:
        This is called automatically when using the CLI.
        For library use, call this function to enable logging.
    """
    import logging
    
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


class LRCConfig:
    """
    Global configuration for LRC behavior.
    
    This class provides a centralized way to configure LRC's behavior
    across different modules and functions.
    """
    
    # Security settings
    REQUIRE_SIGNED_IMPORTS: bool = False
    VALIDATE_FILE_EXTENSIONS: bool = True
    ENABLE_PATH_TRAVERSAL_CHECKS: bool = True
    
    # Generation settings  
    DEFAULT_LINE_ENDINGS: str = "unix"  # "unix" or "windows"
    CREATE_BACKUPS: bool = False
    DRY_RUN_BY_DEFAULT: bool = False
    
    # Template settings
    TRUSTED_TEMPLATES: set[str] = {
        "python-cli", "node-cli", "rust-cli"
    }
    
    # Audit settings
    AUTO_AUDIT_AFTER_GENERATE: bool = False
    AUDIT_FORMAT: str = "json"  # "json", "pdf", "md", "combined"
    
    @classmethod
    def enable_enterprise_mode(cls) -> None:
        """
        Enable enterprise security features.
        
        This enables stricter security checks and audit requirements
        suitable for enterprise environments.
        """
        cls.REQUIRE_SIGNED_IMPORTS = True
        cls.VALIDATE_FILE_EXTENSIONS = True
        cls.ENABLE_PATH_TRAVERSAL_CHECKS = True
        cls.AUTO_AUDIT_AFTER_GENERATE = True
    
    @classmethod
    def disable_security_checks(cls) -> None:
        """
        Disable security checks (not recommended).
        
        Warning: This should only be used in trusted environments
        and may expose your system to security risks.
        """
        cls.REQUIRE_SIGNED_IMPORTS = False
        cls.VALIDATE_FILE_EXTENSIONS = False
        cls.ENABLE_PATH_TRAVERSAL_CHECKS = False


# Initialize package
def _initialize_package() -> None:
    """
    Initialize LRC package on import.
    
    This function is called automatically when the package is imported
    and handles package-level initialization tasks.
    """
    # Check Python version compatibility
    check_compatibility()
    
    # Set up environment variables
    import os
    os.environ.setdefault('LRC_FORCE_COLOR', '0')
    os.environ.setdefault('LRC_DEBUG', '0')
    
    # Initialize logging if debug mode is enabled
    if os.environ.get('LRC_DEBUG') == '1':
        setup_logging('DEBUG')


# Backwards compatibility imports
# These ensure that existing code continues to work after refactoring
try:
    from .core import Action
    __all__.append('Action')
except ImportError:
    # Action might be defined elsewhere or not available
    pass

try:
    from .compiler import BuildPlan
    __all__.append('BuildPlan')
except ImportError:
    # BuildPlan might be defined elsewhere or not available  
    pass

try:
    from .core import GenerationResult
    __all__.append('GenerationResult')
except ImportError:
    # GenerationResult might be defined elsewhere or not available
    pass

# Initialize package on import
_initialize_package()

# Convenience function for direct execution
def main() -> int:
    """
    Convenience function for executing LRC CLI.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
        
    Example:
        >>> from lrc import main
        >>> exit_code = main()
    """
    return cli_main()


# Allow direct execution: python -m lrc
if __name__ == "__main__":
    sys.exit(main())
