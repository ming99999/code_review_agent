#!/bin/bash

# AI Code Review Agent - Setup Script
# This script installs all required dependencies for the project

set -e  # Exit on any error

echo "🚀 Setting up AI Code Review Agent environment..."

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "⚠️  Warning: This script is optimized for Linux environments"
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js is not installed"
    echo "Please install Node.js 16+ and try again"
    exit 1
fi

echo "✅ Found Python: $(python3 --version)"
echo "✅ Found Node.js: $(node --version)"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

echo "✅ Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "  - Set up your environment variables (copy .env.example to .env and fill in values)"
echo "  - Run API server: ./run_api.sh"
echo "  - Run CLI mode: ./run_cli.sh"
echo ""
echo "📝 Note: Make sure to have the following environment variables set:"
echo "  - GITHUB_TOKEN: GitHub personal access token"
echo "  - OPENAI_API_KEY: OpenAI API key (or your preferred AI model API key)"
echo "  - PR_NUMBER: Pull Request number (for CLI mode)"
echo "  - REPOSITORY: Repository name (for CLI mode)"
echo "  - PR_HEAD_SHA: PR head commit SHA (for CLI mode)"
echo "  - PR_BASE_SHA: PR base commit SHA (for CLI mode)"
