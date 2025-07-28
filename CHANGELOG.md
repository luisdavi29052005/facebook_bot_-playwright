
# Changelog

## [2.0.0] - 2024-01-28

### 🚀 Major Refactoring

- **Async non-blocking**: Complete migration from requests to aiohttp
- **Thread safety**: Atomic config saving with threading.Lock
- **Clean shutdown**: Proper stop event handling without orphan threads
- **Comprehensive tests**: pytest suite covering critical functions

### ✨ New Features

- `max_posts_per_cycle` configuration parameter
- Exponential backoff for n8n requests with timeout handling
- Captcha detection and automatic pause
- Improved author extraction with better validation
- Enhanced text extraction using inner_text
- Debug dumps only when all extraction strategies fail

### 🔧 Improvements

- **Config validation**: Min/max limits for intervals and post counts
- **State management**: Thread-safe with post ID normalization
- **Error handling**: Differentiate temporary vs permanent errors
- **Logging**: Reduced noise, structured levels (info/warning/error)
- **Performance**: Optimized post iteration with growth detection

### 🏗️ Architecture

- Modular extraction functions (`encontrar_posts_visiveis`, `rolar_pagina`, `coletar_detalhes_do_post`)
- Centralized CSS selectors in `selectors.py`
- Proper async context management for Playwright
- Type hints and docstrings for public functions

### 🧪 Testing

- Unit tests for extraction functions with realistic HTML fixtures
- Mock-based tests for Playwright interactions
- Thread safety tests for StateManager
- Integration tests for n8n client with aiohttp test server
- Coverage reporting and CI-ready test suite

### 📚 Documentation

- Updated README with setup, execution, and troubleshooting
- API documentation with endpoint descriptions
- Development workflow with make commands
- Configuration reference and examples

### 🐛 Bug Fixes

- Fixed duplicate thread creation on multiple starts
- Resolved memory leaks in Playwright context management
- Corrected post ID consistency issues
- Fixed race conditions in state file access

### ⚠️ Breaking Changes

- Minimum Python 3.8 required
- Configuration validation now enforces limits
- State file format normalized (auto-migrates old format)
- Some internal API changes (affects custom extensions)

## [1.x.x] - Previous Versions

- Initial implementation with synchronous requests
- Basic Flask interface
- Cookie-based login persistence
- Simple post extraction and n8n integration
