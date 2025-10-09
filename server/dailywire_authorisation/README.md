# dailywire-authorisation

A small helper package to generate a login URL for DailyWire using the OAuth 2.0 Device Authorization Grant (Auth0).

The package is written in a pretty generic way and if needed, could be adopted to other OAuth 2.0 Device Authorization Grant providers.

## Usage
### CLI

Login
```bash
dailywire-auth login
```

Get current access token
```bash
dailywire-auth token
```

Status
```bash
dailywire-auth status
```

Logout
```bash
dailywire-auth logout
```

### Library (Programmatic)

The package can be used programmatically from other Python code without any user interaction:

```python
from dailywire_authorisation import DeviceAuthClient, DeviceAuthConfig

# Configure the OAuth client (optional)
config = DeviceAuthConfig(
    issuer="https://your-auth0-domain.auth0.com",
    client_id="your-client-id",
    scope="openid profile email",
    audience="your-api-audience"
)

# Create the client
client = DeviceAuthClient(config)

# Get a valid token (will refresh automatically if expired)
tokens = client.ensure_token()
access_token = tokens.access_token

# Use the access token in your API calls
import requests
response = requests.get(
    "https://api.example.com/endpoint",
    headers={"Authorization": f"Bearer {access_token}"}
)
```

#### Non-interactive Device Flow

For scenarios where you want to handle the device flow UI yourself (e.g., displaying the code in a web interface):

```python
from dailywire_authorisation import DeviceAuthClient

client = DeviceAuthClient()

# Start the device flow
flow_data = client.start_device_flow()
# Returns: {
#   "device_code": "...",
#   "user_code": "ABC-DEF",
#   "verification_uri": "https://...",
#   "verification_uri_complete": "https://...?user_code=ABC-DEF",
#   "expires_in": 900,
#   "interval": 5
# }

# Display the verification_uri and user_code to the user in your UI
print(f"Go to {flow_data['verification_uri']} and enter code: {flow_data['user_code']}")

# Poll for authorization (blocks until user completes auth or timeout)
tokens = client.poll_until_authorized(
    device_code=flow_data["device_code"],
    interval=flow_data["interval"],
    expires_in=flow_data["expires_in"]
)

# Token is now saved and can be retrieved later
access_token = tokens.access_token
```

#### Token Management

```python
# Check if a token exists and is valid
tokens = client.ensure_token()  # Will refresh if expired, or start device flow if missing

# Manually revoke/delete stored tokens
client.revoke()

# Custom token storage location
from dailywire_authorisation import TokenStore
store = TokenStore(service_name="my-custom-service")
client = DeviceAuthClient(config, store=store)
```

**Note:** Tokens are stored securely in the system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service).