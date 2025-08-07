# API Reference for Red Bull Editions Generator

## Red Bull APIs

### Language API
- **URL**: `https://www.redbull.com/v3/api/custom/header/v2?locale={locale}`
- **Purpose**: Get list of available locales and featured energy drinks
- **Response**: JSON with `selectableLocales` and `featuredEnergyDrinks`
- **Rate Limiting**: Random delays 1-3 seconds between requests

### GraphQL API
- **URL**: `https://www.redbull.com/v3/api/graphql/v1/?rb3ResourceId={graphql_id}&rb3Schema=v1:assetInfo`
- **Purpose**: Get detailed product information for each edition
- **Response**: JSON with product details (name, flavor, image, etc.)
- **Rate Limiting**: Random delays 1-3 seconds between requests

### Flag API
- **URL**: `https://rbds-static.redbull.com/@cosmos/foundation/latest/flags/cosmos-flag-{flag_code}.svg`
- **Purpose**: Get country flag images
- **Response**: SVG flag images

## Google Gemini API

### Configuration
- **Model**: `gemini-2.5-flash-lite`
- **Environment Variable**: `GEMINI_API_KEY`
- **Response Format**: JSON (`application/json`)

### Usage
- **Purpose**: Normalize and translate flavor names
- **Input**: Raw JSON data from Red Bull APIs
- **Output**: Standardized, English-language JSON
- **Prompt**: Loaded from `gemini_prompt.txt`

## Error Handling

### Network Errors
- Connection timeouts
- HTTP status errors (4xx, 5xx)
- JSON parsing errors
- Rate limiting responses

### API-Specific Errors
- Missing API keys
- Invalid responses
- Malformed data
- Authentication failures

## Rate Limiting Strategy
- Random delays between requests (1-3 seconds)
- Session-based connection reuse
- Graceful error handling
- Retry logic for transient failures 