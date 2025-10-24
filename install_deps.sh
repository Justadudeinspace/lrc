#!/bin/bash
# LRC dependency installer - cross-platform support

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[LRC]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Detect platform
detect_platform() {
    case "$(uname -s)" in
        Linux*)
            if [[ -f /proc/version && $(grep -i microsoft /proc/version) ]]; then
                echo "wsl"
            elif [[ -d /data/data/com.termux ]]; then
                echo "termux"
            elif [[ $(uname -o) == "Android" ]]; then
                echo "android"
            else
                echo "linux"
            fi
            ;;
        Darwin*)
            echo "macos"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install system dependencies
install_system_deps() {
    local platform=$1
    
    case $platform in
        linux)
            if command_exists apt; then
                log "Installing Ubuntu/Debian dependencies..."
                sudo apt update && sudo apt install -y \
                    python3 \
                    python3-pip \
                    python3-venv \
                    git \
                    libmagic1 \
                    fonts-powerline
            elif command_exists dnf; then
                log "Installing Fedora/RHEL dependencies..."
                sudo dnf install -y \
                    python3 \
                    python3-pip \
                    python3-virtualenv \
                    git \
                    file-devel \
                    powerline-fonts
            elif command_exists pacman; then
                log "Installing Arch Linux dependencies..."
                sudo pacman -S --noconfirm \
                    python \
                    python-pip \
                    git \
                    libmagic \
                    powerline-fonts
            elif command_exists zypper; then
                log "Installing openSUSE dependencies..."
                sudo zypper install -y \
                    python3 \
                    python3-pip \
                    git \
                    python3-virtualenv \
                    file-devel
            else
                warn "Unknown package manager - please install Python 3.8+ and git manually"
            fi
            ;;
            
        wsl)
            log "Installing WSL dependencies..."
            if command_exists apt; then
                sudo apt update && sudo apt install -y \
                    python3 \
                    python3-pip \
                    python3-venv \
                    git \
                    libmagic1 \
                    fonts-powerline
            else
                warn "Unknown package manager in WSL"
            fi
            ;;
            
        termux)
            log "Installing Termux dependencies..."
            pkg update && pkg install -y \
                python \
                git \
                libmagic
            ;;
            
        macos)
            if command_exists brew; then
                log "Installing macOS dependencies via Homebrew..."
                brew install \
                    python@3 \
                    git \
                    libmagic
            else
                warn "Homebrew not found - please install Python 3.8+ and git manually"
                info "To install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            fi
            ;;
            
        windows)
            log "Windows detected - please ensure you have:"
            info "  - Python 3.8+ (from Microsoft Store or python.org)"
            info "  - Git for Windows (from git-scm.com)"
            info "  - Windows Terminal (recommended)"
            return 0
            ;;
            
        *)
            warn "Unknown platform - please install dependencies manually"
            return 1
            ;;
    esac
}

# Setup Python environment
setup_python_env() {
    local with_venv=$1
    
    if [[ $with_venv == "yes" ]]; then
        log "Creating Python virtual environment..."
        python3 -m venv .venv
        source .venv/bin/activate
        
        if [[ $platform == "windows" ]]; then
            source .venv/Scripts/activate
        fi
    fi
    
    log "Installing LRC package..."
    pip install -e .
    
    if [[ -f "requirements.txt" ]]; then
        log "Installing runtime dependencies..."
        pip install -r requirements.txt
    fi
}

# Setup shell integration
setup_shell_integration() {
    local platform=$1
    
    log "Setting up shell integration..."
    
    # Detect shell
    local shell_name=$(basename "$SHELL")
    local rc_file=""
    
    case $shell_name in
        bash)
            rc_file="$HOME/.bashrc"
            ;;
        zsh)
            rc_file="$HOME/.zshrc"
            ;;
        fish)
            rc_file="$HOME/.config/fish/config.fish"
            mkdir -p "$(dirname "$rc_file")"
            ;;
        *)
            warn "Unknown shell $shell_name - please add LRC to PATH manually"
            return 1
            ;;
    esac
    
    if [[ -n "$rc_file" ]]; then
        # Get the directory where LRC is installed
        local lrc_dir=$(pwd)
        local bin_dir="$lrc_dir/.venv/bin"  # If using venv
        
        if [[ -d "$bin_dir" ]]; then
            local path_cmd=""
            
            case $shell_name in
                bash|zsh)
                    path_cmd="export PATH=\"$bin_dir:\$PATH\""
                    ;;
                fish)
                    path_cmd="set -gx PATH \"$bin_dir\" \$PATH"
                    ;;
            esac
            
            if [[ -n "$path_cmd" ]]; then
                if ! grep -q "$bin_dir" "$rc_file" 2>/dev/null; then
                    echo -e "\n# LRC - Local Repo Compile" >> "$rc_file"
                    echo "$path_cmd" >> "$rc_file"
                    log "Added LRC to $rc_file"
                else
                    info "LRC already in PATH in $rc_file"
                fi
            fi
        fi
    fi
}

# Verify installation
verify_installation() {
    log "Verifying installation..."
    
    # Try to run lrc with --version
    if command_exists lrc; then
        if lrc --version >/dev/null 2>&1; then
            log "LRC installed successfully!"
            return 0
        fi
    fi
    
    # Fallback: try Python module
    if python -c "import lrc; print(lrc.__version__)" >/dev/null 2>&1; then
        log "LRC Python package installed successfully!"
        info "You can run it with: python -m lrc"
        return 0
    fi
    
    error "Installation verification failed"
    return 1
}

# Main installation function
main() {
    local with_venv="no"
    local platform=$(detect_platform)
    
    log "LRC Dependency Installer"
    info "Platform: $platform"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --with-venv)
                with_venv="yes"
                shift
                ;;
            *)
                warn "Unknown option: $1"
                shift
                ;;
        esac
    done
    
    # Install system dependencies
    install_system_deps "$platform"
    
    # Setup Python environment
    setup_python_env "$with_venv"
    
    # Setup shell integration
    setup_shell_integration "$platform"
    
    # Verify installation
    if verify_installation; then
        log "🎉 LRC is ready to use!"
        info "Quick start:"
        info "  lrc --help                          # Show help"
        info "  lrc examples/schema_example.lrc     # Run example"
        
        if [[ $with_venv == "yes" ]]; then
            info "Remember to activate virtual environment:"
            if [[ $platform == "windows" ]]; then
                info "  .venv\\Scripts\\activate"
            else
                info "  source .venv/bin/activate"
            fi
        fi
    else
        error "Installation completed with issues"
        error "Please check the output above and fix any errors"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"
