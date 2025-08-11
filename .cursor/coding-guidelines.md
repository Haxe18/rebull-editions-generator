# Coding Guidelines for Red Bull Editions Generator

## Python Style
- Follow PEP 8 conventions
- Use type hints where appropriate
- Keep functions focused and single-purpose
- Use descriptive variable names

## Error Handling
- Use specific exception types (not generic `Exception`)
- Log errors with appropriate levels (ERROR, CRITICAL)
- Graceful degradation when APIs fail
- Clean up temporary files on errors

## API Integration
- Always use session objects for HTTP requests
- Implement rate limiting with random delays
- Handle network timeouts gracefully
- Validate API responses before processing

## File Operations
- Use UTF-8 encoding for all file operations
- Create output directories if they don't exist
- Use atomic file operations when possible
- Clean up temporary files

## Logging
- Use structured logging with appropriate levels
- Include context in log messages
- Suppress verbose logging from third-party libraries
- Log progress for long-running operations

## Data Processing
- Validate JSON data before processing
- Use defensive programming for API responses
- Handle missing or malformed data gracefully
- Preserve original data structure when possible

## AI Integration
- Keep prompts in separate files
- Validate AI responses before using
- Handle API rate limits and errors
- Log AI processing steps clearly

## Command Line Interface
- Use argparse for argument parsing
- Provide clear help messages
- Support both short and long options
- Validate required environment variables 