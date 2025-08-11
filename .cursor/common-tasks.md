# Common Development Tasks

## Testing the Script

### Normal Run (with external data)
```bash
python redbull_editions_json_generate.py
```

### Test with local data only
```bash
python redbull_editions_json_generate.py --skip-external-fetch
```

### Debug mode
```bash
python redbull_editions_json_generate.py -v
```

## Environment Setup

### Set API Key
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Linux/macOS
export GEMINI_API_KEY="your_api_key_here"
```

### Force Processing
```bash
# Force processing even when no changes detected
python redbull_editions_json_generate.py --force

# Combine with other options
python redbull_editions_json_generate.py --force -v
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

## File Structure

### Input Files
- `gemini_prompt.txt` - AI prompt for normalization
- `requirements.txt` - Python dependencies

### Output Files (in `dist/`)
- `redbull_editions_raw.json` - Raw data from APIs
- `redbull_editions_raw.previous.json` - Previous run's raw data
- `redbull_editions.json` - Final normalized data
- `changelog.md` - Changes detected between runs

## Debugging

### Check API Responses
- Enable verbose logging with `-v`
- Check network connectivity
- Verify API key is set correctly

### Common Issues
- Missing `GEMINI_API_KEY` environment variable
- Network connectivity problems
- Invalid JSON responses from APIs
- Rate limiting from Red Bull servers

## Development Workflow

1. **Make changes** to the script
2. **Test locally** with `--skip-external-fetch`
3. **Run full test** with external data
4. **Check output** in `dist/` directory
5. **Verify** JSON structure and content

## Performance Optimization

- Use `--skip-external-fetch` for testing AI processing
- Monitor API rate limits
- Check file sizes and processing times
- Optimize prompt if needed 